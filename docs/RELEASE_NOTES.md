# Smart Expense Tracker v1.1.0

Released 2026-07-26.

Smart Expense Tracker v1.1.0 expands the local CLI from transaction tracking
into managed accounts, managed income/expense categories, and date-based
financial workflows. It also strengthens the application and persistence
boundaries while retaining compatibility with v1.0.0 transaction data.

## Major Features

### Account Management

- Add, view, rename, deactivate, and reactivate accounts.
- Retain stable internal UUIDs and monotonic display IDs such as `A-0001`.
- Enforce active-name uniqueness while allowing inactive-name reuse.
- Validate persisted records and protect complete mutations with locking and
  atomic JSON replacement.

### Category Management

- Manage separate income and expense categories.
- Add, view, rename, activate, and deactivate categories.
- Retain stable UUIDs and monotonic display IDs such as `C-0001`.
- Enforce active-name uniqueness within transaction type and deterministic
  type/display-ID ordering.
- Validate persisted records and lock complete mutations.

### Managed Transaction References

Transaction schema version 3 can store optional Account and Category UUIDs
alongside required name snapshots. Transaction add and update CLI workflows
list active managed records and accept their display IDs, then pass stable
UUIDs to `TransactionService`. Newly selected references must exist and be
active, and categories must match the transaction type. Unrelated updates
preserve inactive historical references.

### Date-based Transaction Management

- Work in a selected financial date that starts on today.
- Add, view, update, delete, and explicitly move transactions by financial date.
- Browse dates that contain transactions.
- Search exact dates and inclusive ranges.
- Produce all-time, daily, and inclusive range reports using
  `transaction_date`, never metadata timestamps.
- Accept numeric `YYYY-M-D` or `YYYY-MM-DD` input, normalize valid calendar
  dates to `YYYY-MM-DD`, and reject future dates.

## Validation and Reliability

- Transaction workflows use an application service and repository abstraction.
- Account, Category, and Transaction mutations use cross-process locks.
- JSON writes use flushed same-directory temporary files and atomic replacement.
- Transaction data remains schema-versioned and backward compatible.
- UUID/display-ID identity is preserved across updates.
- Invalid-date retries preserve values already selected or entered for an
  update.

## Verification

The v1.1.0 release commit passes all 360 pytest tests. Python compilation and
`git diff --check` also pass. Tests use temporary paths or in-memory fakes and
do not modify runtime JSON data.

## Upgrade and Compatibility Notes

No manual transaction-data migration is required. Legacy top-level transaction
lists, schema versions 1 and 2, and legacy `date` fields remain readable. The
next successful transaction mutation writes schema version 3 with explicit
nullable managed references. Existing name-only transactions remain usable and
may be linked to active managed records during update.

## Known Limitations

- Local, single-user CLI only; no authentication or synchronization.
- Separate JSON files and locks provide soft rather than database-level
  referential integrity.
- Explicit managed-reference unlinking and automatic legacy reconciliation are
  not implemented.
- Amounts still use `float`.
- No transfers, multi-currency support, Excel/PDF export, charts, GUI, or
  SQLite persistence.

## Next Planned Version

v1.2.0 is in development. Its implemented Excel reporting scope exports all
transactions plus financial and category summaries through a new CLI option.
It uses resolved managed names, protects existing destinations with explicit
confirmation, and writes `.xlsx` files atomically. Excel import, PDF output,
charts, exact-money migration, CI, and packaging remain separate work.
