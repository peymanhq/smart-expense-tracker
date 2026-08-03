# Smart Expense Tracker — Development Roadmap

## Vision

The goal of Smart Expense Tracker is to evolve from a simple command-line application into a professional personal finance management system.

Development follows an incremental approach. Each version should improve the application while preserving existing functionality.

---

# Smart Expense Tracker v1.0.0

## Status

Published stable baseline.

## Objectives

Build a stable command-line expense tracker with the core features required for personal finance management.

## Features

- Add income and expense transactions
- View transactions
- Search transactions
- Filter transactions
- Update transactions
- Delete transactions
- Financial reports
- JSON persistence
- Input validation
- Internal UUID
- User-facing Display ID
- Modular project structure

---

# Smart Expense Tracker v1.1.0

## Objectives

Add managed Account and Category workflows, date-based transaction management,
and stronger application and persistence boundaries.

## Status

Released 2026-07-26.

## Implemented Work

- Standalone Account Management
- Add, view, rename, deactivate, and reactivate account workflows
- Persistent account UUID and display-ID state
- Atomic single-document account JSON persistence with legacy migration
- Validated account schema and concurrent-writer locking
- Standalone Category Management
- Income and expense category types
- Add, view, rename, activate, and deactivate category workflows
- Persistent category UUIDs and monotonic `C-####` display-ID state
- Strict category schema validation and locked category mutations
- Date-based Transaction Management
- Selected-date transaction workspace with today and historical entry
- Date-scoped add, view, update, and delete with explicit date movement
- Populated-date browsing
- Transaction application service and repository abstraction
- Schema-versioned, backward-compatible transaction JSON
- Locked transaction mutations and atomic monotonic display-ID allocation
- Exact-date and inclusive date-range search
- Daily and inclusive date-range financial reports
- Deterministic clock injection and shared future-date policy

Optional `category_id` and `account_id` transaction fields are established.
Programmatic managed-reference validation is established in
`TransactionService`, and transaction add/update now select active Accounts and
Categories by display ID. Automatic migration of existing free-text values,
explicit unlinking, and cross-file database constraints remain future work.

---

# Smart Expense Tracker v1.2.0

## Status

Released 2026-07-26.

## Focus

Add a safe, professional Excel reporting output while preserving the existing
application and persistence boundaries.

## Implemented Scope

- Excel transaction export from the CLI
- Transactions, Summary, and Category Summary worksheets
- Resolved managed Account/Category names without exposing internal UUIDs
- Existing-destination confirmation and atomic workbook replacement
- Empty-dataset support and focused workbook/CLI test coverage

Continuous integration, packaging, Excel import, PDF export, workbook charts,
dashboards, multiple currencies, transfers, SQLite, Telegram integration, and
a GUI remain separate future work.

---

# Smart Expense Tracker v1.3.0

## Status

Released 2026-07-26.

## Focus

Add professional Python packaging and continuous integration without changing
application features or persistence formats.

## Implemented Scope

- Canonical `pyproject.toml` project and dependency metadata
- Standards-based source and wheel builds over the existing flat modules
- Installed `expense-tracker` command delegating to `main.main`
- Preserved `python3 src/main.py` development execution
- GitHub Actions test/build matrix for Python 3.10 and 3.13
- Packaging, entry-point, import-safety, and runtime-workspace tests
- Documentation and isolated install/build verification

Package publication, linting, type checking, coverage thresholds, release
automation, and application features remain future work.

---

# Smart Expense Tracker v1.4.0

## Status

Released 2026-07-27.

## Focus

Deliver a professional new-transaction Excel input workflow while preserving
the CLI → service → repository → atomic JSON architecture.

## Implemented Scope

- Strict `.xlsx` and `Transactions` worksheet contract
- Canonical required headers with legacy export-date header compatibility
- Complete row validation with physical Excel row numbers
- Active Account and Category name resolution
- Category/transaction-type compatibility
- Stored and within-workbook duplicate conflicts
- Counts and financial-impact preview before confirmation
- One-lock, one-replacement ordered bulk transaction persistence
- New UUID, display-ID, and timestamp generation
- Instructions/Transactions/Reference Data import template
- Named-range Account dropdowns, Type-dependent active Category dropdowns, and
  workspace-aware output
