"""
Web Server Template for YNAB Transaction Tagger

Provides HTTP endpoints for the transaction tagging workflow:
- GET / - Main application page
- GET /api/load-and-tag - Trigger full workflow
- POST /api/submit - Submit tagged transactions
"""

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

        # Execute workflow
        result = generate_recommendations(
            budget_type='both',
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
        "transactions": [
            {
                "id": "transaction-id",
                "category_id": "category-id",
                "notes": "optional notes"
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
        
        if len(transactions) == 0:
            return jsonify({
                'status': 'error',
                'message': 'No transactions provided'
            }), 400
        
        # Validate transaction structure
        for idx, txn in enumerate(transactions):
            if not isinstance(txn, dict):
                return jsonify({
                    'status': 'error',
                    'message': f'Transaction at index {idx} is not an object'
                }), 400
            
            required_fields = ['id', 'category_id']
            for field in required_fields:
                if field not in txn:
                    return jsonify({
                        'status': 'error',
                        'message': f'Transaction at index {idx} missing required field: {field}'
                    }), 400
        
        logger.info(f"Validated {len(transactions)} transactions")
        
        # TODO: Implement submission logic
        # - Update YNAB transactions with confirmed categories
        # - Record learning data
        # - Return results
        
        # Placeholder response
        return jsonify({
            'status': 'success',
            'message': f'Processed {len(transactions)} transactions',
            'note': 'Submission processing not yet implemented (Story 4.3 pending)'
        }), 200
        
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
    app.run(debug=True, host='0.0.0.0', port=5000)
