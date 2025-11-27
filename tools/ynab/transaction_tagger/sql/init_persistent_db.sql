-- ====================================================================
-- YNAB Transaction Tagger - Persistent Database Schema Initialization
-- ====================================================================
-- Version: 1.0.0
-- Created: 2025-11-27T06:32:30Z
-- Author: Agent (via Story 1.3 - Issue #3)
-- 
-- Purpose: Create persistent PostgreSQL tables for YNAB transaction
--          history, split transactions, SOP rules, and agent metadata.
--
-- Usage:
--   psql -U postgres -d ynab_db -f tools/ynab/transaction_tagger/sql/init_persistent_db.sql
--
-- Notes:
--   - Idempotent: Safe to run multiple times (IF NOT EXISTS)
--   - Requires PostgreSQL 14+
--   - Must be run by database owner (not application user)
-- ====================================================================

-- Version check: Require PostgreSQL 14+
DO $$
BEGIN
    IF (SELECT split_part(version(), ' ', 2)::numeric < 14) THEN
        RAISE EXCEPTION 'PostgreSQL 14+ required. Current version: %', version();
    END IF;
END $$;

-- ====================================================================
-- TABLE 1: ynab_transactions
-- ====================================================================
-- Purpose: Store ALL historical transaction data from YNAB for pattern
--          analysis. Supports Learning Budget and Target Budget.
-- ====================================================================

CREATE TABLE IF NOT EXISTS ynab_transactions (
    -- Primary Key
    id TEXT PRIMARY KEY,  -- YNAB transaction ID (unique per transaction)
    
    -- Transaction Core Fields
    account_id TEXT NOT NULL,
    date DATE NOT NULL,
    amount BIGINT NOT NULL,  -- YNAB stores in milliunits (1000 = $1.00)
    payee_id TEXT,
    payee_name TEXT,
    category_id TEXT,
    category_name TEXT,
    memo TEXT,
    cleared TEXT,  -- 'cleared', 'uncleared', 'reconciled'
    approved BOOLEAN,
    flag_color TEXT,
    
    -- Budget Tracking
    budget_id TEXT NOT NULL,  -- Differentiates INIT_BUDGET vs TARGET_BUDGET
    
    -- Split Transaction Support
    is_split BOOLEAN DEFAULT FALSE,  -- True if this transaction has subtransactions
    subtransaction_count INTEGER DEFAULT 0,
    
    -- Learning Metadata
    confidence_score REAL,  -- 0.0-1.0, NULL if not categorized by agent
    categorization_tier INTEGER,  -- 1=SOP, 2=Historical, 3=Research, NULL=Manual
    categorization_timestamp TIMESTAMP WITH TIME ZONE,
    user_approved BOOLEAN DEFAULT FALSE,
    user_corrected BOOLEAN DEFAULT FALSE,  -- True if user changed agent recommendation
    
    -- Audit Trail
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1  -- Increments on each UPSERT
);

-- Indexes for pattern matching performance (Tier 2 historical lookup)
CREATE INDEX IF NOT EXISTS idx_transactions_payee_name ON ynab_transactions(payee_name);
CREATE INDEX IF NOT EXISTS idx_transactions_category_id ON ynab_transactions(category_id);
CREATE INDEX IF NOT EXISTS idx_transactions_budget_id ON ynab_transactions(budget_id);
CREATE INDEX IF NOT EXISTS idx_transactions_date ON ynab_transactions(date DESC);

-- Learning analytics indexes
CREATE INDEX IF NOT EXISTS idx_transactions_confidence ON ynab_transactions(confidence_score) 
    WHERE confidence_score IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_transactions_tier ON ynab_transactions(categorization_tier) 
    WHERE categorization_tier IS NOT NULL;

-- Constraints
ALTER TABLE ynab_transactions 
    DROP CONSTRAINT IF EXISTS check_confidence_range;
ALTER TABLE ynab_transactions 
    ADD CONSTRAINT check_confidence_range 
    CHECK (confidence_score IS NULL OR (confidence_score >= 0.0 AND confidence_score <= 1.0));

ALTER TABLE ynab_transactions 
    DROP CONSTRAINT IF EXISTS check_tier_values;
ALTER TABLE ynab_transactions 
    ADD CONSTRAINT check_tier_values 
    CHECK (categorization_tier IS NULL OR categorization_tier IN (1, 2, 3));

ALTER TABLE ynab_transactions 
    DROP CONSTRAINT IF EXISTS check_cleared_status;
ALTER TABLE ynab_transactions 
    ADD CONSTRAINT check_cleared_status 
    CHECK (cleared IN ('cleared', 'uncleared', 'reconciled'));

-- Table comments
COMMENT ON TABLE ynab_transactions IS 'Persistent storage for all YNAB transactions (Learning + Target budgets)';
COMMENT ON COLUMN ynab_transactions.amount IS 'Amount in milliunits (1000 = $1.00) per YNAB API standard';
COMMENT ON COLUMN ynab_transactions.confidence_score IS 'Agent categorization confidence (0.0-1.0), NULL if manual';
COMMENT ON COLUMN ynab_transactions.categorization_tier IS 'Tier used: 1=SOP, 2=Historical, 3=Research, NULL=Manual';
COMMENT ON COLUMN ynab_transactions.sync_version IS 'Increments on each UPSERT for audit trail';

-- ====================================================================
-- TABLE 2: ynab_split_transactions
-- ====================================================================
-- Purpose: Store split transaction subtransactions (e.g., Walmart 
--          purchase with groceries + household items).
-- ====================================================================

CREATE TABLE IF NOT EXISTS ynab_split_transactions (
    -- Primary Key
    id TEXT PRIMARY KEY,  -- YNAB subtransaction ID
    
    -- Foreign Key to Parent Transaction
    parent_transaction_id TEXT NOT NULL,
    
    -- Subtransaction Fields
    amount BIGINT NOT NULL,
    payee_id TEXT,
    payee_name TEXT,
    category_id TEXT,
    category_name TEXT,
    memo TEXT,
    
    -- Budget Tracking
    budget_id TEXT NOT NULL,
    
    -- Learning Metadata
    confidence_score REAL,
    categorization_tier INTEGER,
    categorization_timestamp TIMESTAMP WITH TIME ZONE,
    user_approved BOOLEAN DEFAULT FALSE,
    
    -- Audit Trail
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    sync_version INTEGER DEFAULT 1
);

-- Foreign key constraint (add after both tables exist)
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint 
        WHERE conname = 'fk_split_parent_transaction'
    ) THEN
        ALTER TABLE ynab_split_transactions 
            ADD CONSTRAINT fk_split_parent_transaction 
            FOREIGN KEY (parent_transaction_id) 
            REFERENCES ynab_transactions(id) 
            ON DELETE CASCADE;
    END IF;
