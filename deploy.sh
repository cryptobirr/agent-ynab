#!/bin/bash
# YNAB Transaction Tagger - Deployment Script (Story 8.3)

set -e  # Exit on error

echo "========================================="
echo "YNAB Transaction Tagger - Deployment"
echo "========================================="
echo ""

# Check Python version
echo "Checking Python version..."
python_version=$(python3 --version 2>&1 | awk '{print $2}')
required_version="3.11"

if ! python3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)"; then
    echo "❌ Error: Python 3.11+ required (found $python_version)"
    exit 1
fi
echo "✅ Python $python_version"
echo ""

# Check PostgreSQL
echo "Checking PostgreSQL connection..."
if ! command -v psql &> /dev/null; then
    echo "⚠️  Warning: psql not found. Ensure PostgreSQL is installed."
else
    echo "✅ PostgreSQL client found"
fi
echo ""

# Create virtual environment
echo "Creating virtual environment..."
if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    echo "✅ Created .venv"
else
    echo "✅ .venv already exists"
fi
echo ""

# Activate virtual environment
echo "Activating virtual environment..."
source .venv/bin/activate
echo "✅ Virtual environment activated"
echo ""

# Install dependencies
echo "Installing dependencies..."
pip install -q --upgrade pip
pip install -q -r requirements.txt
echo "✅ Dependencies installed"
echo ""

# Check for environment configuration
echo "Checking configuration..."
if [ -n "$VAULT_ADDR" ] && [ -n "$VAULT_TOKEN" ]; then
    echo "✅ Vault configuration detected"
    echo "   VAULT_ADDR: $VAULT_ADDR"
elif [ -f ".env" ]; then
    echo "✅ .env file found"
else
    echo "⚠️  Warning: No Vault or .env configuration found"
    echo "   Please configure one of:"
    echo "   - Vault (export VAULT_ADDR and VAULT_TOKEN)"
    echo "   - .env file (copy .env.example and edit)"
fi
echo ""

# Initialize database
echo "Initializing database..."
if python3 tools/ynab/transaction_tagger/atoms/db_init.py; then
    echo "✅ Database initialized"
else
    echo "⚠️  Warning: Database initialization failed (may already exist)"
fi
echo ""

# Run tests
echo "Running tests..."
if pytest -q --tb=short 2>&1 | tail -5; then
    echo "✅ Tests passed"
else
    echo "❌ Tests failed - fix before deploying"
    exit 1
fi
echo ""

# Create deployment info
cat > DEPLOYMENT_INFO.txt << EOF
Deployment Information
======================

Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Python Version: $python_version
Git Commit: $(git rev-parse --short HEAD)
Git Branch: $(git branch --show-current)

Installed Packages:
$(pip freeze)
EOF

echo "✅ Deployment info saved to DEPLOYMENT_INFO.txt"
echo ""

echo "========================================="
echo "Deployment Complete!"
echo "========================================="
echo ""
echo "To start the application:"
echo "  source .venv/bin/activate"
echo "  python main.py"
echo ""
echo "For production deployment:"
echo "  - Use a process manager (systemd, supervisord)"
echo "  - Configure reverse proxy (nginx, caddy)"
echo "  - Enable HTTPS/TLS"
echo "  - Set up monitoring and logging"
echo ""
