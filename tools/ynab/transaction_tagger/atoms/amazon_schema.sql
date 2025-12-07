-- Amazon Item Categorization Schema
-- Scalable storage for Amazon purchase item-level categorization
-- Supports split transactions across multiple YNAB categories

-- ============================================================================
-- TABLE: amazon_items
-- Stores individual line items from Amazon invoices with category mappings
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_items (
    -- Identity
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) NOT NULL,              -- Amazon order ID
    order_date DATE NOT NULL,                   -- Purchase date

    -- Item Details
    item_name TEXT NOT NULL,                    -- Product name/description
    item_asin VARCHAR(20),                      -- Amazon ASIN (unique product ID)
    quantity INTEGER DEFAULT 1,                 -- Number of items
    unit_price_milliunits BIGINT NOT NULL,      -- Price per item in milliunits ($1.00 = 1000000)
    total_price_milliunits BIGINT NOT NULL,     -- Line item total in milliunits

    -- Categorization
    category_id VARCHAR(50),                    -- YNAB category ID
    category_name VARCHAR(200),                 -- YNAB category name
    category_group VARCHAR(200),                -- YNAB category group for reference

    -- Learning & Confidence
    categorization_method VARCHAR(50),          -- 'manual' | 'learned' | 'keyword' | 'asin_match'
    confidence_score DECIMAL(3,2),              -- 0.00-1.00 confidence
    user_verified BOOLEAN DEFAULT FALSE,        -- User confirmed this mapping

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    -- Indexes
    CONSTRAINT unique_order_item UNIQUE (order_id, item_name, unit_price_milliunits)
);

-- Index for fast lookups by order
CREATE INDEX IF NOT EXISTS idx_amazon_items_order_id ON amazon_items(order_id);

-- Index for ASIN-based categorization (exact product match)
CREATE INDEX IF NOT EXISTS idx_amazon_items_asin ON amazon_items(asin) WHERE asin IS NOT NULL;

-- Index for keyword-based categorization (partial name match)
CREATE INDEX IF NOT EXISTS idx_amazon_items_name ON amazon_items USING gin(to_tsvector('english', item_name));

-- Index for verified items (highest priority for learning)
CREATE INDEX IF NOT EXISTS idx_amazon_items_verified ON amazon_items(user_verified) WHERE user_verified = TRUE;

-- Auto-update timestamp trigger
CREATE OR REPLACE FUNCTION update_amazon_items_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER amazon_items_update_timestamp
    BEFORE UPDATE ON amazon_items
    FOR EACH ROW
    EXECUTE FUNCTION update_amazon_items_timestamp();


