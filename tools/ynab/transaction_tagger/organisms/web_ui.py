"""
Web UI Organism - Generate HTML approval interface for transaction categorization.

This organism composes atoms and molecules to create a complete web interface
for reviewing and approving AI-categorized YNAB transactions.

Layer: 3 (Organisms - Complex business logic compositions)
"""
from typing import List, Dict, Any
import logging
import html
import json

logger = logging.getLogger(__name__)


def generate_approval_html(
    transactions: List[Dict[str, Any]],
    category_groups: List[Dict[str, Any]],
    budget_id: str
) -> str:
    """
    Generate complete HTML approval interface for transactions.
    
    Creates an interactive web page with:
    - Transaction grid with checkboxes for bulk selection
    - Category selector modal for changing categories
    - Split transaction modal for multi-category allocation
    
    Args:
        transactions: List of transaction dicts with recommendations.
                     Each transaction should have:
                     - id: Transaction UUID
                     - date: ISO date string (YYYY-MM-DD)
                     - payee_name: Payee name
                     - memo: Transaction memo (optional)
                     - amount: Amount in milliunits (negative = outflow)
                     - category_id: Current/recommended category UUID
                     - category_name: Current/recommended category name
                     - type: 'single' or 'split'
                     - confidence: Float 0.0-1.0 (recommendation confidence)
                     - tier: 'sop', 'historical', or 'research'
        category_groups: YNAB category hierarchy.
                        Each group should have:
                        - id: Category group UUID
                        - name: Group name
                        - categories: List of category dicts with id and name
        budget_id: YNAB budget UUID (for API calls)
    
    Returns:
        Complete HTML page as string with embedded CSS and JavaScript
    
    Raises:
        ValueError: If transactions or category_groups invalid/empty
    
    Example:
        >>> html = generate_approval_html(
        ...     transactions=[{
        ...         'id': 'txn_123',
        ...         'date': '2025-11-29',
        ...         'payee_name': 'Walmart',
        ...         'memo': 'Groceries',
        ...         'amount': -12500,
        ...         'category_id': 'cat_groceries',
        ...         'category_name': 'Groceries',
        ...         'type': 'single',
        ...         'confidence': 0.95,
        ...         'tier': 'sop'
        ...     }],
        ...     category_groups=[{
        ...         'id': 'grp_123',
        ...         'name': 'Everyday Expenses',
        ...         'categories': [
        ...             {'id': 'cat_groceries', 'name': 'Groceries'}
        ...         ]
        ...     }],
        ...     budget_id='budget_123'
        ... )
        >>> '<html' in html
        True
    """
    # Input validation
    if not transactions:
        raise ValueError("transactions list cannot be empty")
    if not category_groups:
        raise ValueError("category_groups list cannot be empty")
    if not budget_id or not isinstance(budget_id, str):
        raise ValueError("budget_id must be a non-empty string")
    
    # Validate transaction structure
    required_txn_fields = ['id', 'date', 'payee_name', 'amount', 'category_id', 'category_name', 'type', 'confidence', 'tier']
    for i, txn in enumerate(transactions):
        for field in required_txn_fields:
            if field not in txn:
                raise ValueError(f"Transaction at index {i} missing required field: {field}")
    
    # Validate category_groups structure
    for i, group in enumerate(category_groups):
        if 'id' not in group or 'name' not in group or 'categories' not in group:
            raise ValueError(f"Category group at index {i} missing required fields (id, name, categories)")
    
    logger.info(f"Generating approval HTML for {len(transactions)} transactions across {len(category_groups)} category groups")
    
    # Generate components
    grid_html = _generate_grid_html(transactions)
    category_modal_html = _generate_category_modal_html(category_groups)
    split_modal_html = _generate_split_modal_html()
    styles_html = _generate_styles()
    scripts_html = _generate_scripts(transactions, category_groups, budget_id)
    
    # Assemble complete page
    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>YNAB Transaction Approval</title>
    {styles_html}
</head>
<body>
    <div class="container">
        <header>
            <h1>Transaction Categorization Approval</h1>
            <div class="header-actions">
                <button id="approve-selected" class="btn btn-primary">Approve Selected</button>
                <button id="select-all" class="btn btn-secondary">Select All</button>
            </div>
        </header>
        
        <main>
            {grid_html}
        </main>
    </div>
    
    {category_modal_html}
    {split_modal_html}
    {scripts_html}
