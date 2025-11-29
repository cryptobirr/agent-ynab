# YNAB Transaction Tagger

AI-powered transaction categorization for You Need A Budget (YNAB).

## Overview

This application analyzes your YNAB transactions and suggests categorizations using machine learning patterns. It provides a web interface to review, adjust, and submit categorizations back to YNAB.

## Features

- **Pattern Analysis:** Learn from your historical categorizations
- **AI Suggestions:** Get smart category suggestions for new transactions
- **Web Interface:** YNAB-style grid for easy review
- **Bulk Operations:** Categorize multiple transactions at once
- **Keyboard Shortcuts:** Power-user efficiency (Ctrl+L, Ctrl+S)
- **Filtering & Sorting:** Focus on what matters

## Architecture

Built on a layered molecular architecture:

- **Layer 1: Atoms** - Database operations (init, upsert)
- **Layer 2: Molecules** - Pattern analysis, learning tracker
- **Layer 3: SOP Manager** - Standard operating procedures
- **Layer 4: Templates** - Web server and frontend
- **Layer 5: Workflow** - Main entry point

## Prerequisites

- Python 3.11+
- PostgreSQL database
- YNAB API token
- HashiCorp Vault (optional, for secrets management)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/cryptobirr/agent-ynab.git
cd agent-ynab
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Configure environment:
```bash
# Option 1: Using Vault (recommended)
export VAULT_ADDR='http://127.0.0.1:8200'
export VAULT_TOKEN='your-vault-token'

# Option 2: Using .env file
cp .env.example .env
# Edit .env with your credentials
```

4. Initialize database:
```bash
python tools/ynab/transaction_tagger/atoms/db_init.py
```

## Usage

Start the application:
```bash
python main.py
```

The server will start on http://127.0.0.1:5000 and automatically open your browser.

### Web Interface

1. Click "Load Transactions" to fetch from YNAB
2. Review AI-suggested categories
3. Adjust categories as needed
4. Select transactions to submit
5. Click "Submit Tagged" to update YNAB

### Keyboard Shortcuts

- `Ctrl+L` - Load transactions
- `Ctrl+S` - Submit tagged transactions

## Testing

Run the test suite:
```bash
# All tests
pytest

# Specific layer
pytest tests/test_atoms.py
pytest templates/test_web_server.py
pytest test_main.py

# With coverage
pytest --cov=tools --cov=templates
```

## Project Structure

```
agent-ynab/
├── common/                  # Shared utilities
│   ├── base_client.py      # YNAB client
│   ├── db_connection.py    # Database connection
│   └── vault_client.py     # Vault integration
├── tools/ynab/transaction_tagger/
│   ├── atoms/              # Database atoms
│   ├── molecules/          # Business logic
│   └── tests/              # Layer tests
├── templates/              # Web layer
│   ├── web_server.py       # Quart server
│   ├── templates/          # HTML templates
│   └── test_web_server.py  # Web tests
├── main.py                 # Entry point
├── requirements.txt        # Dependencies
└── README.md              # This file
```

## Development

### Adding New Features

1. Follow the molecular architecture layers
2. Write tests first (TDD)
3. Ensure all tests pass before PR
4. Document in code and README

### Running in Development

```bash
# With debug logging
python main.py --debug

# Run server only (no browser)
python -c "from templates.web_server import app; app.run()"
```

## Configuration

### Environment Variables

- `VAULT_ADDR` - Vault server address
- `VAULT_TOKEN` - Vault authentication token
- `YNAB_API_TOKEN` - YNAB personal access token (if not using Vault)
- `DB_*` - Database connection parameters (if not using Vault)

### Vault Secrets

Store secrets in Vault paths:
- `secret/ynab/credentials` - YNAB API token
- `secret/postgres/agent-ynab` - Database credentials

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Run tests
5. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

For issues and questions:
- GitHub Issues: https://github.com/cryptobirr/agent-ynab/issues
- Documentation: See docs/ directory

## Acknowledgments

- Built with Quart (async Flask)
- Inspired by YNAB's excellent UI/UX
- Pattern analysis based on historical categorizations
