# PRD: YNAB Intelligent Transaction Tagger

**Last Updated:** 2025-11-27T04:19:51Z
**Version:** 3.5 (Two-Budget Architecture: Learning Budget + Target Budget)
**Status:** Production-Ready Specification

---

## Executive Summary

### Problem
YNAB users manually categorize every transaction. For someone with 500+ monthly transactions, this creates 30+ minutes of monthly overhead and categorization inconsistency. Additionally, split transactions (e.g., Walmart purchase with groceries + household items) require manual splitting.

### Solution
Web-based self-learning agent system that tags transactions using:
1. **Learned SOP Rules** (Tier 1): Agent-maintained SOP with explicit categorization rules
2. **Historical Patterns** (Tier 2): SQL pattern analysis (≥80% confidence from past transactions)
3. **Research + Reasoning** (Tier 3): Web search + AI analysis to identify unknown payees and suggest categories
4. **Split Transaction Support**: Multi-category allocation with percentages
5. **Two-Budget Architecture**:
   - **Learning Budget** (INIT_BUDGET_ID): One-time historical data import for pattern learning
   - **Target Budget** (TARGET_BUDGET_ID): Ongoing transaction tagging operations

### Impact
- **Time:** 30 min/month → 5 min/month (83% reduction)
- **Coverage:** 90% auto-tagged via SOP + historical (grows to 95%+ over time)
- **Accuracy:** ≥95% correct categorization
- **Control:** 100% user approval with bulk checkbox interface
- **Learning:** Agent improves with EVERY approval:
  - SOP file grows (Tier 1 explicit rules - highest confidence)
  - Persistent database grows (Tier 2 historical patterns - high confidence)
  - Research results saved to SOP (Tier 3 becomes Tier 1 next time)
  - Split patterns remembered forever

---

## Core Architecture

### Self-Learning Agent Workflow
```
┌─────────────────────────────────────────────────────────────┐
│                    YNAB Categorization Agent                │
│                                                             │
│  Input: Uncategorized transaction                          │
│  Output: Category recommendation OR split allocation       │
│                                                             │
│  3-Tier Fallback Logic:                                    │
│                                                             │
│  [1] Learned SOP Rules (Highest Priority)                  │
│       ├─ Check agent's categorization_rules.md             │
│       ├─ Pattern match: "Walmart" → split default          │
│       ├─ MATCH → Return category/split + high confidence   │
│       └─ NO MATCH → Continue to Tier 2                     │
│                                                             │
│  [2] Historical SQL Pattern (≥80%)                         │
│       ├─ Query persistent DB for payee matches             │
│       ├─ MATCH → Return category + confidence              │
│       └─ NO MATCH → Continue to Tier 3                     │
│                                                             │
│  [3] Research + Reasoning (Combined)                       │
│       ├─ WebSearch for payee name + location               │
│       ├─ Identify business type from search results        │
│       ├─ Fetch available YNAB categories                   │
│       ├─ AI analyzes search + context + categories         │
│       ├─ Update SOP with new learned rule                  │
│       └─ Return category + medium confidence               │
│                                                             │
│  Post-Processing:                                          │
│  ├─ User approves/modifies recommendation                  │
│  ├─ If modified: Update SOP with correction                │
│  └─ If split approved: Store split pattern in SOP          │
└─────────────────────────────────────────────────────────────┘
```

### Atomic TDD Hierarchy
```
Layer 1: Atoms (Single-responsibility functions)
  ├─ api_fetch.py      → fetch_transactions(), fetch_categories()
  ├─ db_init.py        → initialize_database() [one-time setup]
  ├─ db_upsert.py      → upsert_transaction() [insert or update]
  ├─ db_query.py       → get_untagged_transactions()
  ├─ historical_match  → find_historical_category() [≥80% SQL on persistent DB]
  ├─ sop_loader        → load_categorization_rules()
  ├─ sop_updater       → append_rule_to_sop()
  └─ api_update.py     → update_transaction_category(), update_split_transaction()

Layer 2: Molecules (Combine 2-3 atoms)
  ├─ data_loader       → sync_transactions() [fetch + upsert new/changed only]
  ├─ pattern_analyzer  → analyze_transaction() [query + historical_match]
  ├─ sop_manager       → read/write categorization rules
  ├─ learning_tracker  → record_agent_decision(), record_user_correction()
  └─ ynab_syncer       → sync_transactions_bulk() [batch update with splits]

Layer 3: Organisms (Feature components)
  ├─ categorization_agent → Agent instance (persistent across requests)
  ├─ recommendation_engine → get_recommendation() [orchestrates 4 tiers]
  └─ web_ui            → generate_approval_html() [checkbox table + split UI]

Layer 4: Templates (Orchestration + API)
  ├─ tagging_workflow  → generate_recommendations() [pipeline]
  └─ web_server        → Flask app with API endpoints

Layer 5: Workflow (Entry point <100 lines)
  └─ main.py           → Start Flask server + open browser
```

### Test Gates (NO MOCKS - Real Systems Only)
```
Atoms → test_atoms.py (real DB + real API + real SOP files) → PASS → Build Molecules
Molecules → test_molecules.py (real integration) → PASS → Build Organisms
Organisms → test_organisms.py (real Agent + WebSearch) → PASS → Build Templates
Templates → test_templates.py (real Flask + endpoints) → PASS → Build Workflow
Workflow → test_workflow.py (real browser E2E) → PASS → DONE
```

---

## Technical Specifications

### Stack
- **Language:** Python 3.11+ (via `uv`)
- **Database:** PostgreSQL 14+ (`staging_ynab_transactions`, `staging_ynab_split_transactions` tables)
- **Secrets:** HashiCorp Vault (`secret/ynab/credentials`, `secret/postgres/ynab_db`, `secret/claude/api_key`)
- **Agent Framework:** Claude Agent SDK (sub-agent with persistent memory)
- **Web Search:** WebSearch tool (via Claude Agent SDK or external API)
- **Web Framework:** Flask (lightweight, simple for single-page app)
- **Frontend:** Vanilla HTML/CSS/JS or React (for complex modal state management)
- **Async:** anyio runtime for agent + Flask async routes

### Frontend Implementation Requirements

**Modal State Management:**
- **CategorySelectorModal**: Reusable component with conditional "Split" button
  - Props: `transaction`, `categoryGroups`, `onSelectCategory`, `onSplit`, `hideSplitButton`
  - Shows when: User clicks category cell OR category field in split row
  - `hideSplitButton=true` when called from within split modal
  - `hideSplitButton=false` when called from main grid
  - **Keyboard support**: Escape to close, Enter to confirm selection, Arrow keys to navigate categories

- **SplitTransactionModal**: Full-screen modal for editing split allocations
  - Props: `transaction`, `categoryGroups`, `onSave`, `onClose`
  - Shows when: User clicks "[Split Transaction]" OR "Split" button in category modal
  - State: Array of split rows `{ categoryGroup, categoryName, memo, outflow, inflow }`
  - Real-time validation: Calculate remaining amount as user types
  - Each row can independently open CategorySelectorModal
  - **Keyboard support**: Escape to close, Tab through fields, Enter to approve
  - **Validation**: Prevent negative amounts, enforce YNAB memo length limit (200 chars)

