# Smart Expense Tracker — Test Plan

## Required gate

```bash
python -m pytest --cov --cov-report=term -q
python -m mypy
python -m ruff check src tests
python -m pip_audit --skip-editable
python -m compileall -q src tests
git diff --check
python -m build
```

Coverage must remain at least 90% overall. New persistence and concurrency code
must add focused branch and failure-path tests rather than relying only on the
aggregate threshold.

## Test layers

- Domain validation: amounts, dates, text, UUIDs, managed-reference rules
- Services: Account, Category, Transaction, Excel import, Telegram facade
- Reporting: all-time/date periods and Category UUID continuity across rename
  and deactivation
- Repository contracts: identity, ordering, uniqueness, stale writes, rollback
- SQLite infrastructure: schema lifecycle, migration, constraints, locks,
  malformed rows, connection cleanup, and transaction rollback
- Presentation: CLI prompts/dispatch and Telegram authorization/conversations
- Artifacts: Excel compatibility, atomic save behavior, package metadata,
  installed commands, and CI configuration
- Operations: backup/restore validation, overwrite confirmation, rotating
  retention scope, integrity checks, permissions, and failure cleanup

## Isolation

All persistence tests use pytest temporary workspaces. Tests must never access
or mutate the repository's real `data/` directory. Telegram tests use doubles
and must not contact Telegram. Excel tests close workbooks and use temporary
destinations.

## SQLite-only invariant

Tests must construct SQLite repositories or protocol fakes. No compatibility
backend, JSON storage helper, migration flag, or JSON runtime path may be added.
Packaging tests assert the removed modules are not shipped.
