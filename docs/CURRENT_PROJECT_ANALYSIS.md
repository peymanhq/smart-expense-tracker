# Current Project Analysis

## Verified baseline

Smart Expense Tracker is a local SQLite-only application with CLI, Telegram,
Excel, and storage-maintenance adapters over shared application services. The
legacy JSON backend, migration path, backend flags, and dedicated tests are no
longer shipped. Existing user-owned JSON files are never deleted automatically.

The current gate covers 494+ tests, at least 90% source coverage, mypy, Ruff,
compile checks, dependency audit, package build, and installed-command smoke
tests.

## Strengths

- Explicit adapter → service → repository → SQLite boundaries
- Exact `Decimal` amounts and deterministic clock injection
- Atomic writes, foreign keys, monotonic display IDs, and stale-write rejection
- Repository-side filtered queries, pagination, and financial aggregation
- Atomic Excel import/export and validated SQLite backup/restore
- Private runtime permissions and full/quick integrity commands
- Network-free deterministic Telegram tests

## Remaining gaps and debt

| Priority | Gap | Impact | Chosen treatment |
|---|---|---|---|
| P1 | No currency semantics | Totals are unitless | Introduce explicit Money/currency contracts before multi-currency reports |
| P1 | No opening balance or transfer model | Account balances are incomplete | Add dedicated account balance and transfer boundaries; do not encode transfers as income/expense |
| P1 | Backups remain local | Device loss is unrecoverable | Keep local rotation in-app; document and automate an external off-device copy operationally |
| P2 | `main.py` is a large presentation adapter | Higher change cost | Extract command/session objects incrementally without moving business rules into the CLI |
| P2 | Flat 1.x modules remain packaged | Import-name collision risk | Namespaced entry points now; remove compatibility modules only in 2.0 |
| P2 | Persistence branch coverage is uneven | Rare failure regressions | Require focused migration, lock, corruption, and rollback tests alongside the 90% global gate |
| P3 | Logging is human text only | Weak diagnostics | Add structured local events with secret/financial-data redaction |

## Evidence from this remediation

- Transaction optimistic concurrency now matches Account and Category.
- Search, filter, summaries, CLI reports, and Telegram summaries use repository
  query contracts instead of loading the full transaction table.
- Schema validation runs physical and foreign-key checks.
- Backup, database, and temporary financial artifacts use private permissions.
- Ruff, pip-audit, and a non-vulnerable pytest line are enforced in CI.
- Installed commands now resolve through `smart_expense_tracker.*` entry points.

The dependency-ordered domain design is recorded in `V2_DESIGN.md`.