END $$;

-- Indexes
CREATE INDEX IF NOT EXISTS idx_split_parent_id ON ynab_split_transactions(parent_transaction_id);
CREATE INDEX IF NOT EXISTS idx_split_payee_name ON ynab_split_transactions(payee_name);
CREATE INDEX IF NOT EXISTS idx_split_category_id ON ynab_split_transactions(category_id);

-- Table comments
COMMENT ON TABLE ynab_split_transactions IS 'Subtransactions for split transactions (normalized for data integrity)';
COMMENT ON COLUMN ynab_split_transactions.parent_transaction_id IS 'Foreign key to ynab_transactions.id with CASCADE delete';

-- ====================================================================
-- TABLE 3: sop_rules
-- ====================================================================
-- Purpose: Store agent-learned categorization rules extracted from
--          SOP file. Provides Tier 1 (highest confidence) categorization.
-- ====================================================================

CREATE TABLE IF NOT EXISTS sop_rules (
    -- Primary Key
    id SERIAL PRIMARY KEY,
    
    -- Rule Definition
    rule_type TEXT NOT NULL,  -- 'exact_match', 'pattern_match', 'split_default'
    payee_pattern TEXT NOT NULL,  -- Exact string or regex pattern
    category_group TEXT,
    category_name TEXT,
    
    -- Split Rule Support
    is_split_rule BOOLEAN DEFAULT FALSE,
    split_allocation JSONB,  -- JSON array: [{"category": "Groceries", "percentage": 70}, ...]
    
    -- Rule Metadata
    confidence_score REAL DEFAULT 1.0,  -- SOP rules always 1.0 (highest confidence)
    rule_source TEXT NOT NULL,  -- 'initial_sop', 'agent_learned', 'user_correction'
    times_used INTEGER DEFAULT 0,  -- Increments each time rule is applied
    times_correct INTEGER DEFAULT 0,  -- Increments when user approves
    
    -- Audit Trail
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    last_used_at TIMESTAMP WITH TIME ZONE
);

-- Indexes
CREATE INDEX IF NOT EXISTS idx_sop_rules_payee_pattern ON sop_rules(payee_pattern);
CREATE INDEX IF NOT EXISTS idx_sop_rules_type ON sop_rules(rule_type);
CREATE INDEX IF NOT EXISTS idx_sop_rules_confidence ON sop_rules(confidence_score DESC);

-- Constraints
ALTER TABLE sop_rules 
    DROP CONSTRAINT IF EXISTS check_rule_type;
ALTER TABLE sop_rules 
    ADD CONSTRAINT check_rule_type 
    CHECK (rule_type IN ('exact_match', 'pattern_match', 'split_default'));