**Event Flow Implementation:**
```javascript
// Main grid category click handler
onCategoryClick(transaction) {
  if (transaction.type === 'single') {
    showCategorySelector(transaction, { hideSplitButton: false });
  } else if (transaction.type === 'split') {
    showSplitModal(transaction);  // Goes directly to split modal
  }
}

// Category selector modal handlers
onCategorySelect(group, category) {
  updateTransactionCategory(currentTransaction, group, category);
  closeCategorySelector();
}

onSplitButtonClick() {
  closeCategorySelector();
  showSplitModal(currentTransaction);  // Convert to split
}

// Split modal handlers
onSplitRowCategoryClick(rowIndex) {
  showCategorySelector(splits[rowIndex], { hideSplitButton: true });
}

onSplitApprove() {
  const total = splits.reduce((sum, s) => sum + parseFloat(s.outflow || 0), 0);
  if (Math.abs(total - transaction.amount) < 0.01) {
    saveSplitTransaction(splits);
    closeSplitModal();
  } else {
    showError("Amounts must sum to transaction total");
  }
}
```

**Critical State Rules:**
- Only one modal can be open at a time (except nested category selector within split modal)
- Transaction selection (checkbox) state persists when modals open/close
- Grid updates immediately when modal closes (no refresh needed)
- Modal uses backdrop click-to-close pattern
- Validation errors shown inline, modal stays open until fixed

**Enhanced UX Features:**

1. **Keyboard Navigation & Shortcuts**
   - **Global Shortcuts**:
     - `Ctrl/Cmd + A`: Select/deselect all transactions
     - `Space`: Toggle selected transaction (when row focused)
     - `Enter`: Open category modal for focused transaction
     - `?`: Show keyboard shortcuts help overlay
   - **Modal Keyboard Support**:
     - `Escape`: Close current modal
     - `Tab`: Navigate through form fields and categories
     - `Arrow Up/Down`: Navigate category list
     - `Enter`: Confirm selection and close modal
   - **Accessibility**: Full tab order optimization, focus trapping in modals, ARIA labels

2. **Filtering & Sorting**
   - **Column Sorting**: Click column headers to sort (Date, Payee, Amount, Confidence)
   - **Filter Controls** (toolbar above grid):
     - Method filter: Dropdown with "All", "SOP", "Historical", "Research"
     - Confidence filter: Slider or range (e.g., "≥80%", "≥90%")
     - Date range: Date picker (Last 7 days, Last 30 days, Custom)
   - **Search Bar**: Real-time payee name search
   - **Filter Persistence**: Save filter state in localStorage

3. **Bulk Editing Operations**
   - **Bulk Category Assignment**:
     - Select multiple transactions → "Apply Category" button appears
     - Opens category selector → Applies to all selected
   - **Smart Bulk Actions**:
     - "Approve All High Confidence" button (≥90% confidence)
     - "Review Low Confidence Only" filter preset (<75%)
   - **Undo/Redo**:
     - In-memory action stack (undo last 10 changes before submit)
     - Show toast: "Category changed for 3 transactions. [Undo]"

4. **Transaction Status Display**
   - **YNAB Cleared Status**: Add column showing:
     - 🟢 Cleared (green dot)
     - ⚪ Uncleared (gray dot)
     - 🔒 Reconciled (lock icon)
   - Display between Date and Payee columns
   - Read-only (managed by YNAB, not this tool)

5. **Enhanced Error Handling**
   - **Toast Notifications**: Replace `alert()` with non-blocking toast system
   - **Error Boundary**: React error boundary to catch component failures
   - **Try/Catch Blocks**: Wrap all state updates and API calls
   - **User-Friendly Messages**:
     - Network errors: "Connection lost. Retrying..."
     - Validation errors: "Amount must be positive" (inline)
     - Success feedback: "23 transactions updated successfully"

6. **Configuration Constants** (replace magic numbers)
   ```javascript
   const CONFIG = {
     LOAD_TIMEOUT_MS: 1500,           // Loading simulation delay
     SPLIT_AMOUNT_THRESHOLD: 0.01,    // $0.01 tolerance for splits
     MEMO_MAX_LENGTH: 200,             // YNAB memo character limit
     UNDO_STACK_SIZE: 10,              // Max undo operations
     TOAST_DURATION_MS: 5000,          // Toast auto-dismiss time
     HIGH_CONFIDENCE_THRESHOLD: 0.90,  // For "Approve All High Confidence"
   };
   ```

### Dependencies
```python
# Existing (reuse)
from common.base_client import BaseYNABClient
from common.pg_tools import PostgresAgent
from common.db_connection import DatabaseConnection
from common.vault_client import VaultClient

# New (install)
pip install anthropic flask[async] anyio
```

### Constants
```python
# Budget IDs
INIT_BUDGET_ID = "75f63aa3-9f8f-4dcc-9350-d22535494657"     # One-time: Initialize local tagging database
TARGET_BUDGET_ID = "eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1"   # Ongoing: Tag transactions in this budget

# Configuration
HISTORICAL_CONFIDENCE_THRESHOLD = 0.80  # 80%
WEB_SERVER_PORT = 5000
WEB_SERVER_HOST = "127.0.0.1"
CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
CATEGORIZATION_SOP_PATH = "tools/ynab/transaction_tagger/categorization_rules.md"
```

---

## Database Schema

### Agent's Long-Term Memory: `ynab_transactions` (Persistent)
```sql
-- PERSISTENT TABLE - NEVER TRUNCATED
-- This is the agent's growing knowledge base
CREATE TABLE IF NOT EXISTS ynab_transactions (
    -- Core transaction data
    ynab_id TEXT PRIMARY KEY,
    date DATE NOT NULL,
    payee_name TEXT,
    category_id TEXT,  -- YNAB category UUID (NULL = untagged)
    category_group_name TEXT,  -- e.g., "Household", "Mekonen's", "Infrastructure"
    category_name TEXT,  -- e.g., "Groceries", "Personal", "Verizon"
    approved BOOLEAN DEFAULT false,
    amount BIGINT,  -- YNAB milliunits (1000 = $1.00)
    memo TEXT,

    -- Transfer detection
    transfer_account_id TEXT,  -- NOT NULL = skip tagging

    -- Categorization metadata (for learning)
    was_agent_tagged BOOLEAN DEFAULT false,  -- TRUE if agent categorized it
    agent_method TEXT,  -- 'sop_rule', 'historical', 'research_reasoning'
    agent_confidence FLOAT,
    user_corrected BOOLEAN DEFAULT false,  -- TRUE if user modified agent's suggestion

    -- Split transaction flag
    is_split BOOLEAN DEFAULT false,  -- TRUE if split into multiple categories

    -- Timestamps (for sync tracking)
    first_seen TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    synced_with_ynab BOOLEAN DEFAULT false,

    -- Indexes for fast pattern matching
    CONSTRAINT unique_ynab_id UNIQUE (ynab_id)
);

-- Indexes for Tier 1 SQL pattern matching
CREATE INDEX IF NOT EXISTS idx_payee_category ON ynab_transactions(payee_name, category_id) WHERE approved = true;
CREATE INDEX IF NOT EXISTS idx_date ON ynab_transactions(date DESC);
CREATE INDEX IF NOT EXISTS idx_approved ON ynab_transactions(approved) WHERE approved = true;
```

