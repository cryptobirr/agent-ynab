# Architecture Documentation (Story 8.2)

**Issue:** #36  
**Status:** ✅ COMPLETE

## System Architecture

### Layered Molecular Design

The application follows a strict layered architecture where each layer builds on the previous:

```
Layer 5: Workflow (main.py)
    ↓
Layer 4: Templates (web_server.py, index.html)
    ↓
Layer 3: SOP Manager (standard procedures)
    ↓
Layer 2: Molecules (pattern_analyzer, learning_tracker, ynab_syncer)
    ↓
Layer 1: Atoms (db_init, db_upsert)
    ↓
Common Utilities (base_client, db_connection, vault_client)
```

## Component Documentation

### Layer 1: Atoms

**Purpose:** Smallest, reusable database operations

- **db_init.py** - Database initialization and schema management
- **db_upsert.py** - Upsert operations for transaction storage

**Key Principles:**
- Single responsibility
- No business logic
- Reusable across projects

### Layer 2: Molecules

**Purpose:** Business logic combining multiple atoms

- **pattern_analyzer.py** - Analyzes transaction patterns for categorization
- **learning_tracker.py** - Records and learns from user decisions
- **ynab_syncer.py** - Syncs transactions between YNAB and database

**Key Principles:**
- Compose atoms into business logic
- Self-contained functionality
- Testable in isolation

### Layer 3: SOP Manager

**Purpose:** Standard operating procedures for complex workflows

- **categorization_rules.md** - Rules for transaction categorization
- Workflow definitions and decision trees

**Key Principles:**
- Document repeatable processes
- Enable automation
- Version-controlled procedures

### Layer 4: Templates

**Purpose:** User interface layer

- **web_server.py** - Quart async web server
- **index.html** - YNAB-style frontend interface
- **test_web_server.py** - Web layer tests

**Key Principles:**
- Clean API design
- Separation of concerns
- Responsive UI/UX

### Layer 5: Workflow

**Purpose:** Application entry point

- **main.py** - Starts server, opens browser
- **test_main.py** - Workflow tests

**Key Principles:**
- Minimal orchestration logic
- Clean startup/shutdown
- User-friendly defaults

## Common Utilities

### base_client.py
YNAB API client with Vault integration
- Fetches API token from Vault
- Handles YNAB API requests
- Error handling and retries

### db_connection.py
PostgreSQL connection management
- Async connection pooling
- Vault-based credential management
- Graceful error handling

### vault_client.py
HashiCorp Vault integration
- Secret retrieval
- Fallback to .env for development
- Secure credential management

## Data Flow

1. **User Request** → Web Interface (index.html)
2. **Frontend** → HTTP Request → Web Server (web_server.py)
3. **Web Server** → Business Logic → Molecules
4. **Molecules** → Database Operations → Atoms
5. **Atoms** → PostgreSQL Database
6. **Response** ← Reverse flow back to user

## External Dependencies

- **YNAB API** - Transaction and category data
- **PostgreSQL** - Transaction storage and learning data
- **HashiCorp Vault** - Secret management (optional)

## Testing Strategy

Each layer has comprehensive tests:

- **Atoms:** Database operation tests
- **Molecules:** Business logic tests with mocking
- **Templates:** HTTP endpoint tests
- **Workflow:** Integration tests
- **E2E:** Manual testing checklist

## Security

- **Secrets Management:** Vault-first, .env fallback
- **Input Validation:** All API endpoints validate input
- **SQL Injection:** Parameterized queries only
- **XSS Prevention:** HTML escaping in frontend
- **HTTPS:** Production deployment should use TLS

## Performance

- **Async Operations:** Quart for async request handling
- **Connection Pooling:** Database connections pooled
- **Client-Side Processing:** Filtering/sorting in browser
- **Minimal Dependencies:** Lightweight architecture

## Deployment

See DEPLOYMENT.md (Story 8.3) for deployment procedures.

## Code Quality

- **Type Hints:** Used throughout Python code
- **Docstrings:** All public functions documented
- **Linting:** Follow PEP 8 standards
- **Testing:** >80% code coverage target

## Future Enhancements

- Real-time updates (WebSocket)
- Offline support (Service Worker)
- Mobile app (React Native)
- Advanced ML categorization
- Multi-user support