ALTER TABLE sop_rules 
    DROP CONSTRAINT IF EXISTS check_sop_confidence;
ALTER TABLE sop_rules 
    ADD CONSTRAINT check_sop_confidence 
    CHECK (confidence_score >= 0.0 AND confidence_score <= 1.0);

-- Table comments
COMMENT ON TABLE sop_rules IS 'Agent-learned categorization rules (Tier 1 - highest confidence)';
COMMENT ON COLUMN sop_rules.split_allocation IS 'JSON array for split transaction percentage allocations';
COMMENT ON COLUMN sop_rules.confidence_score IS 'Always 1.0 for SOP rules (Tier 1)';

-- ====================================================================
-- TABLE 4: agent_metadata
-- ====================================================================
-- Purpose: Track agent learning performance metrics and system state
--          using flexible JSONB storage.
-- ====================================================================

CREATE TABLE IF NOT EXISTS agent_metadata (
    -- Primary Key
    id SERIAL PRIMARY KEY,
    
    -- Metadata Fields
    key TEXT UNIQUE NOT NULL,  -- 'last_sync_timestamp', 'total_transactions_analyzed', etc.
    value JSONB NOT NULL,  -- Flexible JSON storage for any metadata type
    
    -- Audit Trail
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- Indexes
CREATE UNIQUE INDEX IF NOT EXISTS idx_metadata_key ON agent_metadata(key);

-- Table comments
COMMENT ON TABLE agent_metadata IS 'Flexible key-value storage for agent learning metrics and system state';
COMMENT ON COLUMN agent_metadata.value IS 'JSONB allows flexible schema evolution without migrations';

-- ====================================================================
-- FUNCTION: find_historical_category()
-- ====================================================================
-- Purpose: Core Tier 2 pattern matching logic for historical
--          categorization. Returns category with 80%+ confidence.
-- ====================================================================

CREATE OR REPLACE FUNCTION find_historical_category(
    p_payee_name TEXT,
    p_amount BIGINT DEFAULT NULL,
    p_min_confidence REAL DEFAULT 0.80
) 
RETURNS TABLE (
    category_id TEXT,
    category_name TEXT,
    confidence REAL,
    match_count BIGINT
) 
LANGUAGE SQL
STABLE
AS $$
    -- Find exact payee matches, calculate confidence from historical data
    WITH historical_matches AS (
        SELECT 
            yt.category_id,
            yt.category_name,
            COUNT(*) as match_count,
            COUNT(*) * 1.0 / NULLIF(
                (SELECT COUNT(*) FROM ynab_transactions WHERE payee_name = p_payee_name),
                0
            ) as confidence_score
        FROM ynab_transactions yt
        WHERE 
            yt.payee_name = p_payee_name
            AND yt.category_id IS NOT NULL
            AND (p_amount IS NULL OR ABS(yt.amount - p_amount) < 100)  -- Allow $0.10 variance
        GROUP BY yt.category_id, yt.category_name
        HAVING COUNT(*) >= 3  -- Minimum 3 historical transactions
    )
    SELECT 
        hm.category_id,
        hm.category_name,
        hm.confidence_score::REAL,
        hm.match_count
    FROM historical_matches hm
    WHERE hm.confidence_score >= p_min_confidence
    ORDER BY hm.confidence_score DESC, hm.match_count DESC
    LIMIT 1;
$$;

-- Function comments
COMMENT ON FUNCTION find_historical_category(TEXT, BIGINT, REAL) IS 
    'Find category for payee with 80%+ confidence from historical patterns (Tier 2 categorization)';

-- ====================================================================
-- TRIGGER: Auto-update updated_at timestamp
-- ====================================================================

CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Apply to all tables
DROP TRIGGER IF EXISTS update_ynab_transactions_updated_at ON ynab_transactions;
CREATE TRIGGER update_ynab_transactions_updated_at
    BEFORE UPDATE ON ynab_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_ynab_split_transactions_updated_at ON ynab_split_transactions;
CREATE TRIGGER update_ynab_split_transactions_updated_at
    BEFORE UPDATE ON ynab_split_transactions
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_sop_rules_updated_at ON sop_rules;
CREATE TRIGGER update_sop_rules_updated_at
    BEFORE UPDATE ON sop_rules
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

DROP TRIGGER IF EXISTS update_agent_metadata_updated_at ON agent_metadata;
CREATE TRIGGER update_agent_metadata_updated_at
    BEFORE UPDATE ON agent_metadata
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();

-- ====================================================================
-- INITIALIZATION COMPLETE
-- ====================================================================
-- All tables, indexes, constraints, functions, and triggers created.
-- Schema is ready for YNAB Transaction Tagger application.
-- ====================================================================