### Split Transactions: `ynab_split_transactions` (Persistent)
```sql
-- PERSISTENT TABLE - NEVER TRUNCATED
-- Stores split allocations for agent learning
CREATE TABLE IF NOT EXISTS ynab_split_transactions (
    id SERIAL PRIMARY KEY,
    ynab_transaction_id TEXT NOT NULL REFERENCES ynab_transactions(ynab_id) ON DELETE CASCADE,
    category_id TEXT NOT NULL,  -- YNAB category UUID
    category_group_name TEXT NOT NULL,  -- e.g., "Household"
    category_name TEXT NOT NULL,  -- e.g., "Groceries"
    amount BIGINT NOT NULL,  -- YNAB milliunits (must sum to parent transaction amount)
    percentage FLOAT,  -- Optional: percentage of total (must sum to 100%)
    memo TEXT,  -- Optional: memo for this split
    created_at TIMESTAMP DEFAULT NOW(),

    CONSTRAINT valid_percentage CHECK (percentage >= 0 AND percentage <= 100)
);

CREATE INDEX IF NOT EXISTS idx_split_txn_id ON ynab_split_transactions(ynab_transaction_id);
CREATE INDEX IF NOT EXISTS idx_split_payee_category ON ynab_split_transactions(ynab_transaction_id, category_id);
```

### SOP Rules Table: `sop_rules` (Persistent)
```sql
-- PERSISTENT TABLE - Stores learned categorization rules
-- Complements the markdown file with structured queryable data
CREATE TABLE IF NOT EXISTS sop_rules (
    id SERIAL PRIMARY KEY,
    payee_pattern TEXT NOT NULL UNIQUE,  -- Pattern to match (exact, prefix, or regex)
    pattern_type TEXT NOT NULL CHECK (pattern_type IN ('exact', 'prefix', 'contains', 'regex')),

    -- Single category rule
    category_id TEXT,  -- NULL if split transaction
    category_group_name TEXT,
    category_name TEXT,

    -- Split transaction rule
    is_split BOOLEAN DEFAULT false,
    split_allocations JSONB,  -- [{category_id, category_name, percentage}, ...]

    -- Metadata
    confidence FLOAT DEFAULT 1.0,
    source TEXT,  -- 'user_correction', 'web_research', 'historical_pattern'
    reasoning TEXT,
    learned_date TIMESTAMP DEFAULT NOW(),
    last_used TIMESTAMP,
    usage_count INTEGER DEFAULT 0,

    CONSTRAINT has_category_or_split CHECK (
        (category_id IS NOT NULL AND is_split = false) OR
        (split_allocations IS NOT NULL AND is_split = true)
    )
);

CREATE INDEX IF NOT EXISTS idx_sop_payee_pattern ON sop_rules(payee_pattern);
CREATE INDEX IF NOT EXISTS idx_sop_pattern_type ON sop_rules(pattern_type);

-- Example: Query historical patterns for a payee
-- Used by Tier 2 (Historical SQL Pattern)
CREATE OR REPLACE FUNCTION find_historical_category(p_payee_name TEXT)
RETURNS TABLE(
    category_id TEXT,
    category_name TEXT,
    confidence FLOAT,
    match_count BIGINT,
    total_count BIGINT
) AS $$
BEGIN
    RETURN QUERY
    SELECT
        t.category_id,
        t.category_name,
        (COUNT(*)::FLOAT / (SELECT COUNT(*) FROM ynab_transactions WHERE payee_name ILIKE p_payee_name AND approved = true)) AS confidence,
        COUNT(*) AS match_count,
        (SELECT COUNT(*) FROM ynab_transactions WHERE payee_name ILIKE p_payee_name AND approved = true) AS total_count
    FROM ynab_transactions t
    WHERE t.payee_name ILIKE p_payee_name
      AND t.approved = true
      AND t.category_id IS NOT NULL
    GROUP BY t.category_id, t.category_name
    HAVING COUNT(*)::FLOAT / (SELECT COUNT(*) FROM ynab_transactions WHERE payee_name ILIKE p_payee_name AND approved = true) >= 0.80
    ORDER BY confidence DESC
    LIMIT 1;
END;
$$ LANGUAGE plpgsql;
```

### YNAB API Category Structure

YNAB organizes categories hierarchically:

```json
{
  "category_groups": [
    {
      "id": "group-uuid-1",
      "name": "Household",
      "categories": [
        {
          "id": "cat-uuid-1",
          "name": "Groceries",
          "category_group_id": "group-uuid-1"
        },
        {
          "id": "cat-uuid-2",
          "name": "Rent",
          "category_group_id": "group-uuid-1"
        }
      ]
    },
    {
      "id": "group-uuid-2",
      "name": "Mekonen's",
      "categories": [
        {
          "id": "cat-uuid-3",
          "name": "Personal",
          "category_group_id": "group-uuid-2"
        }
      ]
    }
  ]
}
```

**Display Format:** `{category_group_name}: {category_name}`
- Examples: "Household: Groceries", "Mekonen's: Personal", "Infrastructure: Verizon"

**Agent Recommendations:**
- Agent must return `category_id` (UUID) for YNAB API
- Store both `category_group_name` and `category_name` in DB for learning
- Display format in UI: `{group}: {category}`

### Database Initialization & Migration Strategy

#### First-Time Setup (One-Time Only)
```sql
-- Create persistent transaction table
CREATE TABLE IF NOT EXISTS ynab_transactions (
    ynab_id TEXT PRIMARY KEY,
    date DATE NOT NULL,
    payee_name TEXT,
    category_id TEXT,  -- YNAB category UUID
    category_group_name TEXT,  -- e.g., "Household", "Mekonen's"
    category_name TEXT,  -- e.g., "Groceries", "Personal"
    approved BOOLEAN DEFAULT false,
    amount BIGINT,
    memo TEXT,
    transfer_account_id TEXT,
    was_agent_tagged BOOLEAN DEFAULT false,
    agent_method TEXT,
    agent_confidence FLOAT,
    user_corrected BOOLEAN DEFAULT false,
    is_split BOOLEAN DEFAULT false,
    first_seen TIMESTAMP DEFAULT NOW(),
    last_updated TIMESTAMP DEFAULT NOW(),
    synced_with_ynab BOOLEAN DEFAULT false
);

-- Create persistent split transactions table
CREATE TABLE IF NOT EXISTS ynab_split_transactions (
    id SERIAL PRIMARY KEY,
    ynab_transaction_id TEXT NOT NULL REFERENCES ynab_transactions(ynab_id) ON DELETE CASCADE,
    category_id TEXT NOT NULL,  -- YNAB category UUID
    category_group_name TEXT NOT NULL,  -- e.g., "Household"
    category_name TEXT NOT NULL,  -- e.g., "Groceries"
    amount BIGINT NOT NULL,
    percentage FLOAT,
    memo TEXT,
    created_at TIMESTAMP DEFAULT NOW(),
    CONSTRAINT valid_percentage CHECK (percentage >= 0 AND percentage <= 100)
);

-- Create indexes for fast pattern matching
CREATE INDEX IF NOT EXISTS idx_payee_category ON ynab_transactions(payee_name, category_id) WHERE approved = true;
CREATE INDEX IF NOT EXISTS idx_date ON ynab_transactions(date DESC);
CREATE INDEX IF NOT EXISTS idx_approved ON ynab_transactions(approved) WHERE approved = true;
CREATE INDEX IF NOT EXISTS idx_split_txn_id ON ynab_split_transactions(ynab_transaction_id);

-- Initialization flag (check if DB has been initialized)
CREATE TABLE IF NOT EXISTS agent_metadata (
    key TEXT PRIMARY KEY,
    value TEXT,
    updated_at TIMESTAMP DEFAULT NOW()
);

INSERT INTO agent_metadata (key, value)
VALUES ('db_initialized', 'true'), ('first_init_date', NOW()::TEXT)
ON CONFLICT (key) DO NOTHING;
```

