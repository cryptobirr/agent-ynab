"""API fetch atom - Pure functions for YNAB API data retrieval"""
from typing import List, Dict, Optional
from common.base_client import BaseYNABClient


def fetch_transactions(budget_id: str, since_date: Optional[str] = None) -> List[Dict]:
    """
    Fetch all transactions from YNAB API for a given budget.
    
    Handles pagination automatically using server_knowledge mechanism.
    Filters out deleted transactions.
    
    Args:
        budget_id: YNAB budget identifier
        since_date: Optional ISO date string (YYYY-MM-DD) to fetch transactions on/after this date
    
    Returns:
        List of transaction dictionaries (non-deleted only)
    
    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)
    
    Example:
        >>> transactions = fetch_transactions('budget-123', since_date='2025-01-01')
        >>> len(transactions)
        42
    """
    client = BaseYNABClient()
    transactions = []
    server_knowledge = 0
    
    while True:
        # Build request parameters
        params = {}
        if since_date:
            params['since_date'] = since_date
        if server_knowledge > 0:
            params['last_knowledge_of_server'] = server_knowledge
        
        # Make API request
        response = client.get(f'/budgets/{budget_id}/transactions', params)
        data = response.get('data', {})
        
        # Get batch and new knowledge
        batch = data.get('transactions', [])
        new_knowledge = data.get('server_knowledge', 0)
        
        # Stop if no data
        if len(batch) == 0:
            break
        
        # If knowledge unchanged from last iteration, we've got all the data
        # (This means the API is returning the same page again)
        if new_knowledge > 0 and new_knowledge == server_knowledge:
            break
            
        # Add this batch
        transactions.extend(batch)
        
        # Update knowledge for next iteration
        server_knowledge = new_knowledge
    
    # Filter out deleted transactions
    return [t for t in transactions if not t.get('deleted', False)]


def fetch_categories(budget_id: str) -> List[Dict]:
    """
    Fetch all categories from YNAB API for a given budget.

    Returns flattened list of categories (not grouped).
    Filters out hidden and deleted categories.

    Args:
        budget_id: YNAB budget identifier

    Returns:
        List of category dictionaries (non-hidden, non-deleted only)

    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)

    Example:
        >>> categories = fetch_categories('budget-123')
        >>> categories[0]['name']
        'Groceries'
    """
    client = BaseYNABClient()

    # Fetch categories
    response = client.get(f'/budgets/{budget_id}/categories')
    data = response.get('data', {})
    category_groups = data.get('category_groups', [])

    # Flatten and filter categories
    categories = []
    for group in category_groups:
        if group.get('hidden') or group.get('deleted'):
            continue

        for category in group.get('categories', []):
            if not category.get('hidden') and not category.get('deleted'):
                categories.append(category)

    return categories


def fetch_accounts(budget_id: str) -> List[Dict]:
    """
    Fetch all accounts from YNAB API for a given budget.

    Filters out closed and deleted accounts.

    Args:
        budget_id: YNAB budget identifier

    Returns:
        List of account dictionaries (non-closed, non-deleted only)

    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)

    Example:
        >>> accounts = fetch_accounts('budget-123')
        >>> accounts[0]['name']
        'Checking Account'
    """
    client = BaseYNABClient()

    # Fetch accounts
    response = client.get(f'/budgets/{budget_id}/accounts')
    data = response.get('data', {})
    accounts = data.get('accounts', [])

    # Filter out closed and deleted accounts
    return [
        acc for acc in accounts
        if not acc.get('closed') and not acc.get('deleted')
    ]


def fetch_category_groups(budget_id: str) -> List[Dict]:
    """
    Fetch category groups with their nested categories from YNAB API.

    Returns grouped structure preserving the hierarchy.
    Filters out hidden and deleted groups and categories.

    Args:
        budget_id: YNAB budget identifier

    Returns:
        List of category group dictionaries with nested categories

    Raises:
        YNABAPIError: On API errors (401, 404, 429, network errors)

    Example:
        >>> groups = fetch_category_groups('budget-123')
        >>> groups[0]['name']
        'Household'
        >>> groups[0]['categories'][0]['name']
        'Groceries'
    """
    client = BaseYNABClient()

    # Fetch categories
    response = client.get(f'/budgets/{budget_id}/categories')
    data = response.get('data', {})
    category_groups = data.get('category_groups', [])

    # Filter groups and categories
    result = []
    for group in category_groups:
        if group.get('hidden') or group.get('deleted'):
            continue

        # Filter categories within the group
        filtered_categories = [
            cat for cat in group.get('categories', [])
            if not cat.get('hidden') and not cat.get('deleted')
        ]

        if filtered_categories:  # Only include groups that have visible categories
            result.append({
                'id': group.get('id'),
                'name': group.get('name'),
                'categories': filtered_categories
            })

    return result