- CLI, parser, service, repository, workbook, and failure-atomicity tests

The scope excludes `.xls`, `.xlsm`, CSV import, updates through Excel,
identifier/timestamp restoration, partial import, managed-record creation,
transfers, and multiple currencies.

---

# Completed Version 1 Stabilization Work

- Core command-line transaction workflows
- Automated tests for version 1 with pytest
- Controlled storage error handling
- Display-ID reuse prevention
- Search by display ID
- Accurate update result handling
- Safe atomic JSON persistence
- Legacy JSON compatibility
- README and release documentation updates

---

# Smart Expense Tracker v1.5.0

## Status

Released 2026-08-03 (`1.5.0`).

## Implemented Scope

- SQLite implementations of all Account, Category, and Transaction repositories
- Backend-neutral application composition with SQLite as the default storage backend
- Explicit JSON compatibility selection at CLI startup
- Automatic migration when JSON files exist and the SQLite database does not
- Import-safe backend configuration with no database creation on module import
- Locked, validated JSON snapshot migration into one SQLite transaction
- Preservation of UUIDs, display IDs, timestamps, managed references, and
  next-display-ID counters
- Idempotent retry after a completed identical migration
- Rejection of non-empty divergent destinations and complete rollback on
  constraint failures
- Installed validated SQLite backup and explicitly confirmed offline restore
- Documented cutover and rollback runbook
- Read-only migration rehearsal against the current workspace with complete
  cross-backend record equality and unchanged JSON source metadata

# Smart Expense Tracker v1.5.1

## Status

Released 2026-08-03 (`1.5.1`).

## Implemented Scope

- Exact `Decimal` amounts throughout the domain and financial calculations
- JSON schema version 4 with canonical decimal-text amounts
- Atomic SQLite schema version 1 to 2 migration from `REAL` to decimal `TEXT`
- Static type checking across all source modules in CI
- A 90% minimum source-coverage gate in CI
- MIT package licensing metadata

## Next Planned Version

v1.6.0

Primary focus:

- Telegram Bot MVP
- Register income and expense from Telegram
- Financial summary through Telegram
- Excel export from Telegram

---

# Version 2.0

## Objectives

Harden and evolve the primary SQLite storage engine.

## Planned Work

- Release automation for the documented migration and rollback workflow
- Automated backup rotation, retention, and off-device policy
- Schema upgrade migrations
- Better search performance

JSON will remain available as an import and export format.

---

# Version 2.1

## Objectives

Expand financial management capabilities.

## Planned Work

- Transfers between accounts
- Opening balances
- Tags
- Better filtering

---

# Version 2.2

## Objectives

Improve reporting.

## Planned Work

- Monthly reports
- Spending analysis
- Income analysis
- Cash-flow reports
- Charts
- Financial dashboard

---

# Version 2.3

## Objectives

Excel integration.

## Planned Work

- Additional Excel export formats
- Dashboard generation
- Additional reporting templates

The safe `.xlsx` new-transaction import and its entry template were delivered
ahead of this broader reporting milestone.

---

# Version 2.4

## Objectives

Telegram integration.

## Planned Work

- Telegram Bot
- Transaction entry from Telegram
- Notifications
- Quick balance lookup
- Expense logging through chat

Telegram should reuse the same validation and application services as the CLI.

---

# Version 2.5

## Objectives

Desktop application.

## Planned Work

- GUI
- Forms
- Tables
- Charts
- Dashboard
- Settings

---

# Version 3.0

## Objectives

Professional finance platform.

## Planned Work

- Multiple currencies
- Budget planning
- Financial goals
- Recurring transactions
- Attachments
- API
- Cloud synchronization
- Plugin architecture

---

# Guiding Principles

Every version should:

- Have a clear objective.
- Deliver working software.
- Preserve backward compatibility.
- Improve maintainability.
- Include documentation updates.
- Include tests whenever possible.

Large rewrites should be avoided.

Development should remain incremental.