#### Incremental Updates (Every Run)
```sql
-- UPSERT pattern: Insert new transactions, update existing
INSERT INTO ynab_transactions (
    ynab_id, date, payee_name, category_id, approved, amount, memo,
    transfer_account_id, last_updated
)
VALUES ($1, $2, $3, $4, $5, $6, $7, $8, NOW())
ON CONFLICT (ynab_id)
DO UPDATE SET
    category_id = EXCLUDED.category_id,
    approved = EXCLUDED.approved,
    last_updated = NOW(),
    synced_with_ynab = CASE
        WHEN EXCLUDED.category_id IS NOT NULL THEN true
        ELSE ynab_transactions.synced_with_ynab
    END;
```

---

## Agent Design

### Agent Definition: `agents/ynab-categorization-agent.md`
```markdown
# YNAB Categorization Agent

## Role
Financial transaction categorization specialist that learns and improves categorization rules over time.

## Capabilities
- Analyze YNAB transactions and suggest categories
- Maintain categorization rules SOP (`categorization_rules.md`)
- Research unknown payees via web search
- Suggest split transactions for multi-category purchases
- Learn from user corrections and update rules

## Tools Available
- **WebSearch**: Search internet for payee information
- **Read**: Read categorization_rules.md SOP
- **Write**: Update categorization_rules.md with new rules
- **Grep**: Search for existing patterns in SOP

## Decision Logic (3 Tiers)

### Tier 1: Learned SOP Rules (Highest Priority)
- Read `categorization_rules.md`
- Search for payee patterns:
  - Exact match: "Amazon.com" → "Shopping: Online"
  - Partial match: "Walmart #" → Split [Groceries 70%, Household 30%]
  - Regex match: "Shell Gas.*" → "Auto: Fuel"
- **Why first?** User-validated explicit rules are most reliable
- If match found → Return category/split + high confidence (0.90-0.95)
- Else → Continue to Tier 2

### Tier 2: Historical Pattern (Deterministic)
- Delegate to SQL query: `find_historical_category(payee_name)`
- Query persistent DB for past transactions with same payee
- If ≥80% of past transactions use same category → Return that category
- Return category + high confidence (0.80-0.90)
- Else → Continue to Tier 3

### Tier 3: Research + Reasoning (Combined)
- Execute WebSearch: "{payee_name} business type location"
- Analyze search results:
  - Extract: Business type, category hint
  - Example: "Shell Gas 12345" → Search → "Gas station" → "Auto: Fuel"
- Fetch list of available YNAB categories
- AI analyzes: search results + transaction context (amount, memo, date) + available categories
- Select BEST MATCH from available categories ONLY
- **CRITICAL**: Never invent categories - must choose from list
- Update SOP with new learned rule for future
- Return category + medium confidence (0.60-0.75)

## Learning Mechanism

### When User Approves Recommendation
- No action needed (validates existing rule)

### When User Modifies Recommendation
- Read categorization_rules.md
- Append new rule:
  ```
  ## Payee: {payee_name}
  - Category: {user_selected_category}
  - Reasoning: User correction from {old_category} on {date}
  - Confidence: High (user-validated)
  ```
- Save updated SOP

### When User Approves Split Transaction
- Store split pattern in SOP:
  ```
  ## Payee: Walmart #1234
  - Type: Split Transaction
  - Default Split:
    * Groceries: 60%
    * Household: 25%
    * Personal Care: 15%
  - Reasoning: Typical Walmart purchase pattern
  ```

## Output Format

### Single Category Recommendation (from SOP rule)
```json
{
  "type": "single",
  "category_id": "abc-123",
  "category_name": "Groceries",
  "confidence": 0.95,
  "method": "sop_rule",
  "reasoning": "Matched SOP rule: Whole Foods → Groceries"
}
```

### Single Category Recommendation (from research + reasoning)
```json
{
  "type": "single",
  "category_id": "def-456",
  "category_name": "Auto: Fuel",
  "confidence": 0.70,
  "method": "research_reasoning",
  "reasoning": "WebSearch identified 'Joe's Gas Station' as fuel provider. Matched to Auto: Fuel category.",
  "should_update_sop": true,
  "sop_update_content": "## Payee: Joe's Gas Station\n- Category: Auto: Fuel\n- Confidence: High\n- Source: Web research + AI reasoning"
}
```

### Split Transaction Recommendation
```json
{
  "type": "split",
  "splits": [
    {
      "category_id": "abc-123",
      "category_name": "Groceries",
      "percentage": 60,
      "amount": 72000
    },
    {
      "category_id": "def-456",
      "category_name": "Household",
      "percentage": 40,
      "amount": 48000
    }
  ],
  "confidence": 0.90,
  "method": "sop_rule",
  "reasoning": "Walmart split pattern from SOP rule"
}
```
```

