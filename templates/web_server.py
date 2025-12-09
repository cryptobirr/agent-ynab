"""
Web Server Template for YNAB Transaction Tagger

Provides HTTP endpoints for the transaction tagging workflow:
- GET / - Main application page
- GET /api/load-and-tag - Trigger full workflow
- POST /api/submit - Submit tagged transactions
"""

# CRITICAL: Set environment variables FIRST, before any other imports
import os
import sys
from pathlib import Path

# Add project root to Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Set Vault environment variables (must be done before importing common modules)
if 'VAULT_ADDR' not in os.environ:
    os.environ['VAULT_ADDR'] = 'http://127.0.0.1:8200'
if 'VAULT_TOKEN' not in os.environ:
    # Read token from ~/.vault-token file
    try:
        with open(os.path.expanduser('~/.vault-token'), 'r') as f:
            os.environ['VAULT_TOKEN'] = f.read().strip()
    except:
        os.environ['VAULT_TOKEN'] = 'dev-token'  # Fallback

# Also set database environment variables as fallback
if 'POSTGRES_HOST' not in os.environ:
    os.environ['POSTGRES_HOST'] = 'localhost'
    os.environ['POSTGRES_PORT'] = '5432'
    os.environ['POSTGRES_DB'] = 'ynab_db'
    os.environ['POSTGRES_USER'] = 'postgres'
    os.environ['POSTGRES_PASSWORD'] = 'Dayton01'

# Set YNAB API token
if 'YNAB_API_TOKEN' not in os.environ:
    os.environ['YNAB_API_TOKEN'] = 'bxZJrzgLIH9S7nrvRRoy1IqkYh-TrF20J-Z020Zd0zc'

# Now import other modules
from quart import Quart, request, jsonify, render_template
import logging
from typing import Dict, Any
import traceback

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Quart app
app = Quart(__name__)


# Add no-cache headers to all responses
@app.after_request
async def add_no_cache_headers(response):
    """Disable caching for all responses."""
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
async def index():
    """
    Serve main application page.

    Returns:
        HTML template for the main application interface
    """
    try:
        return await render_template('index.html')
    except Exception as e:
        logger.error(f"Error serving index: {e}")
        return jsonify({
            'status': 'error',
            'message': 'Failed to load application'
        }), 500


@app.route('/api/load-and-tag', methods=['GET'])
async def load_and_tag():
    """
    Trigger full workflow execution.
    
    Executes the complete YNAB transaction tagging workflow:
    1. Load transactions from YNAB
    2. Analyze patterns
    3. Generate categorization suggestions
    4. Return tagged transactions
    
    Returns:
        JSON response with workflow results or error message
    """
    try:
        logger.info("Starting load-and-tag workflow")

        # Import tagging workflow template
        # Note: Import here to avoid circular dependencies
        from tools.ynab.transaction_tagger.templates.tagging_workflow import generate_recommendations

        # Execute workflow - only load personal budget
        result = generate_recommendations(
            budget_type='personal',
            uncategorized_only=True
        )

        if result['status'] == 'failed':
            logger.error(f"Workflow failed: {result.get('errors')}")
            return jsonify({
                'status': 'error',
                'message': 'Workflow execution failed',
                'errors': result.get('errors', [])
            }), 500

        # Count total transactions
        total_txns = sum(
            len(budget_data.get('transactions', []))
            for budget_data in result.get('budgets', {}).values()
        )

        # Fetch ALL accounts from YNAB (for tabs)
        from tools.ynab.transaction_tagger.atoms.api_fetch import fetch_accounts
        budget_id = result.get('budgets', {}).get('personal', {}).get('budget_id')
        if budget_id:
            try:
                all_accounts = fetch_accounts(budget_id)
                # Add accounts to result
                for budget_name, budget_data in result.get('budgets', {}).items():
                    budget_data['all_accounts'] = all_accounts
            except Exception as e:
                logger.warning(f"Failed to fetch accounts: {e}")

        logger.info(f"Workflow completed successfully: {total_txns} transactions")

        return jsonify({
            'status': 'success',
            'data': result
        }), 200
        
    except Exception as e:
        logger.error(f"Error in load-and-tag: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.route('/api/submit', methods=['POST'])
async def submit():
    """
    Accept tagged transaction submissions.

    Receives user-confirmed transaction categorizations and:
    1. Validates the payload
    2. Updates YNAB with confirmed categories
    3. Records decisions for learning

    Expected payload:
    {
        "budget_id": "budget-uuid",
        "transactions": [
            {
                "transaction_id": "transaction-id",
                "category_id": "category-id",
                "category_name": "category-name",
                "categorization_tier": 1-3,
                "confidence_score": 0.0-1.0,
                "method": "sop|historical|manual"
            }
        ]
    }

    Returns:
        JSON response with processing results or error message
    """
    try:
        logger.info("Processing transaction submission")

        # Parse request body
        data = await request.get_json()

        # Validate payload
        if not data:
            return jsonify({
                'status': 'error',
                'message': 'Empty request body'
            }), 400

        if 'budget_id' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "budget_id" field in payload'
            }), 400

        if 'transactions' not in data:
            return jsonify({
                'status': 'error',
                'message': 'Missing "transactions" field in payload'
            }), 400

        if not isinstance(data['transactions'], list):
            return jsonify({
                'status': 'error',
                'message': '"transactions" must be an array'
            }), 400

        transactions = data['transactions']
        budget_id = data['budget_id']

        if len(transactions) == 0:
            return jsonify({
                'status': 'error',
                'message': 'No transactions provided'
            }), 400

        # Validate transaction structure
        required_fields = ['transaction_id', 'category_name',
                          'categorization_tier', 'confidence_score', 'method']
        for idx, txn in enumerate(transactions):
            if not isinstance(txn, dict):
                return jsonify({
                    'status': 'error',
                    'message': f'Transaction at index {idx} is not an object'
                }), 400

            for field in required_fields:
                if field not in txn:
                    return jsonify({
                        'status': 'error',
                        'message': f'Transaction at index {idx} missing required field: {field}'
                    }), 400

            # category_id is required for non-transfers
            is_transfer = txn.get('category_name') == 'SKIP_TRANSFER'
            if not is_transfer and 'category_id' not in txn:
                return jsonify({
                    'status': 'error',
                    'message': f'Transaction at index {idx} missing required field: category_id'
                }), 400

        logger.info(f"Validated {len(transactions)} transactions for budget {budget_id}")

        # Import submission function
        from tools.ynab.transaction_tagger.templates.tagging_workflow import submit_approved_changes

        # Submit to YNAB API
        result = submit_approved_changes(
            budget_id=budget_id,
            approved_changes=transactions
        )

        logger.info(f"Submission result: {result['status']} - {result.get('succeeded', 0)}/{result.get('total', 0)} succeeded")

        # Return result to frontend
        return jsonify(result), 200

    except Exception as e:
        logger.error(f"Error in submit: {e}")
        logger.error(traceback.format_exc())
        return jsonify({
            'status': 'error',
            'message': str(e)
        }), 500


@app.errorhandler(404)
async def not_found(error):
    """Handle 404 errors."""
    return jsonify({
        'status': 'error',
        'message': 'Endpoint not found'
    }), 404


@app.errorhandler(500)
async def internal_error(error):
    """Handle 500 errors."""
    logger.error(f"Internal server error: {error}")
    return jsonify({
        'status': 'error',
        'message': 'Internal server error'
    }), 500


if __name__ == '__main__':
    logger.info("Starting YNAB Transaction Tagger web server")
    app.run(debug=True, host='0.0.0.0', port=5001)  # debug=True for development
