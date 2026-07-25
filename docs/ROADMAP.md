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

# Version 1.1.0

## Objectives

Continue improving reliability and internal design after v1.0.0 is published.

## Status

In development.

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

## Planned Work

- Replace `float` with `Decimal`
- Better exception hierarchy
- Refactor `main.py`
- Better project packaging
- Continuous Integration (CI)

Category selection during transaction entry, a `category_id` or `account_id`
transaction field, migration of existing free-text values, account/category
integration with transactions, transfers, Decimal money, Excel/PDF export,
charts/dashboard, SQLite, multiple currencies, multiple accounts, and a GUI
remain future work. Version 1.1.0 is still in development.

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

# Version 2.0

## Objectives

Replace JSON as the primary storage engine.

## Planned Work

- SQLite database
- Data migration
- Backup and restore
- Repository implementation
- Better search performance
- Atomic transactions

JSON will remain available as an import and export format.

---

# Version 2.1

## Objectives

Expand financial management capabilities.

## Planned Work

- Multiple accounts
- Transfers between accounts
- Opening balances
- Categories management
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

- Excel import
- Excel export
- Dashboard generation
- Templates
- Batch transaction import

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