### Agent Invocation: `organisms/categorization_agent.py`
```python
"""
YNAB Categorization Agent
Self-learning transaction categorization with 4-tier fallback logic
"""

import anthropic
import json
from typing import Dict, List
from pathlib import Path

# Get API key from Vault
from common.vault_client import VaultClient

CLAUDE_MODEL = "claude-sonnet-4-5-20250929"
SOP_PATH = Path("tools/ynab/transaction_tagger/categorization_rules.md")
AGENT_PROMPT_PATH = Path("agents/ynab-categorization-agent.md")


class CategorizationAgent:
    """
    Persistent agent for transaction categorization with self-learning.
    """

    def __init__(self):
        vault = VaultClient()
        api_key = vault.get_secret('claude/api_key')
        self.client = anthropic.Anthropic(api_key=api_key)
        self.conversation_history = []

        # Load agent definition
        with open(AGENT_PROMPT_PATH) as f:
            self.system_prompt = f.read()

    async def categorize_transaction(
        self,
        txn: Dict,
        available_categories: List[Dict],
        sop_match: Dict = None,
        historical_match: Dict = None
    ) -> Dict:
        """
        Categorize a transaction using 3-tier fallback logic.

        Args:
            txn: Transaction dict with payee_name, amount, memo, date
            available_categories: List of YNAB category dicts [{id, name}, ...]
            sop_match: Optional pre-computed SOP rule match from Tier 1
            historical_match: Optional pre-computed historical match from Tier 2

        Returns:
            Recommendation dict with category OR split allocation
        """

        # Tier 1: SOP Rules (already computed outside agent)
        if sop_match:
            return sop_match

        # Tier 2: Historical Pattern (already computed outside agent)
        if historical_match:
            return historical_match

        # Build context for agent
        category_list = "\n".join([f"- {cat['name']} (ID: {cat['id']})" for cat in available_categories])

        # Read current SOP
        if SOP_PATH.exists():
            with open(SOP_PATH) as f:
                sop_content = f.read()
        else:
            sop_content = "# Categorization Rules\n\n_No rules learned yet._"

        # Agent prompt
        user_message = f"""
Categorize this YNAB transaction:

**Transaction:**
- Payee: {txn.get('payee_name', 'Unknown')}
- Amount: ${txn.get('amount', 0) / 1000.0:.2f}
- Memo: {txn.get('memo') or 'N/A'}
- Date: {txn.get('date', 'Unknown')}

**Available YNAB Categories:**
{category_list}

**Current Categorization Rules (SOP):**
{sop_content}

**Instructions:**
This transaction has NO SOP rule match and NO historical pattern (those were checked first).
Your job is Tier 3: Research + Reasoning.

1. Use WebSearch tool to research this payee (business type, location, what they sell)
2. Analyze search results to understand the business
3. Based on search results + transaction context (amount, memo), select BEST MATCH from available categories
4. **CRITICAL**: Only suggest categories from the available list above - NEVER invent categories
5. Determine if this should be a split transaction (e.g., Walmart, Target, Costco typically need splits)
6. Update SOP with your learned rule so future transactions match in Tier 1

Respond in JSON format:
{{
  "type": "single" | "split",
  "category_id": "..." (if single),
  "category_name": "..." (if single),
  "splits": [...] (if split - see agent definition),
  "confidence": 0.0-1.0,
  "method": "research_reasoning",
  "reasoning": "...",
  "should_update_sop": true,
  "sop_update_content": "..." (always update SOP with learned rule)
}}
"""

        # Call Claude with agent system prompt
        message = self.client.messages.create(
            model=CLAUDE_MODEL,
            max_tokens=2048,
            system=self.system_prompt,
            messages=[
                *self.conversation_history,
                {
                    "role": "user",
                    "content": user_message
                }
            ]
        )

        # Parse response
        try:
            response_text = message.content[0].text
            result = json.loads(response_text)

            # Update SOP if agent suggests
            if result.get('should_update_sop'):
                self._update_sop(result['sop_update_content'])

            # Store conversation for context
            self.conversation_history.append({
                "role": "user",
                "content": user_message
            })
            self.conversation_history.append({
                "role": "assistant",
                "content": response_text
            })

            # Keep conversation history manageable (last 10 exchanges)
            if len(self.conversation_history) > 20:
                self.conversation_history = self.conversation_history[-20:]

            return self._format_recommendation(result, txn)

        except (json.JSONDecodeError, KeyError) as e:
            # Fallback if parsing fails
            return {
                'type': 'single',
                'category_id': None,
                'confidence': 0.0,
                'method': 'error',
                'reasoning': f'Agent parsing failed: {str(e)}'
            }

    def _update_sop(self, content: str):
        """Append learned rule to SOP."""
        with open(SOP_PATH, 'a') as f:
            f.write(f"\n\n{content}")

    def _format_recommendation(self, agent_result: Dict, txn: Dict) -> Dict:
        """Format agent result into standardized recommendation."""
        if agent_result['type'] == 'single':
            return {
                'type': 'single',
                'recommended_category_id': agent_result['category_id'],
                'recommended_category_name': agent_result['category_name'],
                'confidence': agent_result['confidence'],
                'method': agent_result['method'],
                'reasoning': agent_result['reasoning']
            }
        else:  # split
            # Calculate amounts from percentages
            total_amount = txn.get('amount', 0)
            for split in agent_result['splits']:
                split['amount'] = int(total_amount * split['percentage'] / 100.0)

            return {
                'type': 'split',
                'splits': agent_result['splits'],
                'confidence': agent_result['confidence'],
                'method': agent_result['method'],
                'reasoning': agent_result['reasoning']
            }

    def learn_from_correction(self, txn: Dict, user_category: Dict, original_recommendation: Dict):
        """
        Update SOP when user corrects a recommendation.
        """
        correction_rule = f"""
---
**Learned from User Correction - {txn['date']}**

## Payee: {txn['payee_name']}
- **Correct Category**: {user_category['name']} (ID: {user_category['id']})
- **Agent Suggested**: {original_recommendation.get('category_name', 'Unknown')}
- **Reasoning**: User correction - agent was wrong
- **Confidence**: High (user-validated)
"""
        self._update_sop(correction_rule)

    def learn_from_split_approval(self, txn: Dict, split_allocation: List[Dict]):
        """
        Store split pattern when user approves split transaction.
        """
        split_rule = f"""
---
**Split Transaction Pattern - {txn['date']}**

## Payee: {txn['payee_name']}
- **Type**: Split Transaction
- **Default Allocation**:
"""
        for split in split_allocation:
            split_rule += f"  * {split['category_name']}: {split['percentage']}% (${split['amount']/1000.0:.2f})\n"

        split_rule += "- **Reasoning**: User-defined split pattern\n"
        self._update_sop(split_rule)
```

---

## User Flow

### Command
```bash
python tools/ynab/transaction_tagger/main.py
```

### Web Interface Flow
```
1. User runs script → Flask server starts at http://127.0.0.1:5000
2. Browser opens automatically to web interface
3. User sees landing page with "Load & Tag Transactions" button
4. User clicks button:
   a. Frontend: Shows loading spinner
   b. Backend: GET /api/load-and-tag
      - Check if DB initialized (agent_metadata table)
      - If first run: Initialize DB, fetch ALL transactions from YNAB
      - If subsequent run: Fetch only NEW transactions since last sync
      - UPSERT transactions into persistent ynab_transactions table
      - For each untagged transaction:
        * Try Tier 1: Check SOP rules (categorization_rules.md)
        * If no match: Try Tier 2: SQL historical (≥80% from persistent DB)
        * If no match: Invoke categorization agent (Tier 3: Research + Reasoning)
        * Agent does WebSearch → Analyzes results → Suggests category → Updates SOP
        * Agent may suggest split transaction
      - Return recommendations (single + splits) as JSON
   c. Frontend: Displays table with checkboxes

5. User reviews table:
   - Single category rows: [✓] Date | Payee | Amount | → | Recommended Cat | Confidence
   - Split transaction rows: [✓] Date | Payee | Amount | → | [Split] button
   - Clicking [Split] opens modal with category allocation table
   - User can:
     * Check/uncheck rows (default: all checked)
     * Edit category via dropdown
     * Edit split allocations (percentages/amounts)
     * Add/remove split categories

6. User clicks "Submit Approved Changes" button:
   a. Frontend: POST /api/submit with:
      - Single transactions: {ynab_id, category_id, was_modified}
      - Split transactions: {ynab_id, splits: [{category_id, amount}, ...], was_modified}
   b. Backend:
      - Batch update YNAB API (single categories)
      - Batch update YNAB API (split transactions - different endpoint)
      - **Update persistent DB**:
        * Set approved=true, category_id=user_selection
        * Set was_agent_tagged=true, agent_method, agent_confidence
        * Set user_corrected=true (if was_modified)
        * Insert splits into ynab_split_transactions
        * Update last_updated timestamp
      - If user modified: Agent learns from correction (updates SOP)
      - If split approved: Agent stores split pattern (updates SOP + DB)
   c. Frontend: Shows success message with count
   d. **Database now contains approved transaction for future Tier 1 matching**

7. User can reload page to verify completion (should show 0 untagged)
```

### Web UI Layout - YNAB-Style Grid
```
┌────────────────────────────────────────────────────────────────────────┐
│  YNAB Transaction Tagger                    23 untagged | 23 selected  │
│                                                          [Submit (23)]  │
├───┬───┬────────────┬──────────────┬─────────────────┬────────┬────┬───┤
│ ☑ │   │ Date       │ Payee        │ Category        │ Method │ %  │ $ │
├───┼───┼────────────┼──────────────┼─────────────────┼────────┼────┼───┤
│ ✓ │   │ 11/22/2025 │ Whole Foods  │ Household:      │ Hist   │ 85%│127│
│   │   │            │              │ Groceries       │        │    │   │
├───┼───┼────────────┼──────────────┼─────────────────┼────────┼────┼───┤
│ ✓ │ ▶ │ 11/21/2025 │ Walmart      │ [Split Trans]   │ SOP    │ 90%│ 86│
│   │   │            │              │                 │        │    │   │
├───┼───┼────────────┼──────────────┼─────────────────┼────────┼────┼───┤
│ ✓ │   │ 11/20/2025 │ Shell Gas    │ Transportation: │ Hist   │ 92%│ 45│
│   │   │            │              │ Fuel            │        │    │   │
└───┴───┴────────────┴──────────────┴─────────────────┴────────┴────┴───┘
```

