# YNAB Categorization Rules

**Last Updated:** 2025-12-07T19:56:29Z
**Agent Version:** 1.1
**Documentation:** See ynab-agent-prd-v2.md, .dev/amazon-categorization-system.md

This file is automatically maintained by the YNAB Categorization Agent.
Rules are learned from user corrections and web research.

---

## Core Patterns

This section contains high-confidence categorization rules learned from:
- Historical pattern analysis (≥80% confidence)
- User-validated corrections
- Web research results that have been validated

### Template Entry Format
```
- **Pattern**: {regex or keyword pattern}
- **Category**: {YNAB category name}
- **Confidence**: {High|Medium|Low}
- **Source**: {Historical|User Validation|Web Research}
- **Date Added**: {YYYY-MM-DD}
```

### Transfer Detection Rule (Tier 1 - Priority 1)

- **Pattern**: `^Transfer\s*:.*`
- **Pattern Type**: regex
- **Category**: null (do not categorize - YNAB transfers are not categorized)
- **Confidence**: High
- **Source**: YNAB Standard Behavior
- **Date Added**: 2025-11-28
- **Reasoning**: YNAB transfers between budget accounts should not be categorized. They represent movement of money between accounts in the same budget and are tracked via payee only.
- **Note**: Matches "Transfer : Wells Fargo", "Transfer: Citi Credit Card", "Transfer :Wealthfront" etc.

### Inflow Detection Rule (Tier 1 - Priority 2)

- **Pattern**: `amount > 0` (positive transaction amounts)
- **Pattern Type**: amount-based
- **Category**: Ready to Assign (Inflow)
- **Confidence**: High
- **Source**: YNAB Standard Behavior
- **Date Added**: 2025-11-28
- **Reasoning**: YNAB standard behavior - all inflows (income) are categorized as "Ready to Assign" unless they are transfers. This includes paychecks, reimbursements, and any other money coming into budget accounts.
- **Note**: Applied after transfer detection, so transfer inflows are excluded

### Amazon Invoice Processing (Tier 1 - Priority 3)

- **Pattern**: `^Amazon` (payee starts with "Amazon")
- **Pattern Type**: regex + invoice matching
- **Category**: Multi-category split based on invoice line items
- **Confidence**: High (0.95+ for matched items, 0.0 for unmatched)
- **Source**: Invoice-Level Categorization System
- **Date Added**: 2025-12-07
- **Implementation**: Database-backed (amazon_items, amazon_order_totals tables)
- **Reasoning**: Amazon transactions often contain multiple items from different categories. Instead of categorizing the entire transaction to one category, parse the invoice PDF to extract line items and split the transaction proportionally across categories.

**Processing Flow:**
1. **Match Transaction to Invoice**: Link YNAB transaction to Amazon order using amount and date
2. **Parse Invoice PDF**: Extract line items, quantities, prices from invoice
3. **Categorize Items**: Query `amazon_items` table for category mappings using:
   - Tier 1: Exact ASIN match (100% confidence, user verified)
   - Tier 2: Exact item name match (95% confidence, user verified)
   - Tier 3: Fuzzy item name match (80% confidence, learned patterns)
4. **Generate Split**: Create YNAB split transaction if items span multiple categories
5. **Add Memo**: Include concise item description in each subtransaction memo

**Split Transaction Format:**
```
Amazon Order 113-1234567-8901234
├─ Electronics ($12.99) - "USB-C Cable, 6ft"
├─ Groceries ($16.98) - "Organic Coffee Beans, 2lb"
└─ Household ($8.50) - "Dish Soap, 3-pack"
Total: $38.47
```

**Learning System:**
- User corrections automatically update `amazon_items` table
- ASIN-based matching enables exact product identification
- Item name fuzzy matching handles variations in description
- User-verified categories take highest priority

**Scalability:**
- Supports thousands of unique Amazon items via PostgreSQL tables
- No performance degradation as rule count grows
- Full-text search indexing for fast item name matching
- ASIN indexing for instant exact product matches

**Modules:**
- `atoms/amazon_schema.sql` - Database schema
- `atoms/amazon_db_init.py` - Table initialization
- `molecules/amazon_parser.py` - PDF invoice parsing
- `molecules/amazon_categorizer.py` - Split transaction generation

**Manual Review Trigger:**
- If any line item lacks category mapping → mark entire transaction "Needs Review"
- User assigns categories → system learns for future automation
- Uncategorized items listed in transaction notes for quick resolution

---

## Split Transaction Patterns

Multi-category allocations for merchants that typically have mixed purchases.

### Template Entry Format
```
- **Pattern**: {payee name pattern}
- **Type**: Split Transaction
- **Default Allocation**:
  * {Category 1}: {percentage}%
  * {Category 2}: {percentage}%
  * {Category 3}: {percentage}%
- **Confidence**: {High|Medium|Low}
- **Source**: {User-defined|Agent inference|Historical pattern}
- **Date Added**: {YYYY-MM-DD}
- **Note**: {optional context}
```

---

## Learned from User Corrections

Rules created when user modifies agent recommendations. These have highest confidence.

### Template Entry Format
```
- **Payee**: {exact payee name}
- **Correct Category**: {category name} (ID: {category_id})
- **Agent Initially Suggested**: {wrong category}
- **Reasoning**: {why correction was needed}
- **Confidence**: High (user-validated)
- **Date Learned**: {YYYY-MM-DD}
```

---

## Web Research Results

Categorization rules derived from web search when payee is unknown.

### Template Entry Format
```
- **Unknown Payee**: {payee name}
- **Business Type**: {type from web search}
- **Category**: {suggested category}
- **Reasoning**: {web search findings}
- **Confidence**: Medium (web-sourced)
- **Date Added**: {YYYY-MM-DD}
```

---

_End of Categorization Rules_
