# YNAB Categorization Rules

**Last Updated:** 2025-11-27T14:31:57Z
**Agent Version:** 1.0
**Documentation:** See ynab-agent-prd-v2.md

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