### Modal Interactions - UX Requirements

#### **Category Selection Modal**
Triggered when user clicks on a category cell for a **single transaction**.

```
┌─────────────────────────────────────┐
│ Selected                            │
│ ✓ Groceries (Household)             │
├─────────────────────────────────────┤
│ HOUSEHOLD                           │
│   Groceries                      ✓  │
│   Household Items                   │
│   Rent                              │
│                                     │
│ MEKONEN'S                           │
│   Personal                          │
│   Clothing                          │
│                                     │
│ TRANSPORTATION                      │
│   Fuel                              │
│   Car Maintenance                   │
├─────────────────────────────────────┤
│ [Payment/Transfer]  [Split]         │
└─────────────────────────────────────┘
```

**Behavior:**
- Click category name → Selects category, closes modal, updates transaction
- Click "Split" → Closes category modal, opens split modal, converts transaction to split
- Click "Payment/Transfer" → Closes modal (no action)

#### **Split Transaction Modal**
Triggered when:
1. User clicks "[Split Transaction]" in category column for split transactions
2. User clicks "Split" button in category selection modal

```
┌──────────────────────────────────────────────────────────────────┐
│ Split Transaction                                                │
│ Walmart #1234 - $85.99                                          │
├──────────────────────────────────────────────────────────────────┤
│ Payee         │ Category              │ Memo    │ Outflow │ Inf  │
├───────────────┼───────────────────────┼─────────┼─────────┼──────┤
│ payee         │ Household: Groceries  │         │  51.59  │      │
├───────────────┼───────────────────────┼─────────┼─────────┼──────┤
│ payee         │ Household: Items      │         │  25.80  │      │
├───────────────┼───────────────────────┼─────────┼─────────┼──────┤
│ payee         │ Mekonen's: Personal   │         │   8.60  │      │
├───────────────┼───────────────────────┼─────────┼─────────┼──────┤
│ + Add another split                                              │
│                                                                  │
│ Amount remaining to assign:           $0.00        $0.00        │
├──────────────────────────────────────────────────────────────────┤
│                                        [Cancel]  [Approve]       │
└──────────────────────────────────────────────────────────────────┘
```

**Behavior:**
- Click category field in any row → Opens category selector modal (without "Split" button)
- Select category in modal → Updates that row's category, closes modal
- Type in outflow field → Updates amount, recalculates remaining
- Click "+" → Adds new split row
- Click "×" on row → Removes split row (minimum 1 row required)
- Click "Approve" → Validates amounts sum to total, saves split, closes modal
- Click "Cancel" → Discards changes, closes modal

**Validation:**
- Must have at least 1 split row
- Outflow amounts must sum to transaction total ($0.00 remaining)
- Shows red text if amounts don't sum correctly
- "Approve" button disabled until validation passes

### Key UX Flows

#### **Flow 1: Edit Single Transaction Category**
1. User clicks category cell (e.g., "Household: Groceries")
2. Category selector modal opens
3. User selects new category from list
4. Modal closes, category updates in grid
5. Transaction remains selected (checkbox stays checked)

#### **Flow 2: Convert Single Transaction to Split**
1. User clicks category cell on single transaction
2. Category selector modal opens
3. User clicks "Split" button
4. Category modal closes, split modal opens
5. Split modal pre-populated with 2 empty rows
6. User selects categories and enters amounts
7. User clicks "Approve"
8. Split modal closes, transaction shows "[Split Transaction]" in grid

#### **Flow 3: Edit Existing Split Transaction**
1. User clicks "[Split Transaction]" in category column
2. Split modal opens with existing split allocations populated
3. User clicks category field on a split row
4. Category selector modal opens (no "Split" button shown)
5. User selects category
6. Category modal closes, split row category updates
7. User modifies amounts, adds/removes rows as needed
8. User clicks "Approve"
9. Validation runs: amounts must sum to transaction total
10. If valid: Modal closes, splits saved
11. If invalid: Red error shown, modal stays open

#### **Flow 4: Expand/Collapse Split Details in Grid**
1. User clicks arrow (▶) next to split transaction
2. Split details expand inline below transaction row
3. Shows all categories with percentages and amounts
4. User clicks arrow (▼) to collapse
5. Split details hide

**CRITICAL UX Rules:**
- Single transaction category click → Category selector modal
- Split transaction category click → Split modal (NOT category selector)
- Within split modal, category field click → Category selector (no split button)
- Category selector "Split" button ONLY shows for single transactions
- Split modal validates amounts before allowing approval
- All modals use click-outside-to-close pattern

---

## API Specifications

### Endpoints

#### GET `/` - Landing Page
**Response:** HTML page with "Load & Tag" button

#### GET `/api/load-and-tag` - Load & Generate Recommendations
**Purpose:** Fetch YNAB transactions, run agent categorization, return recommendations

**Two-Budget Strategy:**
- **INIT_BUDGET_ID** (75f63aa3-9f8f-4dcc-9350-d22535494657): Used ONE-TIME ONLY to populate local database with historical transactions for learning patterns
- **TARGET_BUDGET_ID** (eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1): Used for all ongoing tagging operations

**Process:**
1. Check if DB initialized (`SELECT value FROM agent_metadata WHERE key='db_initialized'`)
2. If first run (initialization):
   - Initialize tables (ynab_transactions, ynab_split_transactions, agent_metadata)
   - Fetch ALL transactions from YNAB API using **INIT_BUDGET_ID** (full history for learning)
   - Insert all into ynab_transactions (builds historical pattern database)
   - Mark as db_initialized with timestamp
   - **Note:** This populates the agent's learning database with categorized transactions
3. If subsequent run (ongoing operations):
   - Use **TARGET_BUDGET_ID** for all operations
   - Fetch only NEW transactions since last_updated (YNAB API: since_date parameter)
   - UPSERT into ynab_transactions (update if exists, insert if new)
4. Query untagged transactions (WHERE category_id IS NULL AND transfer_account_id IS NULL)
5. For each untagged:
   - Try Tier 1: Check SOP rules (read categorization_rules.md, match payee patterns)
   - If no match: Try Tier 2: SQL historical pattern (≥80% from persistent DB populated from INIT_BUDGET_ID)
   - If no match: Invoke categorization agent (Tier 3: Research + Reasoning)
   - Agent does WebSearch → Analyzes → Suggests category → Updates SOP
   - Agent may return split transaction
6. Return JSON array of recommendations (singles + splits)