-- ============================================================================
-- TABLE: amazon_order_totals
-- Tracks Amazon order-level totals for reconciliation
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_order_totals (
    -- Identity
    order_id VARCHAR(50) PRIMARY KEY,           -- Amazon order ID
    order_date DATE NOT NULL,                   -- Purchase date

    -- Order Totals
    subtotal_milliunits BIGINT,                 -- Subtotal before tax/shipping
    tax_milliunits BIGINT,                      -- Sales tax
    shipping_milliunits BIGINT,                 -- Shipping fees
    total_milliunits BIGINT NOT NULL,           -- Final total charged

    -- YNAB Reconciliation
    ynab_transaction_id VARCHAR(50),            -- Linked YNAB transaction
    reconciled BOOLEAN DEFAULT FALSE,           -- Items reconciled to transaction
    split_count INTEGER DEFAULT 1,              -- Number of YNAB split categories

    -- Metadata
    invoice_path TEXT,                          -- Path to PDF invoice
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Index for YNAB transaction lookups
CREATE INDEX IF NOT EXISTS idx_amazon_orders_ynab_txn ON amazon_order_totals(ynab_transaction_id);

-- Index for unreconciled orders
CREATE INDEX IF NOT EXISTS idx_amazon_orders_unreconciled ON amazon_order_totals(reconciled) WHERE reconciled = FALSE;

-- Auto-update timestamp trigger
CREATE TRIGGER amazon_order_totals_update_timestamp
    BEFORE UPDATE ON amazon_order_totals
    FOR EACH ROW
    EXECUTE FUNCTION update_amazon_items_timestamp();


-- ============================================================================
-- FUNCTION: get_amazon_item_category
-- Find category for an Amazon item using multi-tier matching
-- ============================================================================
CREATE OR REPLACE FUNCTION get_amazon_item_category(
    p_item_name TEXT,
    p_asin VARCHAR(20) DEFAULT NULL
)
RETURNS TABLE(
    category_id VARCHAR(50),
    category_name VARCHAR(200),
    confidence DECIMAL(3,2),
    method VARCHAR(50)
) AS $$
BEGIN
    -- Tier 1: Exact ASIN match (highest confidence)
    IF p_asin IS NOT NULL THEN
        RETURN QUERY
        SELECT
            ai.category_id,
            ai.category_name,
            CASE
                WHEN ai.user_verified THEN 1.00::DECIMAL(3,2)
                ELSE ai.confidence_score
            END as confidence,
            'asin_exact'::VARCHAR(50) as method
        FROM amazon_items ai
        WHERE ai.asin = p_asin
          AND ai.category_id IS NOT NULL
        ORDER BY ai.user_verified DESC, ai.confidence_score DESC
        LIMIT 1;

        IF FOUND THEN
            RETURN;
        END IF;
    END IF;

    -- Tier 2: Exact item name match (user verified)
    RETURN QUERY
    SELECT
        ai.category_id,
        ai.category_name,
        0.95::DECIMAL(3,2) as confidence,
        'name_exact_verified'::VARCHAR(50) as method
    FROM amazon_items ai
    WHERE ai.item_name = p_item_name
      AND ai.user_verified = TRUE
      AND ai.category_id IS NOT NULL
    ORDER BY ai.updated_at DESC
    LIMIT 1;

    IF FOUND THEN
        RETURN;
    END IF;

    -- Tier 3: Fuzzy item name match (learned patterns)
    RETURN QUERY
    SELECT
        ai.category_id,
        ai.category_name,
        0.80::DECIMAL(3,2) as confidence,
        'name_fuzzy'::VARCHAR(50) as method
    FROM amazon_items ai
    WHERE to_tsvector('english', ai.item_name) @@ to_tsquery('english',
          regexp_replace(p_item_name, '[^a-zA-Z0-9\s]', '', 'g'))
      AND ai.category_id IS NOT NULL
    ORDER BY ai.user_verified DESC, ai.confidence_score DESC, ai.updated_at DESC
    LIMIT 1;

    IF FOUND THEN
        RETURN;
    END IF;

    -- No match found
    RETURN;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- FUNCTION: categorize_amazon_order
-- Split Amazon order into multiple YNAB categories
-- ============================================================================
CREATE OR REPLACE FUNCTION categorize_amazon_order(p_order_id VARCHAR(50))
RETURNS TABLE(
    category_id VARCHAR(50),
    category_name VARCHAR(200),
    amount_milliunits BIGINT,
    memo TEXT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        ai.category_id,
        ai.category_name,
        ai.total_price_milliunits as amount_milliunits,
        ai.item_name as memo
    FROM amazon_items ai
    WHERE ai.order_id = p_order_id
      AND ai.category_id IS NOT NULL
    ORDER BY ai.total_price_milliunits DESC;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE amazon_items IS 'Individual line items from Amazon orders with YNAB category mappings';
COMMENT ON TABLE amazon_order_totals IS 'Amazon order-level totals for reconciliation with YNAB transactions';
COMMENT ON FUNCTION get_amazon_item_category IS 'Find category for Amazon item using ASIN, exact name, or fuzzy matching';
COMMENT ON FUNCTION categorize_amazon_order IS 'Generate split transaction breakdown for Amazon order';