</body>
</html>"""
    
    return html


def _generate_grid_html(transactions: List[Dict]) -> str:
    """Generate transaction grid table HTML."""
    rows = []
    
    for txn in transactions:
        # Format amount as currency
        amount_value = txn['amount'] / 1000.0  # Convert milliunits to dollars
        amount_str = f"${abs(amount_value):,.2f}"
        amount_class = "outflow" if amount_value < 0 else "inflow"
        
        # Format confidence with color coding
        confidence = txn['confidence']
        confidence_pct = f"{confidence * 100:.0f}%"
        if confidence >= 0.90:
            confidence_class = "confidence-high"
        elif confidence >= 0.70:
            confidence_class = "confidence-medium"
        else:
            confidence_class = "confidence-low"
        
        # Category display (special handling for split)
        if txn['type'] == 'split':
            category_display = '<span class="split-indicator">[Split Transaction]</span>'
            category_click = f"onclick=\"openSplitModal('{txn['id']}')\""
        else:
            category_display = html.escape(txn['category_name'])
            category_click = f"onclick=\"openCategoryModal('{txn['id']}')\""
        
        # Tier badge
        tier = txn['tier'].upper()
        tier_class = f"tier-{txn['tier'].lower()}"
        
        # Build row
        row = f"""
        <tr data-txn-id="{txn['id']}" class="txn-row">
            <td><input type="checkbox" class="txn-checkbox" data-txn-id="{txn['id']}"></td>
            <td>{txn['date']}</td>
            <td class="payee-cell">{html.escape(txn['payee_name'])}</td>
            <td class="memo-cell">{html.escape(txn.get('memo', ''))}</td>
            <td class="{amount_class}">{amount_str}</td>
            <td class="category-cell" {category_click}>{category_display}</td>
            <td><span class="{confidence_class}">{confidence_pct}</span></td>
            <td><span class="tier-badge {tier_class}">{tier}</span></td>
        </tr>
        """
        rows.append(row)
    
    table_html = f"""
    <div class="table-container">
        <table class="txn-table">
            <thead>
                <tr>
                    <th><input type="checkbox" id="select-all-checkbox"></th>
                    <th>Date</th>
                    <th>Payee</th>
                    <th>Memo</th>
                    <th>Amount</th>
                    <th>Category</th>
                    <th>Confidence</th>
                    <th>Tier</th>
                </tr>
            </thead>
            <tbody>
                {''.join(rows)}
            </tbody>
        </table>
    </div>
    """
    
    return table_html


def _generate_category_modal_html(category_groups: List[Dict]) -> str:
    """Generate category selector modal HTML."""
    groups_html = []
    
    for group in category_groups:
        categories_html = []
        for cat in group['categories']:
            categories_html.append(
                f'<div class="category-item" data-group-id="{group["id"]}" data-category-id="{cat["id"]}" onclick="selectCategory(\'{group["id"]}\', \'{cat["id"]}\', \'{html.escape(cat["name"])}\')">{html.escape(cat["name"])}</div>'
            )
        
        group_html = f"""
        <div class="category-group">
            <div class="category-group-name">{html.escape(group['name'])}</div>
            <div class="category-list">
                {''.join(categories_html)}
            </div>
        </div>
        """
        groups_html.append(group_html)
    
    modal_html = f"""
    <div id="category-modal" class="modal" style="display: none;">
        <div class="modal-backdrop" onclick="closeCategoryModal()"></div>
        <div class="modal-content category-modal-content">
            <div class="modal-header">
                <h2>Select Category</h2>
                <button class="modal-close" onclick="closeCategoryModal()">&times;</button>
            </div>
            <div class="modal-body">
                {''.join(groups_html)}
                <div class="modal-actions">
                    <button id="split-button" class="btn btn-secondary" onclick="switchToSplitModal()">Split Transaction</button>
                </div>
            </div>
        </div>
    </div>
    """
    
    return modal_html


def _generate_split_modal_html() -> str:
    """Generate split transaction modal HTML."""
    modal_html = """
    <div id="split-modal" class="modal" style="display: none;">
        <div class="modal-backdrop" onclick="closeSplitModal()"></div>
        <div class="modal-content split-modal-content">
            <div class="modal-header">
                <h2>Split Transaction</h2>
                <button class="modal-close" onclick="closeSplitModal()">&times;</button>
            </div>
            <div class="modal-body">
                <div id="split-transaction-info" class="split-info"></div>
                <div id="split-rows-container"></div>
                <div class="split-actions">
                    <button class="btn btn-secondary" onclick="addSplitRow()">+ Add Row</button>
                </div>
                <div id="split-remaining" class="split-remaining"></div>
                <div id="split-error" class="split-error" style="display: none;"></div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" onclick="closeSplitModal()">Cancel</button>
                <button id="approve-split-btn" class="btn btn-primary" onclick="approveSplit()">Approve Split</button>
            </div>
        </div>
    </div>
    """
    
    return modal_html


def _generate_styles() -> str:
    """Generate embedded CSS styles."""
    return """
    <style>
        * {
            box-sizing: border-box;
            margin: 0;
            padding: 0;
        }
        
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            background-color: #f5f7fa;
            color: #2d3748;
            line-height: 1.6;
        }
        
        .container {
            max-width: 1400px;
            margin: 0 auto;
            padding: 20px;
        }
        
        header {
            background: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 20px;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        header h1 {
            font-size: 24px;
            color: #1a202c;
        }
        
        .header-actions {
            display: flex;
            gap: 10px;
        }
        
        .btn {
            padding: 10px 20px;
            border: none;
            border-radius: 6px;
            cursor: pointer;
            font-size: 14px;
            font-weight: 500;
            transition: all 0.2s;
        }
        
        .btn-primary {
            background-color: #3182ce;
            color: white;
        }
        
        .btn-primary:hover {
            background-color: #2c5aa0;
        }
        
        .btn-primary:disabled {
            background-color: #cbd5e0;
            cursor: not-allowed;
        }
        
        .btn-secondary {
            background-color: #e2e8f0;
            color: #2d3748;
        }
        
        .btn-secondary:hover {
            background-color: #cbd5e0;
        }
        
        .table-container {
            background: white;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 1px 3px rgba(0, 0, 0, 0.1);
        }
        
        .txn-table {
            width: 100%;
            border-collapse: collapse;
        }
        
        .txn-table thead {
            background-color: #f7fafc;
        }
        
        .txn-table th {
            padding: 12px 16px;
            text-align: left;
            font-weight: 600;
            font-size: 12px;
            text-transform: uppercase;
            color: #4a5568;
            border-bottom: 2px solid #e2e8f0;
        }
        
        .txn-table td {
            padding: 12px 16px;
            border-bottom: 1px solid #e2e8f0;
        }
        
        .txn-row:hover {
            background-color: #f7fafc;
        }
        
        .txn-row.selected {
            background-color: #ebf8ff;
        }
        
        .category-cell {
            cursor: pointer;
            color: #3182ce;
        }
        
        .category-cell:hover {
            text-decoration: underline;
        }
        
        .split-indicator {
            font-style: italic;
            color: #805ad5;
        }
        
        .outflow {
            color: #e53e3e;
            font-weight: 500;
        }
        
        .inflow {
            color: #38a169;
            font-weight: 500;
        }
        
        .confidence-high {
            background-color: #c6f6d5;
            color: #22543d;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        
        .confidence-medium {
            background-color: #feebc8;
            color: #744210;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        
        .confidence-low {
            background-color: #fed7d7;
            color: #742a2a;
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 12px;
        }
        
        .tier-badge {
            padding: 4px 8px;
            border-radius: 4px;
            font-size: 11px;
            font-weight: 600;
        }
        
        .tier-sop {
            background-color: #bee3f8;
            color: #2c5282;
        }
        
        .tier-historical {
            background-color: #d6bcfa;
            color: #44337a;
        }
        
        .tier-research {
            background-color: #fbd38d;
            color: #744210;
        }
        
        .modal {
            position: fixed;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            z-index: 1000;
        }
        
        .modal-backdrop {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            background-color: rgba(0, 0, 0, 0.5);
        }
        
        .modal-content {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            background: white;
            border-radius: 8px;
            box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1);
            max-height: 80vh;
            overflow-y: auto;
        }
        
        .category-modal-content {
            width: 90%;
            max-width: 600px;
        }
        
        .split-modal-content {
            width: 90%;
            max-width: 900px;
        }
        
        .modal-header {
            padding: 20px;
            border-bottom: 1px solid #e2e8f0;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        
        .modal-header h2 {
            font-size: 20px;
            color: #1a202c;
        }
        
        .modal-close {
            background: none;
            border: none;
            font-size: 28px;
            color: #a0aec0;
            cursor: pointer;
            padding: 0;
            width: 32px;
            height: 32px;
            line-height: 1;
        }
        
        .modal-close:hover {
            color: #4a5568;
        }
        
        .modal-body {
            padding: 20px;
        }
        
        .modal-footer {
            padding: 20px;
            border-top: 1px solid #e2e8f0;
            display: flex;
            justify-content: flex-end;
            gap: 10px;
        }
        
        .category-group {
            margin-bottom: 20px;
        }
        
        .category-group-name {
            font-weight: 600;
            color: #2d3748;
            margin-bottom: 8px;
            padding-bottom: 8px;
            border-bottom: 2px solid #e2e8f0;
        }
        
        .category-list {
            display: grid;
            gap: 8px;
        }
        
        .category-item {
            padding: 10px 12px;
            background-color: #f7fafc;
            border-radius: 6px;
            cursor: pointer;
            transition: all 0.2s;
        }
        
        .category-item:hover {
            background-color: #edf2f7;
            color: #3182ce;
        }
        
        .modal-actions {
            margin-top: 20px;
            padding-top: 20px;
            border-top: 1px solid #e2e8f0;
        }
        
        .split-info {
            background-color: #f7fafc;
            padding: 12px;
            border-radius: 6px;
            margin-bottom: 20px;
        }
        
        .split-row {
            display: grid;
            grid-template-columns: 2fr 2fr 2fr 1fr 1fr auto;
            gap: 10px;
            margin-bottom: 10px;
            align-items: center;
        }
        
        .split-row input,
        .split-row select {
            padding: 8px;
            border: 1px solid #cbd5e0;
            border-radius: 4px;
        }
        
        .split-row button {
            background-color: #fc8181;
            color: white;
            border: none;
            padding: 8px 12px;
            border-radius: 4px;
            cursor: pointer;
        }
        
        .split-row button:hover {
            background-color: #f56565;
        }
        
        .split-remaining {
            margin-top: 15px;
            padding: 12px;
            background-color: #f7fafc;
            border-radius: 6px;
            font-weight: 600;
        }
        
        .split-error {
            margin-top: 15px;
            padding: 12px;
            background-color: #fed7d7;
            color: #742a2a;
            border-radius: 6px;
        }
        
        .payee-cell {
            font-weight: 500;
        }
        
        .memo-cell {
            color: #718096;
            font-size: 13px;
        }
    </style>
    """


def _generate_scripts(
    transactions: List[Dict],
    category_groups: List[Dict],
    budget_id: str
) -> str:
    """Generate embedded JavaScript for modal interactions."""
    
    # Convert Python data to JSON for JavaScript
    transactions_json = json.dumps(transactions)
    category_groups_json = json.dumps(category_groups)
    
    return f"""
    <script>
        // Global state
        const state = {{
            transactions: {transactions_json},
            categoryGroups: {category_groups_json},
            budgetId: '{budget_id}',
            selectedTransactions: new Set(),
            activeModal: null,
            currentTransaction: null,
            splitRows: []
        }};
        
        // Initialize on page load
        document.addEventListener('DOMContentLoaded', function() {{
            // Select all checkbox handler
            document.getElementById('select-all-checkbox').addEventListener('change', function(e) {{
                const checkboxes = document.querySelectorAll('.txn-checkbox');
                checkboxes.forEach(cb => {{
                    cb.checked = e.target.checked;
                    onCheckboxChange(cb.dataset.txnId, cb.checked);
                }});
            }});
            
            // Individual checkbox handlers
            document.querySelectorAll('.txn-checkbox').forEach(cb => {{
                cb.addEventListener('change', function(e) {{
                    onCheckboxChange(e.target.dataset.txnId, e.target.checked);
                }});
            }});
            
            // Select all button
            document.getElementById('select-all').addEventListener('click', function() {{
                const selectAllCheckbox = document.getElementById('select-all-checkbox');
                selectAllCheckbox.checked = !selectAllCheckbox.checked;
                selectAllCheckbox.dispatchEvent(new Event('change'));
            }});
            
            // Keyboard shortcuts
            document.addEventListener('keydown', function(e) {{
                // Escape key - close modals
                if (e.key === 'Escape') {{
                    if (state.activeModal === 'category') closeCategoryModal();
                    if (state.activeModal === 'split') closeSplitModal();
                }}
                
                // Ctrl/Cmd + A - select all
                if ((e.ctrlKey || e.metaKey) && e.key === 'a') {{
                    e.preventDefault();
                    document.getElementById('select-all').click();
                }}
            }});
        }});
        
        // Checkbox selection
        function onCheckboxChange(txnId, checked) {{
            const row = document.querySelector(`tr[data-txn-id="${{txnId}}"]`);
            if (checked) {{
                state.selectedTransactions.add(txnId);
                row.classList.add('selected');
            }} else {{
                state.selectedTransactions.delete(txnId);
                row.classList.remove('selected');
            }}
        }}
        
        // Open category modal
        function openCategoryModal(txnId) {{
            state.currentTransaction = state.transactions.find(t => t.id === txnId);
            state.activeModal = 'category';
            document.getElementById('category-modal').style.display = 'block';
        }}
        
        // Close category modal
        function closeCategoryModal() {{
            state.activeModal = null;
            state.currentTransaction = null;
            document.getElementById('category-modal').style.display = 'none';
        }}
        
        // Select category
        function selectCategory(groupId, categoryId, categoryName) {{
            if (!state.currentTransaction) return;
            
            // Update transaction in state
            state.currentTransaction.category_id = categoryId;
            state.currentTransaction.category_name = categoryName;
            
            // Update UI
            const row = document.querySelector(`tr[data-txn-id="${{state.currentTransaction.id}}"]`);
            const categoryCell = row.querySelector('.category-cell');
            categoryCell.textContent = categoryName;
            
            // Close modal
            closeCategoryModal();
        }}
        
        // Switch to split modal from category modal
        function switchToSplitModal() {{
            closeCategoryModal();
            openSplitModal(state.currentTransaction.id);
        }}
        
        // Open split modal
        function openSplitModal(txnId) {{
            state.currentTransaction = state.transactions.find(t => t.id === txnId);
            state.activeModal = 'split';
            
            // Set up split modal
            const amount = state.currentTransaction.amount / 1000.0;
            const infoDiv = document.getElementById('split-transaction-info');
            infoDiv.innerHTML = `
                <strong>Payee:</strong> ${{state.currentTransaction.payee_name}}<br>
                <strong>Total Amount:</strong> $${{Math.abs(amount).toFixed(2)}}
            `;
            
            // Initialize split rows
            state.splitRows = [
                {{ categoryGroupId: '', categoryId: '', memo: '', amount: 0 }},
                {{ categoryGroupId: '', categoryId: '', memo: '', amount: 0 }}
            ];
            renderSplitRows();
            updateSplitRemaining();
            
            document.getElementById('split-modal').style.display = 'block';
        }}
        
        // Close split modal
        function closeSplitModal() {{
            state.activeModal = null;
            state.currentTransaction = null;
            state.splitRows = [];
            document.getElementById('split-modal').style.display = 'none';
        }}
        
        // Render split rows
        function renderSplitRows() {{
            const container = document.getElementById('split-rows-container');
            container.innerHTML = state.splitRows.map((row, idx) => `
                <div class="split-row">
                    <select onchange="updateSplitRowGroup(${{idx}}, this.value)">
                        <option value="">Select Group...</option>
                        ${{state.categoryGroups.map(g => 
                            `<option value="${{g.id}}" ${{row.categoryGroupId === g.id ? 'selected' : ''}}>${{g.name}}</option>`
                        ).join('')}}
                    </select>
                    <select onchange="updateSplitRowCategory(${{idx}}, this.value)">
                        <option value="">Select Category...</option>
                        ${{row.categoryGroupId ? 
                            state.categoryGroups.find(g => g.id === row.categoryGroupId)?.categories.map(c => 
                                `<option value="${{c.id}}" ${{row.categoryId === c.id ? 'selected' : ''}}>${{c.name}}</option>`
                            ).join('') : ''
                        }}
                    </select>
                    <input type="text" placeholder="Memo" value="${{row.memo}}" onchange="updateSplitRowMemo(${{idx}}, this.value)">
                    <input type="number" step="0.01" placeholder="0.00" value="${{row.amount || ''}}" onchange="updateSplitRowAmount(${{idx}}, this.value)">
                    <button onclick="removeSplitRow(${{idx}})" ${{state.splitRows.length <= 2 ? 'disabled' : ''}}>Remove</button>
                </div>
            `).join('');
        }}
        
        // Add split row
        function addSplitRow() {{
            state.splitRows.push({{ categoryGroupId: '', categoryId: '', memo: '', amount: 0 }});
            renderSplitRows();
            updateSplitRemaining();
        }}
        
        // Remove split row
        function removeSplitRow(idx) {{
            if (state.splitRows.length <= 2) return;  // Minimum 2 rows
            state.splitRows.splice(idx, 1);
            renderSplitRows();
            updateSplitRemaining();
        }}
        
        // Update split row group
        function updateSplitRowGroup(idx, groupId) {{
            state.splitRows[idx].categoryGroupId = groupId;
            state.splitRows[idx].categoryId = '';  // Reset category when group changes
            renderSplitRows();
        }}
        
        // Update split row category
        function updateSplitRowCategory(idx, categoryId) {{
            state.splitRows[idx].categoryId = categoryId;
        }}
        
        // Update split row memo
        function updateSplitRowMemo(idx, memo) {{
            state.splitRows[idx].memo = memo;
        }}
        
        // Update split row amount
        function updateSplitRowAmount(idx, amount) {{
            state.splitRows[idx].amount = parseFloat(amount) || 0;
            updateSplitRemaining();
        }}
        
        // Calculate and display remaining amount
        function updateSplitRemaining() {{
            const totalAmount = Math.abs(state.currentTransaction.amount / 1000.0);
            const splitTotal = state.splitRows.reduce((sum, row) => sum + (row.amount || 0), 0);
            const remaining = totalAmount - splitTotal;
            
            const remainingDiv = document.getElementById('split-remaining');
            remainingDiv.textContent = `Remaining: $${{remaining.toFixed(2)}}`;
            
            const errorDiv = document.getElementById('split-error');
            const approveBtn = document.getElementById('approve-split-btn');
            
            if (Math.abs(remaining) < 0.01) {{
                errorDiv.style.display = 'none';
                approveBtn.disabled = false;
            }} else {{
                errorDiv.style.display = 'block';
                errorDiv.textContent = `Split amounts must sum to $${{totalAmount.toFixed(2)}}`;
                approveBtn.disabled = true;
            }}
        }}
        
        // Approve split
        function approveSplit() {{
            if (!state.currentTransaction) return;
            
            // Validate all rows have category selected
            const allValid = state.splitRows.every(row => row.categoryId && row.amount > 0);
            if (!allValid) {{
                alert('Please select a category and amount for all split rows');
                return;
            }}
            
            // Update transaction to split type
            state.currentTransaction.type = 'split';
            state.currentTransaction.split_details = state.splitRows;
            
            // Update UI
            const row = document.querySelector(`tr[data-txn-id="${{state.currentTransaction.id}}"]`);
            const categoryCell = row.querySelector('.category-cell');
            categoryCell.innerHTML = '<span class="split-indicator">[Split Transaction]</span>';
            categoryCell.setAttribute('onclick', `openSplitModal('${{state.currentTransaction.id}}')`);
            
            // Close modal
            closeSplitModal();
        }}
        
        // Approve selected transactions
        document.getElementById('approve-selected').addEventListener('click', function() {{
            if (state.selectedTransactions.size === 0) {{
                alert('Please select at least one transaction');
                return;
            }}
            
            const selectedTxns = Array.from(state.selectedTransactions).map(id => 
                state.transactions.find(t => t.id === id)
            );
            
            // TODO: Send to backend for approval
            console.log('Approving transactions:', selectedTxns);
            alert(`Approved ${{selectedTxns.length}} transaction(s)`);
            
            // Clear selection
            state.selectedTransactions.clear();
            document.querySelectorAll('.txn-checkbox').forEach(cb => cb.checked = false);
            document.querySelectorAll('.txn-row').forEach(row => row.classList.remove('selected'));
        }});
    </script>
    """