**Response:**
```json
{
  "status": "success",
  "total_transactions": 487,
  "untagged_count": 23,
  "recommendations": [
    {
      "ynab_id": "abc123",
      "type": "single",
      "date": "2025-11-22",
      "payee_name": "Whole Foods",
      "amount": 127430,
      "recommended_category_id": "groceries-cat-id",
      "recommended_category_name": "Groceries",
      "confidence": 0.85,
      "method": "historical",
      "reasoning": "85% of 50 previous transactions categorized as Groceries"
    },
    {
      "ynab_id": "def456",
      "type": "split",
      "date": "2025-11-21",
      "payee_name": "Walmart #1234",
      "amount": 85990,
      "splits": [
        {
          "category_id": "groceries-cat-id",
          "category_name": "Groceries",
          "percentage": 60,
          "amount": 51594
        },
        {
          "category_id": "household-cat-id",
          "category_name": "Household",
          "percentage": 30,
          "amount": 25797
        },
        {
          "category_id": "personal-cat-id",
          "category_name": "Personal Care",
          "percentage": 10,
          "amount": 8599
        }
      ],
      "confidence": 0.90,
      "method": "sop_rule",
      "reasoning": "Walmart split pattern from SOP rule #18"
    }
  ],
  "available_categories": [
    {"id": "groceries-cat-id", "name": "Groceries"},
    {"id": "dining-cat-id", "name": "Dining Out"},
    ...
  ]
}
```

#### POST `/api/submit` - Submit Approved Changes
**Purpose:** Batch update YNAB for checked transactions (single + splits)

**Request:**
```json
{
  "approved_transactions": [
    {
      "ynab_id": "abc123",
      "type": "single",
      "category_id": "groceries-cat-id",
      "was_modified": false
    },
    {
      "ynab_id": "def456",
      "type": "split",
      "splits": [
        {"category_id": "groceries-cat-id", "amount": 51594},
        {"category_id": "household-cat-id", "amount": 25797},
        {"category_id": "personal-cat-id", "amount": 8599}
      ],
      "was_modified": false
    },
    {
      "ynab_id": "ghi789",
      "type": "single",
      "category_id": "dining-cat-id",
      "was_modified": true,
      "original_category_id": "groceries-cat-id"
    }
  ]
}
```

**Process:**
1. For each transaction:
   - If single: PUT `/budgets/{id}/transactions/{ynab_id}` with category_id
   - If split: PUT `/budgets/{id}/transactions/{ynab_id}` with subtransactions array
2. **Update persistent DB** (CRITICAL - this is how agent learns):
   ```sql
   UPDATE ynab_transactions
   SET
       category_id = $category_id,
       approved = true,
       was_agent_tagged = true,
       agent_method = $method,
       agent_confidence = $confidence,
       user_corrected = $was_modified,
       synced_with_ynab = true,
       last_updated = NOW()
   WHERE ynab_id = $ynab_id;
   ```
3. If split: Insert into ynab_split_transactions
4. If was_modified: Invoke agent.learn_from_correction() (updates SOP)
5. If split approved: Invoke agent.learn_from_split_approval() (updates SOP)
6. Return success/error counts
7. **Database now has this approved transaction for future Tier 1 SQL matching**

**Response:**
```json
{
  "status": "success",
  "synced_count": 21,
  "split_count": 3,
  "error_count": 0,
  "learned_corrections": 1,
  "errors": []
}
```

---

## Categorization SOP Structure

### `categorization_rules.md` (Self-Learning File)
```markdown
# YNAB Categorization Rules

**Last Updated:** 2025-11-23T00:00:00Z
**Agent Version:** 3.0

This file is automatically maintained by the YNAB Categorization Agent.
Rules are learned from user corrections and web research.

---

## Core Patterns

### Gas Stations
- **Pattern**: Contains "Shell", "Chevron", "Exxon", "Mobil", "76"
- **Category**: Auto: Fuel
- **Confidence**: High
- **Source**: Web research + user validation

### Grocery Stores
- **Pattern**: "Whole Foods", "Safeway", "Trader Joe's", "Sprouts"
- **Category**: Groceries
- **Confidence**: High
- **Source**: Historical patterns

### Restaurants
- **Pattern**: "McDonald's", "Chipotle", "Subway", contains "Restaurant"
- **Category**: Dining Out
- **Confidence**: High
- **Source**: Web research

---

## Split Transaction Patterns

### Walmart
- **Pattern**: Starts with "Walmart #" or "WALMART"
- **Type**: Split Transaction
- **Default Allocation**:
  * Groceries: 60%
  * Household: 25%
  * Personal Care: 15%
- **Confidence**: Medium-High
- **Source**: User-defined pattern (learned 2025-11-15)
- **Note**: User can adjust percentages

### Target
- **Pattern**: Starts with "Target #" or "TARGET"
- **Type**: Split Transaction
- **Default Allocation**:
  * Groceries: 40%
  * Household: 35%
  * Clothing: 25%
- **Confidence**: Medium
- **Source**: Agent inference from business type

### Costco
- **Pattern**: "COSTCO" or "Costco Wholesale"
- **Type**: Split Transaction
- **Default Allocation**:
  * Groceries: 70%
  * Household: 20%
  * Gas: 10%
- **Confidence**: Medium
- **Source**: Typical Costco purchase pattern

---

## Learned from User Corrections

### Starbucks
- **Payee**: Starbucks #12345
- **Correct Category**: Coffee Shops (ID: coffee-cat-123)
- **Agent Initially Suggested**: Dining Out
- **Reasoning**: User correction - Starbucks should be Coffee Shops
- **Confidence**: High (user-validated)
- **Date Learned**: 2025-11-20

### Amazon.com
- **Payee**: AMZN Mktp US
- **Correct Category**: Shopping: Online (ID: online-shop-456)
- **Agent Initially Suggested**: General Merchandise
- **Reasoning**: User correction - Amazon purchases go to Online Shopping
- **Confidence**: High (user-validated)
- **Date Learned**: 2025-11-18

---

## Web Research Results

### Unknown Payee: "Joe's Diner"
- **Business Type**: Restaurant (from Google search)
- **Category**: Dining Out
- **Reasoning**: Web search confirmed local restaurant
- **Confidence**: Medium (web-sourced)
- **Date Added**: 2025-11-22

---

_End of Categorization Rules_
```

---

## Implementation Checklist

### Preparation
- [ ] `pip install anthropic flask[async] anyio`
- [ ] Store Claude API key in Vault: `vault kv put secret/claude/api_key value=<your-key>`
- [ ] Store YNAB API key in Vault: `vault kv put secret/ynab/credentials api_key=<your-key>`
- [ ] Store DB connection in Vault: `vault kv put secret/postgres/ynab_db connection_string=<postgres-url>`
- [ ] Create agent definition: `agents/ynab-categorization-agent.md`
- [ ] Create empty SOP: `tools/ynab/transaction_tagger/categorization_rules.md`
- [ ] **Initialize persistent DB** (ONE-TIME ONLY):
  ```bash
  psql $DB_CONNECTION_STRING -f tools/ynab/transaction_tagger/sql/init_persistent_db.sql
  ```
- [ ] Verify Vault access: `vault kv get secret/ynab/credentials`
- [ ] **Two-Budget Setup:**
  - **INIT_BUDGET_ID** (75f63aa3-9f8f-4dcc-9350-d22535494657): First run fetches ALL historical transactions from this budget for learning (1-2 minutes)
  - **TARGET_BUDGET_ID** (eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1): All subsequent runs tag transactions in this budget

