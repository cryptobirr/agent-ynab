-- Amazon V2 Database Schema - Shipment-Based Matching
-- Handles Amazon's real-world billing: 1 order → N shipments → N YNAB transactions

-- ============================================================================
-- TABLE: amazon_orders
-- Order-level data from invoices
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_orders (
    order_id VARCHAR(50) PRIMARY KEY,
    order_date DATE NOT NULL,

    -- Order totals
    order_total_milliunits BIGINT,
    subtotal_milliunits BIGINT,
    tax_milliunits BIGINT,
    shipping_milliunits BIGINT,

    -- Metadata
    invoice_path TEXT,
    parsed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_orders_date ON amazon_orders(order_date);
CREATE INDEX IF NOT EXISTS idx_orders_parsed ON amazon_orders(parsed_at);


-- ============================================================================
-- TABLE: amazon_items
-- Line items - the source of truth for categorization
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_items (
    id SERIAL PRIMARY KEY,
    order_id VARCHAR(50) REFERENCES amazon_orders(order_id) ON DELETE CASCADE,

    -- Item details
    item_name TEXT NOT NULL,
    item_asin VARCHAR(20),
    quantity INTEGER DEFAULT 1,
    unit_price_milliunits BIGINT,
    line_total_milliunits BIGINT,

    -- Shipment tracking
    shipment_id VARCHAR(100),
    shipped_date DATE,

    -- Categorization (learned from user)
    category_id VARCHAR(50),
    category_name VARCHAR(200),
    confidence_score DECIMAL(3,2),
    user_verified BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT unique_item UNIQUE (order_id, item_name, unit_price_milliunits)
);

CREATE INDEX IF NOT EXISTS idx_items_order ON amazon_items(order_id);
CREATE INDEX IF NOT EXISTS idx_items_shipment ON amazon_items(shipment_id) WHERE shipment_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_asin ON amazon_items(item_asin) WHERE item_asin IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_items_name_fts ON amazon_items USING gin(to_tsvector('english', item_name));
CREATE INDEX IF NOT EXISTS idx_items_verified ON amazon_items(user_verified) WHERE user_verified = TRUE;


-- ============================================================================
-- TABLE: amazon_shipments
-- Shipment tracking - links items to YNAB transactions
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_shipments (
    id SERIAL PRIMARY KEY,
    shipment_id VARCHAR(100) UNIQUE,
    order_id VARCHAR(50) REFERENCES amazon_orders(order_id) ON DELETE CASCADE,

    -- Shipment details
    shipment_date DATE,
    shipment_total_milliunits BIGINT,
    item_count INTEGER DEFAULT 0,

    -- YNAB matching
    ynab_transaction_id VARCHAR(50),
    match_confidence DECIMAL(3,2),
    match_method VARCHAR(50),  -- 'exact' | 'fuzzy_amount' | 'fuzzy_date' | 'manual'
    matched BOOLEAN DEFAULT FALSE,

    -- Metadata
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_shipments_order ON amazon_shipments(order_id);
CREATE INDEX IF NOT EXISTS idx_shipments_date ON amazon_shipments(shipment_date);
CREATE INDEX IF NOT EXISTS idx_shipments_amount ON amazon_shipments(shipment_total_milliunits);
CREATE INDEX IF NOT EXISTS idx_shipments_unmatched ON amazon_shipments(matched) WHERE matched = FALSE;
CREATE INDEX IF NOT EXISTS idx_shipments_ynab_txn ON amazon_shipments(ynab_transaction_id) WHERE ynab_transaction_id IS NOT NULL;


-- ============================================================================
-- TABLE: amazon_match_attempts
-- Audit trail for transaction-shipment matching
-- ============================================================================
CREATE TABLE IF NOT EXISTS amazon_match_attempts (
    id SERIAL PRIMARY KEY,

    -- YNAB transaction
    ynab_transaction_id VARCHAR(50) NOT NULL,
    ynab_amount_milliunits BIGINT,
    ynab_date DATE,

    -- Matched shipment
    shipment_id VARCHAR(100),
    shipment_amount_milliunits BIGINT,
    shipment_date DATE,

    -- Match quality
    confidence_score DECIMAL(3,2),
    match_method VARCHAR(50),
    amount_diff_milliunits BIGINT,
    date_diff_days INTEGER,

    -- Status
    status VARCHAR(20), -- 'accepted' | 'rejected' | 'pending'
    created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_match_attempts_txn ON amazon_match_attempts(ynab_transaction_id);
CREATE INDEX IF NOT EXISTS idx_match_attempts_shipment ON amazon_match_attempts(shipment_id);
CREATE INDEX IF NOT EXISTS idx_match_attempts_status ON amazon_match_attempts(status);


-- ============================================================================
-- Auto-update triggers
-- ============================================================================
CREATE OR REPLACE FUNCTION update_amazon_timestamp()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER amazon_orders_update_timestamp
    BEFORE UPDATE ON amazon_orders
    FOR EACH ROW
    EXECUTE FUNCTION update_amazon_timestamp();

CREATE TRIGGER amazon_items_update_timestamp
    BEFORE UPDATE ON amazon_items
    FOR EACH ROW
    EXECUTE FUNCTION update_amazon_timestamp();

CREATE TRIGGER amazon_shipments_update_timestamp
    BEFORE UPDATE ON amazon_shipments
    FOR EACH ROW
    EXECUTE FUNCTION update_amazon_timestamp();


-- ============================================================================
-- FUNCTION: find_shipment_matches
-- Fuzzy matching of YNAB transactions to Amazon shipments
-- ============================================================================
CREATE OR REPLACE FUNCTION find_shipment_matches(
    p_transaction_amount BIGINT,
    p_transaction_date DATE,
    p_amount_tolerance BIGINT DEFAULT 500000,  -- $0.50
    p_date_window_days INTEGER DEFAULT 3
)
RETURNS TABLE(
    shipment_id VARCHAR(100),
    order_id VARCHAR(50),
    shipment_date DATE,
    shipment_amount BIGINT,
    item_count INTEGER,
    confidence DECIMAL(3,2),
    match_method VARCHAR(50),
    amount_diff BIGINT,
    date_diff INTEGER
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        s.shipment_id,
        s.order_id,
        s.shipment_date,
        s.shipment_total_milliunits,
        s.item_count,
        CASE
            -- Exact match (100%)
            WHEN s.shipment_total_milliunits = p_transaction_amount
                 AND s.shipment_date = p_transaction_date
            THEN 1.00::DECIMAL(3,2)

            -- Exact amount, near date (95%)
            WHEN s.shipment_total_milliunits = p_transaction_amount
                 AND ABS(s.shipment_date - p_transaction_date) = 1
            THEN 0.95::DECIMAL(3,2)

            -- Near amount, exact date (90%)
            WHEN ABS(s.shipment_total_milliunits - p_transaction_amount) <= 100000
                 AND s.shipment_date = p_transaction_date
            THEN 0.90::DECIMAL(3,2)

            -- Fuzzy match (80-85%)
            WHEN ABS(s.shipment_total_milliunits - p_transaction_amount) <= p_amount_tolerance
                 AND ABS(s.shipment_date - p_transaction_date) <= p_date_window_days
            THEN (0.85 - (ABS(s.shipment_date - p_transaction_date) * 0.01))::DECIMAL(3,2)

            ELSE 0.50::DECIMAL(3,2)
        END as confidence,
        CASE
            WHEN s.shipment_total_milliunits = p_transaction_amount
                 AND s.shipment_date = p_transaction_date
            THEN 'exact'::VARCHAR(50)

            WHEN s.shipment_total_milliunits = p_transaction_amount
            THEN 'fuzzy_date'::VARCHAR(50)

            WHEN s.shipment_date = p_transaction_date
            THEN 'fuzzy_amount'::VARCHAR(50)

            ELSE 'fuzzy'::VARCHAR(50)
        END as match_method,
        ABS(s.shipment_total_milliunits - p_transaction_amount)::BIGINT as amount_diff,
        ABS(s.shipment_date - p_transaction_date)::INTEGER as date_diff
    FROM amazon_shipments s
    WHERE s.matched = FALSE
      AND ABS(s.shipment_total_milliunits - p_transaction_amount) <= p_amount_tolerance
      AND ABS(s.shipment_date - p_transaction_date) <= p_date_window_days
    ORDER BY confidence DESC, amount_diff ASC, date_diff ASC
    LIMIT 5;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- FUNCTION: get_shipment_items
-- Get all items in a shipment for split transaction generation
-- ============================================================================
CREATE OR REPLACE FUNCTION get_shipment_items(p_shipment_id VARCHAR(100))
RETURNS TABLE(
    item_name TEXT,
    item_asin VARCHAR(20),
    quantity INTEGER,
    line_total_milliunits BIGINT,
    category_id VARCHAR(50),
    category_name VARCHAR(200),
    confidence_score DECIMAL(3,2),
    user_verified BOOLEAN
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        i.item_name,
        i.item_asin,
        i.quantity,
        i.line_total_milliunits,
        i.category_id,
        i.category_name,
        i.confidence_score,
        i.user_verified
    FROM amazon_items i
    WHERE i.shipment_id = p_shipment_id
    ORDER BY i.line_total_milliunits DESC;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- FUNCTION: get_unmatched_shipments_summary
-- Get summary of unmatched shipments for dashboard
-- ============================================================================
CREATE OR REPLACE FUNCTION get_unmatched_shipments_summary()
RETURNS TABLE(
    total_unmatched BIGINT,
    date_range_start DATE,
    date_range_end DATE,
    total_amount_milliunits BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        COUNT(*)::BIGINT as total_unmatched,
        MIN(shipment_date) as date_range_start,
        MAX(shipment_date) as date_range_end,
        SUM(shipment_total_milliunits)::BIGINT as total_amount_milliunits
    FROM amazon_shipments
    WHERE matched = FALSE;
END;
$$ LANGUAGE plpgsql;


-- ============================================================================
-- Comments
-- ============================================================================
COMMENT ON TABLE amazon_orders IS 'Order-level data from Amazon invoices';
COMMENT ON TABLE amazon_items IS 'Line items with learned categorization';
COMMENT ON TABLE amazon_shipments IS 'Shipment tracking - links items to YNAB transactions';
COMMENT ON TABLE amazon_match_attempts IS 'Audit trail for transaction-shipment matching';

COMMENT ON FUNCTION find_shipment_matches IS 'Fuzzy match YNAB transactions to shipments using amount and date tolerance';
COMMENT ON FUNCTION get_shipment_items IS 'Get all items in a shipment for split transaction generation';
COMMENT ON FUNCTION get_unmatched_shipments_summary IS 'Dashboard summary of unmatched shipments';
