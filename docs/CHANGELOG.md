# Changelog

All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog** and follows **Semantic Versioning**.

---

## [Unreleased]

No changes yet.

---

## [1.1.0] - 2026-07-26

### Added

- Account creation, listing, renaming, deactivation, and reactivation
- Internal account UUIDs and user-facing `A-0001` display IDs
- Separate atomic JSON persistence for account records and display-ID state
- Account Management CLI submenu
- Focused automated coverage for account rules and persistence
- Income/expense category creation, listing, renaming, activation,
  and deactivation
- Internal category UUIDs and persistent `C-0001` display IDs
- Strict category schema and uniqueness validation
- Locked category mutations with atomic category-list and counter writes
- Category Management CLI submenu with numbered Income/Expense selection
- Date-based Transaction Management with a selected-date workspace that starts
  on today and supports historical entry
- Date-scoped add, view, update, and delete workflows, including explicit
  transaction-date movement and populated-date browsing
- `TransactionService`, `TransactionRepository`, and
  `JsonTransactionRepository` boundaries with injected date/time providers
- Transaction schema version 2 with typed financial dates and optional UTC
  creation/update metadata
- Exact-date and inclusive date-range search, including one-sided ranges in the
  Python API
- Daily and inclusive date-range reports with transaction counts
- Deterministic coverage for date policy, clocks, locking, concurrency,
  compatibility, CLI workspaces, search, and reports
- Optional managed Account and Category UUID references in transaction schema
  version 3
- Public Account and Category list/lookup query APIs
- Managed Account/Category selection in transaction add and update CLI flows

### Changed

- Shared the atomic JSON writer between transaction and account persistence
- Consolidated account records and display-ID metadata into one atomic document
- Added automatic migration from legacy account-list and state files
- Normalized account display-ID input and Unicode account names
- Paused after account operations until the user returns to the submenu
- Added deterministic category ordering by transaction type and display ID
- Stored managed references alongside required Account and Category name
  snapshots while preserving legacy free-text compatibility
- Made `transaction_date` the financial date used by CRUD, search, and reports
- Moved transaction date/timestamp rules into `TransactionService` and JSON
  responsibilities into the repository/storage boundary
- Made search ordering deterministic by newest financial date and ascending
  numeric display ID
- Preserved legacy `date` records and missing historical timestamps without
  rewriting files on read
- Documented metadata-only updates as explicit update events that advance
  `updated_at`
- Accepted numeric `YYYY-M-D` and `YYYY-MM-DD` transaction-date input and
  normalized valid dates to canonical ISO form

### Fixed

- Prevented inactive-account renames from triggering active-name conflicts
- Prevented a failed account-state write from partially persisting account data
- Prevented reactivation when it would create duplicate active account names
- Prevented concurrent account operations from losing data or reusing IDs
- Rejected malformed fields, invalid UUIDs, and duplicate account identifiers
- Converted invalid UTF-8 and lock-setup failures into controlled storage errors
- Prevented concurrent category additions from losing records or reusing IDs
- Prevented category activation when it would duplicate an active same-type
  name
- Recovered category counter state from stored IDs when the state file is
  missing and rejected malformed or regressed state
- Prevented concurrent transaction creation from losing records or allocating
  duplicate display IDs by locking the complete allocation/write sequence
- Prevented duplicate transaction identities and regressed display-ID metadata
  from being written by validating complete candidate documents before atomic
  replacement
- Preserved transaction UUID, display ID, financial content, and legacy
  `created_at=None` semantics across updates
- Rejected future financial dates, ambiguous exact/range queries, and reversed
  ranges through one shared policy
- Preserved values already entered during invalid transaction-date retries in
  the update workflow
- Rejected missing, inactive, or type-incompatible newly selected managed
  transaction references while preserving inactive historical references

### Testing

- Confirmed 360 passing pytest tests in the release commit
- Confirmed Python compilation, whitespace-safe diffs, and unchanged runtime
  JSON data

### Documentation

- Updated the README, architecture, decisions, roadmap, test plan, changelog,
  release notes, and current project analysis for the v1.1.0 release

---

## [1.0.0] - 2026-07-24

### Added

- Add income and expense transactions
- View, search, filter, update, and delete transactions
- Financial summary reports
- JSON persistence and input validation
- Internal UUIDs and user-facing display IDs
- Modular project structure
- Persistent monotonic display-ID metadata
- Exact, case-insensitive display-ID lookup for user workflows
- Backward-compatible loading of legacy list-only JSON files
- A 27-test pytest regression suite using temporary data files

### Changed

- Shared display-ID lookup across search, update, and deletion flows
- Preservation of the existing internal UUID and display ID during updates
- Flushed same-directory temporary files and atomic `os.replace` for JSON saves

### Fixed

- Prevented reuse of the highest display ID after its transaction is deleted
- Corrected update result handling for missing records
- Added controlled handling for malformed and structurally invalid JSON
- Cleaned up temporary files after failed writes while preserving previous data

### Testing

- Confirmed 27 passing pytest tests
- Confirmed Python compilation and `git diff --check`
- Confirmed CLI startup and clean exit, add/delete display-ID sequencing,
  legacy JSON loading, and preservation after a simulated replacement failure
- Confirmed `data/transactions.json` remained unchanged during verification

### Documentation

- Prepared README and release documentation for the planned v1.0.0 release

---

## Versioning

This project follows Semantic Versioning.

```text
MAJOR.MINOR.PATCH
```

Example:

```text
1.0.0
```

- MAJOR: Breaking changes
- MINOR: New features
- PATCH: Bug fixes