### Build Sequence (with gates)
```
Layer 1: Atoms (9 files)
  → Create sql/init_persistent_db.sql (DB schema)
  → Create atoms/{api_fetch, db_init, db_upsert, db_query, historical_match, sop_loader, sop_updater, api_update}.py
  → db_init checks agent_metadata, creates tables if needed
  → db_upsert implements UPSERT pattern (insert or update)
  → historical_match queries persistent ynab_transactions table
  → api_update supports split transactions
  → Create test_atoms.py
  → ✅ GATE: pytest test_atoms.py → ALL PASS

Layer 2: Molecules (5 files)
  → Create molecules/{data_loader, pattern_analyzer, sop_manager, learning_tracker, ynab_syncer}.py
  → data_loader uses UPSERT (not truncate+insert)
  → learning_tracker records agent decisions + user corrections in DB
  → ynab_syncer supports batch splits + DB updates
  → Create test_molecules.py
  → ✅ GATE: pytest test_molecules.py → ALL PASS

Layer 3: Organisms (3 files)
  → Create organisms/{categorization_agent, recommendation_engine, web_ui}.py
  → categorization_agent implements 4-tier logic + learning
  → web_ui supports split transaction UI
  → Create test_organisms.py
  → ✅ GATE: pytest test_organisms.py → ALL PASS

Layer 4: Templates (2 files)
  → Create templates/tagging_workflow.py (generate_recommendations, submit_approved_changes)
  → Create templates/web_server.py (Flask app with routes)
  → Create templates/index.html (frontend UI with split modals)
  → Create test_templates.py (Flask test client + endpoints)
  → ✅ GATE: pytest test_templates.py → ALL PASS

Layer 5: Workflow (1 file)
  → Create main.py (<100 lines - starts Flask + opens browser)
  → Create test_workflow.py (E2E with splits)
  → ✅ GATE: pytest test_workflow.py → ALL PASS

Manual E2E Test
  → Run: python tools/ynab/transaction_tagger/main.py
  → Verify browser opens to web UI
  → Click "Load & Tag", verify table displays
  → Verify split transactions show correctly
  → Edit split allocation
  → Click "Submit", verify YNAB updates (singles + splits)
  → Check categorization_rules.md was updated
  → ✅ GATE: Full workflow completes successfully
```

---

## File Structure (Final)

```
tools/ynab/transaction_tagger/
├── main.py                          # Entry point (<100 lines)
├── categorization_rules.md          # Self-learning SOP (agent updates)
├── sql/
│   └── init_persistent_db.sql       # NEW: DB schema (one-time init)
├── templates/
│   └── index.html                   # Web UI with split transaction modals
├── atoms/
│   ├── __init__.py
│   ├── api_fetch.py
│   ├── db_init.py                   # NEW: Check/init persistent DB
│   ├── db_upsert.py                 # NEW: UPSERT transactions (not truncate)
│   ├── db_query.py
│   ├── historical_match.py          # Modified: Query persistent ynab_transactions
│   ├── sop_loader.py                # NEW: Load SOP rules
│   ├── sop_updater.py               # NEW: Update SOP file
│   └── api_update.py                # Modified: Split transaction support
├── molecules/
│   ├── __init__.py
│   ├── data_loader.py               # Modified: UPSERT (not truncate+insert)
│   ├── pattern_analyzer.py
│   ├── sop_manager.py               # NEW: Manage categorization_rules.md
│   ├── learning_tracker.py          # NEW: Record agent decisions + corrections
│   └── ynab_syncer.py               # Modified: Batch splits + DB updates
├── organisms/
│   ├── __init__.py
│   ├── categorization_agent.py      # NEW: Self-learning agent
│   ├── recommendation_engine.py     # Modified: Orchestrates agent
│   └── web_ui.py                    # Modified: Split transaction UI
└── templates/
    ├── __init__.py
    ├── tagging_workflow.py          # Modified: Agent integration + DB updates
    └── web_server.py                # Modified: Split endpoints

agents/
└── ynab-categorization-agent.md     # NEW: Agent definition

.dev/testing/
├── test_atoms.py
├── test_molecules.py
├── test_organisms.py                # NEW: Test agent learning
├── test_templates.py                # Modified: Test split endpoints
└── test_workflow.py                 # Modified: Test split E2E

Database (PostgreSQL):
├── ynab_transactions                # PERSISTENT - grows with every approval
├── ynab_split_transactions          # PERSISTENT - split patterns
└── agent_metadata                   # PERSISTENT - initialization flag
```

**Total Files:** 26 (20 implementation + 1 HTML + 1 SQL schema + 1 agent definition + 1 SOP + 5 tests)
**Total Lines:** ~2,800 (excluding tests)

---

## Success Metrics

### Implementation Complete When:
- ✅ All 5 layers implemented (Atoms → Workflow)
- ✅ All test gates pass (real systems, no mocks)
- ✅ Agent can update categorization_rules.md
- ✅ Agent successfully uses WebSearch for unknown payees
- ✅ Split transactions display and submit correctly
- ✅ YNAB API accepts split transactions
- ✅ Agent learns from user corrections
- ✅ SOP file grows with learned rules
- ✅ Manual E2E test passes with splits

### Runtime Performance:
- ✅ Tier 1 (SOP Rules): <50ms per transaction (file read + pattern match)
- ✅ Tier 2 (SQL Historical): <100ms per transaction (DB query)
- ✅ Tier 3 (Research + Reasoning): 2-5 seconds per transaction (WebSearch + AI analysis)
- ✅ 23 untagged transactions processed in <3 minutes
- ✅ Split transaction modal loads instantly
- ✅ Over time: Most transactions hit Tier 1 (SOP) = near-instant

### User Experience:
- ✅ Clean web interface
- ✅ Split transactions clearly marked
- ✅ Edit split allocation easily
- ✅ See agent's reasoning
- ✅ Agent learns from corrections automatically
- ✅ SOP file viewable (transparency)
- ✅ Full keyboard navigation support
- ✅ Filtering and sorting capabilities
- ✅ Bulk category assignment
- ✅ Undo/redo functionality
- ✅ Toast notifications (no intrusive alerts)
- ✅ YNAB cleared status visibility
- ✅ Smart bulk actions (approve all high confidence)

---

## Vault Secret Structure

### Required Secrets
```bash
# YNAB API credentials
vault kv put secret/ynab/credentials \
  api_key=<your-ynab-api-key>

# Claude API credentials
vault kv put secret/claude/api_key \
  value=<your-anthropic-api-key>

# PostgreSQL connection (YNAB-specific database)
vault kv put secret/postgres/ynab_db \
  connection_string=postgresql://user:pass@host:port/dbname
```

---

**END OF PRD**

**Version History:**
- v3.5 (2025-11-27): Two-Budget Architecture - INIT_BUDGET_ID (75f63aa3-9f8f-4dcc-9350-d22535494657) for one-time learning, TARGET_BUDGET_ID (eaf7c5cb-e008-4b62-9733-e7d0ca96cbf1) for ongoing operations
- v3.4 (2025-11-25): Enhanced UX - keyboard navigation, filtering/sorting, bulk operations, YNAB cleared status, toast notifications, configuration constants, sop_rules table
- v3.3 (2025-11-23): Added comprehensive UX requirements for YNAB-style modal interactions
- v3.2 (2025-11-23): Reorganized to 3-tier logic: SOP Rules (Tier 1) → Historical (Tier 2) → Research+Reasoning (Tier 3)
- v3.1 (2025-11-23): Persistent database - agent's long-term memory grows with every approval
- v3.0 (2025-11-23): Self-learning agent with fallback logic, split transactions, SOP updates
- v2.2 (2025-11-23): Direct Claude API with Anthropic SDK, fixed DB references
- v2.1 (2025-11-23): Web-based interface with bulk checkbox approval
- v2.0 (2025-11-23): Atomic TDD architecture
- v1.0 (2025-10-25): Initial atomic modular design
