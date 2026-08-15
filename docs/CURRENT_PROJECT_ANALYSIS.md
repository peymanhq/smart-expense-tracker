# Smart Expense Tracker — Current Project Analysis

## Executive Summary

Smart Expense Tracker v1.5.1 is the current released version. SQLite is now
the default storage backend, while JSON remains available through an explicit
compatibility mode. The complete Account, Category, and Transaction repository
set supports both storage backends through the same application-service layer.
Automatic non-destructive JSON migration, validated SQLite backup, and offline
restore are fully integrated without changing the application-service or Excel
workflow contracts.

The transaction path now has explicit boundaries:

```text
main.py
    -> TransactionService
    -> TransactionRepository
       ├── SQLiteTransactionRepository / SQLiteDatabase
       └── JsonTransactionRepository / storage.py (compatibility mode)
```

Excel import reaches the same transaction path after a separate workbook
analysis boundary:

```text
main.py
    -> ExcelImportService
    -> TransactionService.add_transactions
    -> TransactionRepository.create_many
    -> selected TransactionRepository
    -> one atomic JSON replacement OR one SQLite transaction
```

The completed date feature adds a selected-date workspace, historical entry,
date-scoped CRUD, explicit date movement, populated-date browsing, exact/range
search, and daily/range reports. Transaction mutations are locked, creation
allocates display IDs atomically, and JSON schema versions 1 through 3 remain
compatible with legacy transaction files.

The v1.5.1 release suite contains 617 passing tests. The current v1.6.0
development suite contains 648 passing tests with a 90% coverage gate and
source-wide static type checking. Persistence, migration, packaging, Excel, and
Telegram tests use temporary workspaces or network-free test doubles and do not
modify runtime data.

## Current Architecture

### Presentation

`main.py` owns terminal input/output and the active workspace date. The active
date starts from an injected today provider, lasts only for one Transaction
Management session, and is not persisted.

The CLI does not allocate transaction display IDs, generate timestamps, or
access backend records directly. SQLite is selected by default when the CLI
starts; `SMART_EXPENSE_TRACKER_BACKEND=json` selects compatibility mode.
Importing `main.py` still creates no data files.

### Application

`TransactionService` owns:

- future financial-date rejection;
- injected today and UTC clock behavior;
- add, date-scoped update/delete, and date movement workflows;
- the distinction between global not-found and active-date mismatch;
- creation/update timestamp semantics.
- optional managed Account/Category resolution, active-selection rules, and
  managed category/type compatibility.

Calling update with no editable values is a metadata-only update: financial
content remains unchanged and `updated_at` advances.

### Domain and Pure Logic

`Transaction` is a typed dataclass. `transaction_date` is the financial date.
Optional `created_at` and `updated_at` values are timezone-aware UTC metadata
and are never used to select financial periods. Optional `account_id` and
`category_id` values hold canonical UUID references, while the required account
and category names remain stored snapshots and fallbacks.

`search.py` and `report.py` remain pure. Search supports exact, inclusive
closed-range, and one-sided API date criteria with AND semantics. Reports reuse
the same date selection before aggregation.

### Repository and Persistence

`TransactionRepository` defines the operations required by the service.
`JsonTransactionRepository` and `SQLiteTransactionRepository` implement the
same contract. `build_application()` composes the selected repository family
without introducing backend access into application services or presentation
code.

Complete create, replace, delete, and compatibility mutations hold a
cross-process lock across read-modify-write. Creation performs the following
under one lock:

1. Load and validate the latest document.
2. Read `metadata.next_display_id`.
3. Allocate the display ID.
4. Append the finalized transaction.
5. Advance the counter.
6. Validate the complete candidate document.
7. Atomically replace the JSON file.

Display IDs are global across all dates and are never reused after deletion.
Duplicate internal IDs, duplicate display IDs, and counters behind stored IDs
fail before a replacement.

Bulk creation validates every ordered request before mutation. Under one lock,
the repository rechecks deterministic managed duplicate keys, allocates
consecutive display IDs, advances metadata once, validates the complete
candidate document, and performs one atomic replacement. This preserves
all-or-nothing behavior even when persistence fails or a matching concurrent
insert occurs after preview.

## Compatibility

Transaction schema version 4 stores `transaction_date`, timestamps, and
optional Account and Category UUID references. Missing schema metadata is
treated as version 1. Schema versions 1 and 2, legacy top-level lists, and
legacy `date` fields remain readable. Missing reference fields load as `None`.

Matching `date` and `transaction_date` fields are accepted; conflicts fail.
Missing historical timestamps load as `None`, are never invented, and
`created_at=None` remains missing after an update. Reads never migrate data.
The next successful mutation writes schema version 4, stores amounts as
canonical decimal text, and represents missing references explicitly as JSON
`null`. Schema version 3 remains readable.

