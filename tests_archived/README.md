# Tests Directory

This directory contains the test suite for the Stock Price Data API.

## Structure

```
tests/
├── README.md           # This file
├── conftest.py         # Shared pytest configuration
├── unit/               # Unit tests (isolated, fast)
├── integration/        # Integration tests (with database)
└── e2e/               # End-to-end tests (full API)
```

## Test Categories

### Unit Tests (`unit/`)
- Fast, isolated tests
- Mock external dependencies
- Test individual functions and classes
- Run with: `pytest tests/unit/`

### Integration Tests (`integration/`)
- Test database interactions
- Test service layer integration
- Require database connection
- Run with: `pytest tests/integration/`

### End-to-End Tests (`e2e/`)
- Test complete API workflows
- Test full request/response cycles
- Require running application
- Run with: `pytest tests/e2e/`

## Running Tests

### All Tests
```bash
pytest tests/
```

### Specific Category
```bash
pytest tests/unit/
pytest tests/integration/
pytest tests/e2e/
```

### With Coverage
```bash
pytest tests/ --cov=app --cov-report=html
```

## Test Configuration

The `conftest.py` file contains shared pytest fixtures and configuration used across all test categories.

## Cleanup History

This directory was cleaned up to remove:
- Temporary debug scripts
- Analysis utilities
- One-time migration scripts
- Backup files
- Cache directories (`__pycache__`)

Only proper test files following pytest conventions are now maintained.
