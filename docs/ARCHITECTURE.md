# Smart Expense Tracker — Architecture

## System shape

```text
CLI / Telegram / Excel adapters
              |
              v
Application services
              |
              v
Repository protocols
              |
              v
SQLite repository adapters
              |
              v
SQLiteDatabase + versioned schema
```

SQLite is the only persistence engine. Application services depend on Account,
Category, and Transaction repository protocols and contain no SQL. Presentation
adapters contain no persistence access.

## Main boundaries

- `application.py`: composition for one workspace
- `account_service.py`, `category_service.py`, `transaction_service.py`:
  validation and use-case orchestration
- `*_repository.py`: persistence protocols and backend-neutral errors
- `sqlite_*_repository.py`: SQLite mapping and atomic mutations
- `sqlite_database.py`: connections and transaction boundary
- `sqlite_schema.py`: versioned initialization, migration, and validation
- `main.py`: terminal adapter and selected-date session
- `telegram_application.py`: Telegram-facing application facade
- `telegram_handlers.py`: authorization and conversation presentation
- `excel_*`: workbook adapters and import orchestration
- `search.py`, `report.py`: pure selection and aggregation logic

## Persistence contract

Every connection enables foreign keys and a busy timeout. Writes use
`BEGIN IMMEDIATE`, commit exactly once, roll back application or SQLite errors,
and close the connection. Repository row mapping revalidates persisted values.

Schema version 2 stores Account, Category, and Transaction UUIDs; independent
monotonic display-ID counters; managed foreign keys; canonical decimal text;
financial dates; and UTC timestamps. Version 1 REAL amounts migrate atomically
to version 2.

Account, Category, and Transaction replacement use optimistic concurrency: a
caller provides the expected model and a stale mutation is rejected.

## Data semantics

- `transaction_date` is the financial date.
- `created_at` and `updated_at` are audit metadata, never reporting dates.
- Amounts are positive `Decimal` values; type determines income or expense.
- Account and Category UUIDs are authoritative managed references.
- Stored names are historical snapshots and fallbacks.
- Category reports filter by managed UUID, so rename and deactivation preserve
  historical reporting continuity.
- Deactivation preserves historical references; deletion is restricted.

## Operational boundary

Runtime paths are workspace-relative. Backup uses SQLite's online backup API,
validates temporary output, and atomically replaces the destination. Managed
rotation retains only the configured newest timestamped backups. Restore is
offline because replacing a database path cannot coordinate existing processes.

Installed commands enter through the `smart_expense_tracker` namespace. Flat
module imports remain temporarily packaged as a compatibility surface for the
1.x line; their removal requires a major-version migration.

JSON compatibility code is not part of the current architecture. Historical
decisions remain in `DECISIONS.md` for traceability only.