Unsupported future schema versions and malformed records raise controlled
storage errors instead of being skipped or overwritten.

## Strengths

- Clear CLI, application-service, repository, and storage responsibilities
- Deterministic clock injection and shared financial-date policy
- Stable UUID identity and global monotonic display IDs
- Locked mutations plus same-directory atomic replacement
- Backward-compatible schema evolution without read-time rewrites
- Pure, reusable search and reporting functions
- Isolated Account and Category persistence
- Broad deterministic test coverage using disposable data paths

## Remaining Risks and Deferred Work

### Managed References

Transactions can store optional managed-record UUIDs alongside required
snapshot names. `TransactionService` receives public UUID lookup callables from
application composition. Newly supplied references must exist and be active;
managed category types must match. Preserved inactive historical references are
not revalidated during unrelated updates, and managed snapshots cannot be
edited without a new reference.

Transaction add and update now list active records by display ID and submit the
selected UUIDs. Categories are listed for the resulting transaction type.
Empty update selections preserve historical references, including inactive
ones, and legacy snapshot-only records can be linked by choosing an active
record. Explicit unlinking and automatic migration of historical snapshot-only
values remain future work.

Account, Category, and Transaction data use separate files and locks under the
JSON compatibility backend, so cross-file referential integrity is deliberately
soft there. Primary SQLite storage enforces managed-reference foreign keys.

### Flat JSON Limits

Locking prevents lost read-modify-write mutations, but every JSON transaction
change still rewrites the whole file. SQLite is primary with atomic SQL
transactions and indexed queries. The first SQLite schema upgrade is
implemented; automated backups and merge-style migration are not implemented.

### Operational Recovery

`expense-tracker-storage` creates validated atomic SQLite backups and restores
them only with explicit overwrite confirmation. Restore remains an offline
operation because atomic file replacement cannot coordinate already-running
external processes. Immediate rollback may return to preserved JSON only before
SQLite receives new writes; later recovery uses a SQLite backup. Rotation,
retention, encryption, and off-device copies remain operational policy.

### Project Tooling

`pyproject.toml` now defines a PEP 517 setuptools build over the existing flat
modules, runtime dependencies, the `expense-tracker` entry point, and the
development extra. GitHub Actions checks tests with a 90% source-coverage
floor, static types across all source modules, compilation, changed-content
whitespace, package builds, and a deterministic installed-command smoke test
on Python 3.10 and 3.13.

Linting, package publication, and release automation remain deliberately
deferred.

### Excel Reporting Adapter

`excel_exporter.py` receives detached transactions and managed-name mappings
from the CLI/service boundary. It creates Transactions, Summary, and Category
Summary worksheets, reuses pure report calculations, and saves through
same-directory temporary output plus atomic replacement. It never reads JSON,
depends on a concrete repository, or mutates application state.

### Excel Import and Template Adapters

`excel_import.py` enforces the `.xlsx`, Transactions worksheet, and normalized
header contracts in read-only calculated-value mode. It returns parsed rows
and physical-row issues without domain persistence entities.

`ExcelImportService` resolves active names, enforces Category/type
compatibility, applies the existing date policy, and detects duplicates using
date, type, amount, normalized description, Account UUID, and Category UUID.
Valid previews persist once through the generic transaction bulk-create
boundary. Identity/timestamp columns are ignored.

`excel_template.py` generates Instructions, an empty formatted entry sheet, and
active Reference Data with named-range dropdowns. Category validation selects
the stable Income or Expense range from each row's Type. Shared workbook
constants and atomic output behavior live in `excel_workbook.py`.

Template generation and `ExcelImportService` remain callable without terminal
input or output. `main.py` remains the CLI adapter; the Telegram adapter reuses
these boundaries without owning workbook or persistence logic.

### Telegram Adapter

The v1.6.0 work adds a separate single-user Telegram adapter. `telegram_bot.py`
composes the configured SQLite workspace and owns foreground long polling;
`telegram_handlers.py` owns authorization and the guided conversation; and
`telegram_application.py` reuses existing application services and pure report
calculations. No Telegram code accesses SQL or JSON directly, and `main.py`
remains unchanged.

The guided add flow accepts today's income or expense only, lists active
Accounts and type-compatible active Categories, requires Amount and Description,
and persists after confirmation. Balance is all-time and summary is limited to
today in the configured IANA timezone. Update, delete, Excel delivery, and
multiple users remain deferred.

Charts and PDF output remain deferred.

## Recommended Next Work

Keep future work scoped and incremental:

1. Complete live manual Telegram verification with a disposable bot token.
2. Define backup rotation/retention and release rollback policy.
3. Add rollback and corruption tests for each future SQLite schema upgrade.
4. Add linting as a separately scoped tooling change.

Multiple currencies, transfers, dashboards, a GUI, and broader external
interfaces remain roadmap items.
