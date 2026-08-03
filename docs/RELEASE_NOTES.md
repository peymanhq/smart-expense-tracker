# Smart Expense Tracker v1.5.0

Released 2026-08-03.

v1.5.0 makes SQLite the default storage backend while retaining JSON as an
explicit compatibility backend. Existing valid JSON workspaces migrate
automatically on first startup when no SQLite database exists.

## Storage and Migration

- Use SQLite by default through the same Account, Category, Transaction, and
  Excel application-service boundaries.
- Automatically validate and migrate existing JSON records and display-ID
  counters without changing or deleting the JSON source files.
- Stop startup on invalid legacy JSON instead of creating an empty database.
- Keep JSON available explicitly through
  `SMART_EXPENSE_TRACKER_BACKEND=json` for compatibility.

## Backup and Restore

- Create validated atomic SQLite backups with the installed
  `expense-tracker-storage` command.
- Restore a validated backup offline with explicit overwrite confirmation.
- Preserve the live database when validation or atomic replacement fails.

## Release Verification

The v1.5.0 release suite contains 610 passing tests. Coverage includes all
SQLite repositories, default and compatibility backend selection, automatic
and explicit migration, rollback on migration failure, backup and restore,
packaging, installed commands, Excel workflows, and all earlier behavior.

---

# Smart Expense Tracker v1.4.0

Released 2026-07-27.

v1.4.0 adds a safe Excel transaction input path without making Excel a
persistence layer.

## User-visible Improvements

- Generate a workspace-aware import template with Instructions, Transactions,
  and active Account/Category Reference Data.
- Use dependent Category dropdowns: Income rows show active Income Categories,
  while Expense rows show active Expense Categories.
- Import transactions from `.xlsx` files with a required `Transactions`
  worksheet and required headers.
- Resolve Account and Category names to active managed records and enforce
  Category/type compatibility.
- Validate every row and see each issue with its physical Excel row number.
- Preview transaction counts, income, expense, and net balance impact before
  confirmation.
- Import all valid rows through one all-or-nothing mutation, or import none.
- Receive explicit conflicts for stored duplicates and earlier matching
  workbook rows.
- Generate new UUIDs, timestamps, and monotonic display IDs in workbook row
  order rather than trusting imported identity.

The required worksheet is `Transactions`, with `Date`, `Type`, `Amount`,
`Description`, `Account`, and `Category` columns. Additional exported metadata
columns are ignored. Imported UUIDs, Display IDs, and timestamps are never
trusted; the application generates new identity and metadata.

Template generation and Excel import remain reusable application services
without CLI input/output coupling, allowing a future adapter such as Telegram
to invoke the same boundaries.

## Confirmed Limitations

- No `.xls` or `.xlsm` import
- No CSV import
- No partial import
- No transaction updates through Excel
- No UUID, display-ID, or timestamp restoration
- No automatic Account or Category creation
- No transfers
- No multiple currencies

## Development Verification

The v1.4.0 release suite contains 471 passing tests. Coverage includes workbook
structure and types, active managed-reference resolution, duplicate keys,
late-conflict protection, monotonic ordered IDs, one-lock atomic persistence,
save-failure preservation, Type-dependent template dropdowns, CLI confirmation,
packaging, and all earlier behavior.

---

# Smart Expense Tracker v1.3.0

Released 2026-07-26.

v1.3.0 adds professional delivery infrastructure while preserving every
financial workflow and persistence schema from v1.2.0.

## User-visible Improvements

- Install and start the application with `expense-tracker`.
- Continue using `python3 src/main.py` during repository development.
- Build standards-compliant source and wheel distributions from
  `pyproject.toml`.
- Receive automated test and build feedback through GitHub Actions.

The installed command delegates directly to the existing `main.main`
orchestration callable. It does not duplicate menus, bypass services, expose
UUIDs, or change Account, Category, Transaction, report, or Excel behavior.

Runtime JSON and default Excel files remain workspace-local under `data/` and
`exports/`. No package publication, database migration, exact-money migration,
or financial feature is part of this version.

## Development Verification

The v1.3.0 release suite contains 391 passing tests. CI and local release
checks cover Python compilation, changed-content whitespace checks, source and
wheel builds, editable installation, and deterministic installed-command
startup and exit.

---

# Smart Expense Tracker v1.2.0

Released 2026-07-26.

v1.2.0 adds atomic Excel reporting with Transactions, Summary, and Category
Summary worksheets. It resolves managed names without exposing UUIDs, confirms
overwrites, and preserves all JSON and financial behavior. The release commit
passes 385 tests.

---

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
- No transfers, multi-currency support, PDF export, charts, GUI, or SQLite
  persistence.

## Later Versions

v1.2.0 subsequently delivered Excel transaction, financial, and category
summaries. v1.3.0 delivered packaging and CI. v1.4.0 delivered Excel import
and its guided template; PDF output, charts, and exact-money migration remain
separate work.
