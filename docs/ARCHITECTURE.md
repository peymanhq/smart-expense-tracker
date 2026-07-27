# Smart Expense Tracker — Architecture

## Overview

Smart Expense Tracker is designed as a modular Python application with a clear separation of responsibilities.

The project follows an incremental architecture. Each version improves the internal design while preserving existing functionality.

The long-term objective is to build a maintainable, testable, and extensible finance application.

---

## Current Architecture (v1.5.0 development)

The current application follows this structure:

```text
User
  │
  ▼
main.py
  │
  ├── application.py
  │     ├── account_service.py
  │     │     └── account_repository.py
  │     ├── category_service.py
  │     │     └── category_repository.py
  │     ├── transaction_service.py
  │     │     └── transaction_repository.py
  │     └── excel_import_service.py
  ├── account_storage.py
  ├── category_storage.py
  ├── storage.py
  ├── validators.py
  ├── report.py
  ├── excel_exporter.py
  ├── excel_workbook.py
  ├── excel_import.py
  ├── excel_import_service.py
  ├── excel_template.py
  ├── search.py
  ├── formatter.py
  ├── transaction.py
  └── json_storage.py
        │
        ▼
  accounts.json / categories.json / categories_state.json / transactions.json
```

### Module Responsibilities

| Module | Responsibility |
|---------|----------------|
| `main.py` | CLI interaction and workflow orchestration |
| `application.py` | Typed construction of services and JSON repositories for one workspace |
| `account.py` | Account data model |
| `account_service.py` | Account validation and add, rename, deactivate, and activate rules |
| `account_repository.py` | Account repository protocol and JSON implementation |
| `account_storage.py` | Validated, locked account persistence and legacy migration |
| `category.py` | Passive standalone Category data model |
| `category_service.py` | Category validation, listing, and mutation rules |
| `category_repository.py` | Category repository protocol and JSON implementation |
| `category_storage.py` | Validated, locked category-list and counter persistence |
| `json_storage.py` | Shared atomic JSON writing |
| `persistence_errors.py` | Backend-neutral persistence failure exposed to orchestration |
| `sqlite_database.py` | Inactive SQLite path, connection, and transaction foundation |
| `sqlite_schema.py` | Inactive SQLite schema version 1 initialization and validation |
| `transaction.py` | Typed, passive Transaction data model |
| `transaction_factory.py` | Transaction creation |
| `transaction_service.py` | Transaction workflows, date rules, and timestamp behavior |
| `transaction_repository.py` | Repository protocol and JSON implementation |
| `clock.py` | Default and injectable today/UTC clock providers |
| `date_policy.py` | Shared exact/range shape and future-date policy |
| `validators.py` | Input validation |
| `storage.py` | Versioned schema handling, locking, validation, and JSON persistence |
| `report.py` | Pure financial aggregation over selected transactions |
| `excel_exporter.py` | In-memory workbook construction, Excel formatting, and atomic `.xlsx` saving |
| `excel_workbook.py` | Shared Excel header/style contract, destination validation, and atomic workbook saving |
| `excel_import.py` | Read-only `.xlsx` parsing and row-level structural/type issues |
| `excel_import_service.py` | Managed-name resolution, duplicate analysis, preview totals, and import orchestration |
| `excel_template.py` | Instructions, entry, and active-reference workbook generation |
| `search.py` | Pure date/text filtering, ordering, and display-ID lookup |
| `formatter.py` | Terminal formatting |
| `id_generator.py` | UUID creation and display-ID formatting, parsing, and legacy-state calculation |

`main.py` owns terminal interaction and date-workspace session state.
`application.py` owns dependency construction for the current JSON backend.
Application services coordinate workflows without terminal or JSON access.
The Account, Category, and Transaction repository protocols isolate the
application layer from the current JSON implementations.

### Excel Export Data Flow

```text
CLI (`main.py`)
  -> Transaction and managed-record query services
  -> transactions + Account/Category name mappings
  -> `excel_exporter.py` + pure `report.py` calculations
  -> atomic `.xlsx` reporting artifact
```

The CLI owns destination input and overwrite confirmation. It obtains all
transactions through `TransactionService`, obtains active and inactive managed
records through the established read-only service queries, and passes detached
domain data and UUID-to-name mappings to the exporter. Legacy records without
UUIDs retain their stored name snapshots; a referenced UUID that cannot be
resolved produces a neutral blank rather than an invented name.

`excel_exporter.py` owns workbook sheets, cell population, number/date formats,
column widths, filters, frozen headers, and safe saving. It reuses
`calculate_financial_summary()` for totals and never reads JSON or depends on
`JsonTransactionRepository`. Excel therefore remains an output adapter, not a
persistence implementation. The exporter writes a same-directory temporary
workbook and atomically replaces the final path only after a complete save.

The application factory composes `TransactionService` with the public Account
and Category UUID query functions. The service requires an explicitly supplied
repository and receives only lookup callables; it does not know managed-record
file paths or storage formats.

### Excel Import Data Flow

```text
CLI (`main.py`)
  -> `ExcelImportService.analyze(path)`
     -> `excel_import.py` read-only/cached-value parser
     -> Account/Category read-only lists and established name keys
     -> `TransactionService` date policy and current transaction query
     -> complete issues or immutable preview
  -> explicit user confirmation
  -> `ExcelImportService.persist(preview)`
     -> one `TransactionService.add_transactions(...)` call
     -> one `TransactionRepository.create_many(...)` mutation
     -> one lock + one validated atomic JSON replacement
```

The parser owns only the external workbook contract. It does not create
`Transaction` entities or read/write JSON. Parsed rows retain physical Excel
row numbers and ignore unrelated identity/timestamp columns.

`ExcelImportService` resolves trimmed Account and Category names with the
existing NFC/case-folded comparison keys. It requires active records and a
Category compatible with the normalized transaction type. It computes the
same deterministic duplicate key for stored and candidate transactions:
financial date, type, float amount, normalized description, Account UUID, and
Category UUID. Resolvable legacy name snapshots participate in the stored
duplicate check.

The service returns every validation and conflict issue before persistence.
Any issue makes the preview non-persistable. Confirmation delegates ordered
requests once to `TransactionService`; the repository rechecks managed
duplicate keys under the mutation lock so a concurrent insert after preview
cannot produce a silent duplicate.

### Excel Import Template Data Flow

```text
CLI destination + overwrite confirmation
  -> active Account/Category query results
  -> `excel_template.py`
  -> shared `excel_workbook.py` atomic output helper
  -> Instructions / Transactions / Reference Data workbook
```

Named worksheet ranges back Account and Category dropdowns, avoiding Excel's
direct-list length and special-character limitations. Stable
`IncomeCategories` and `ExpenseCategories` ranges contain active values only;
each entry row derives its Category list from that row's Type cell. Empty
category groups still resolve to a valid blank range. The template never
contains UUIDs or real transaction rows, and import validation remains
authoritative if a user changes Type without reselecting Category.

Template generation and import analysis/persistence are callable application
services without terminal input or output. `main.py` is the current CLI
adapter; a future messaging adapter can invoke the same boundaries without
moving workbook parsing or JSON persistence into the adapter.

`AccountService` and `CategoryService` own managed-record validation and
business rules. They receive repository protocols and do not accept file
paths, acquire file locks, read JSON, or manage counter files. Small
function-oriented wrappers remain available but likewise require repository
objects.

The services expose public managed-record queries. Account queries list all or
only active records and resolve canonical UUIDs or normalized display IDs.
Category queries add active-state and transaction-type filters while retaining
the established type-then-display-ID ordering. UUID and display-ID lookup
includes inactive records so historical callers can still resolve them.

`JsonAccountRepository` and `JsonCategoryRepository` own the existing JSON
paths, compatibility loaders, mutation locks, atomic writes, and display-ID
allocation. Creation allocates and persists under one lock. Replacement
preserves UUID and display ID, checks that the service's source record is still
current, and rechecks persisted uniqueness inside the protected mutation.
`build_json_application()` constructs these repositories and injects their
services into transaction and Excel workflows. `main.py` consumes the returned
frozen service aggregate and contains no repository construction details.
Supplying a workspace root isolates all JSON data below that root; omitting it
retains the existing current-working-directory-relative `data/` behavior.

---

## Current Workflows

### Transaction Creation

1. `main.py` lists active Accounts and Categories through public query
   boundaries, accepts normalized display-ID selections, and passes their UUIDs
   with the active financial date and entered values to `TransactionService`.
2. The service applies the shared future-date policy, obtains one injected UTC
   timestamp, and uses `transaction_factory.py` for validation and construction.
   Optional managed UUIDs are resolved independently: a supplied reference must
   identify an active record, and its current name becomes the authoritative
   stored snapshot. Omitted references retain legacy free-text behavior.
3. `JsonTransactionRepository` acquires the transaction lock and loads the
   latest document.
4. Under that same lock, it allocates the next global display ID, appends the
   transaction, advances metadata, validates the complete candidate document,
   and invokes the shared atomic JSON writer.

The CLI does not allocate display IDs, access transaction JSON, or generate
timestamps.

Atomic bulk creation follows the same boundary. `TransactionService` validates
every ordered request, re-resolves active managed UUIDs, creates fresh UUIDs
and timestamps, and submits the complete candidate list once. The JSON
repository loads the latest document under one lock, rejects stored or batch
duplicate keys, allocates consecutive display IDs from persisted metadata,
validates the complete candidate document, and atomically replaces the file.
No earlier row can remain persisted after a later-row or write failure.

### Search, Update, and Deletion

The Transaction Management workspace keeps an active date local to one menu
session. It defaults to the injected today, may select an empty historical
date, can browse populated dates, and resets when reopened.

For update and deletion, `TransactionService` first performs a global
display-ID lookup so not-found and outside-active-date errors remain distinct.
Repository mutations then operate by stable internal UUID under a complete
read-modify-write lock. Updates preserve UUID, display ID, and `created_at`,
advance `updated_at`, and may explicitly change `transaction_date`.

Unrelated updates preserve managed UUIDs and their stored snapshots without
revalidating active status, allowing inactive historical references to remain
usable. Selecting a new managed record requires an active lookup. Direct text
changes to a preserved managed snapshot are rejected; callers must supply a new
UUID. A transaction-type change must remain compatible with an existing or new
managed category. Legacy transactions with no category UUID retain their
free-text category during type changes.

The update CLI lists active replacement Accounts and Categories for the
resulting transaction type. Empty selection omits the reference argument, so
inactive or missing historical references can remain unchanged. A legacy
snapshot-only transaction can be linked by selecting an active record. The
service, not the selection list, remains authoritative if status changes
between display and mutation.

`search.py` applies exact, inclusive closed-range, and one-sided-range financial
date selection with AND semantics. `report.py` reuses that pure selection logic
before aggregation. Neither module consults the clock.

### Account Management

`account_service.py` validates account names, rejects duplicate active names,
and coordinates add, rename, deactivate, and activate operations through
`AccountRepository`. Mutations
return an explicit result containing success state, a user-facing message, and
the affected account when applicable. Display-ID lookup normalizes whitespace,
letter case, and numeric padding. Account names use NFC Unicode normalization
plus case-insensitive comparison. Deactivation changes `is_active` while
retaining the record and both identifiers; reactivation restores the same
record unless it would create duplicate active names. Inactive names are
intentionally reusable: a new account or inactive-account rename may match an
active name, but the inactive account cannot be reactivated until the conflict
is resolved.

Public query operations are `list_accounts()`, `get_account_by_id()`, and
`get_account_by_display_id()`. Listing is deterministic by numeric account
display ID and can exclude inactive records. Both lookup operations return
active or inactive records, with UUID lookup requiring canonical UUID text.

### Category Management

`category_service.py` trims and NFC-normalizes names, canonicalizes transaction
types to `income` or `expense`, and returns explicit operation results for add,
rename, activate, and deactivate behavior through `CategoryRepository`.
Active-name uniqueness is scoped by
transaction type and compared case-insensitively. Inactive names may be reused;
activation is rejected if it would conflict with an active category of the
same type. Listing is deterministic: transaction type, then numeric display ID.
Display-ID lookup follows Account Management normalization while still
requiring an exact complete category ID.

Public query operations are `list_categories()`, `get_category_by_id()`, and
`get_category_by_display_id()`. Listing can exclude inactive records and filter
by a validated `income` or `expense` transaction type. UUID and display-ID
lookup remain status-independent for historical resolution. The CLI uses these
boundaries to select managed categories for transactions; the service validates
the selected UUID and transaction-type compatibility.

---

## JSON Persistence

The current document structure is:

```json
{
    "schema_version": 3,
    "metadata": {
        "next_display_id": 3
    },
    "transactions": [
        {
            "id": "internal-uuid",
            "display_id": "T-0001",
            "type": "expense",
            "amount": 12.5,
            "category": "Food",
            "category_id": "category-uuid-or-null",
            "account": "Cash",
            "account_id": "account-uuid-or-null",
            "description": "Lunch",
            "transaction_date": "2026-07-24",
            "created_at": "2026-07-24T09:15:00+00:00",
            "updated_at": "2026-07-24T09:15:00+00:00"
        }
    ]
}
```

`transaction_date` is the financial date. The optional `created_at` and
`updated_at` fields are timezone-aware UTC metadata and are not used for
financial period selection. `account_id` and `category_id` are optional
canonical UUID references. The required `account` and `category` strings remain
stored snapshots and fallbacks for display, search, filtering, and unresolved
legacy transactions.

`metadata.next_display_id` is a persistent global monotonic counter. Deleting the
highest transaction does not decrease it, so a deleted display ID is not
reused. Legacy files whose top level is a transaction list remain readable;
their next safe value is derived from the highest valid display ID, and they
are migrated to schema version 3 on the next successful mutation. Missing
schema metadata is version 1, and schema versions 1 and 2 load missing reference
fields as `None`. Legacy `date` maps to `transaction_date`; historical missing
timestamps remain `None`, and reads never rewrite files. Schema version 3
writes missing references explicitly as JSON `null`.

Missing and empty files represent an empty dataset. Malformed JSON, invalid
top-level structures, invalid metadata, and malformed transaction entries
raise a controlled `StorageError`.

Complete create, bulk-create, replace, delete, and retained compatibility mutations use a
re-entrant cross-process lock. Duplicate internal IDs, duplicate display IDs,
import comparison keys during bulk creation, and a counter behind existing IDs
are rejected before a write. Writes use a
temporary file in the destination directory. Storage serializes
and flushes the full document, calls `os.fsync`, and then uses `os.replace` for
an atomic destination replacement. A failed write removes its temporary file
and leaves the previous destination content unchanged.

Accounts use a separate `data/accounts.json` document containing metadata and
the account list. Keeping both sections in one atomic replacement prevents
partial state/account saves. The persisted counter is checked against the
highest stored display ID, so identifiers are not reused if the list later
shrinks.

The storage boundary validates required fields, canonical UUID and display-ID
formats, boolean status, and uniqueness of internal IDs, display IDs, and
active normalized names. Complete account read-modify-write workflows use a
cross-process lock, preventing lost updates between application instances.
The previous list-only account file and companion `accounts_state.json` remain
readable and migrate on the next save. Accounts use separate persistence from
transactions while their UUIDs may be stored as managed transaction references.

Categories use a current list-only `data/categories.json` document and a
separate `data/categories_state.json` counter. No legacy Category format is
needed because there is no production Category data to migrate. Storage
validates exact fields, canonical UUIDs and `C-####` display IDs, NFC names,
lowercase transaction types, real boolean status, identifier uniqueness, and
active-name uniqueness within each transaction type. State cannot be lower
than the next value derived from stored IDs; a missing state file is safely
recovered from the records. Each file uses same-directory atomic replacement.
State advancement precedes persistence of a newly allocated record, so a
failed second write can create a harmless ID gap but cannot cause reuse.
Complete mutations run under a re-entrant cross-process category lock.

`TransactionService` now validates optional managed Account and Category UUIDs
through injected public query boundaries. Runtime transaction add and update
handlers list active records by display ID and submit their UUIDs. Stored names
remain snapshots, inactive historical references may be preserved, and legacy
transactions may be linked during update. Explicit unlinking and automatic
legacy reconciliation remain future work. Separate JSON files and locks provide
soft rather than database-level referential integrity.

The older function-oriented transaction operations in `storage.py` remain
supported compatibility surfaces and retain their tests. Production
composition reaches transaction persistence exclusively through
`TransactionRepository`; the application factory never injects those legacy
functions into a service.

---

## SQLite Persistence Foundation

SQLite infrastructure exists for future repository adapters but is not part of
production composition. `build_json_application()` remains unchanged, JSON
remains the only active backend, and neither `main.py` nor any service imports
SQLite. There is no SQLite repository, backend selector, or JSON migration.

### Path and Connection Policy

The future workspace database path is:

```text
<workspace root>/data/smart_expense_tracker.sqlite3
```

When no root is supplied, the path remains the unresolved relative path
`data/smart_expense_tracker.sqlite3`, preserving current-working-directory
workspace behavior. Calculating a path and importing the SQLite modules create
no directory or file. A short-lived connection creates the parent directory for
a real file-backed database.

Every connection uses Python's built-in `sqlite3`, returns `sqlite3.Row`
objects, enables `PRAGMA foreign_keys = ON`, and configures a five-second
`busy_timeout`. Journal mode and synchronous mode retain SQLite defaults;
the foundation does not introduce WAL side files or unneeded tuning. There is
no ORM, external database dependency, global connection, or import-time access.

Writes use an explicit `BEGIN IMMEDIATE` context. Successful work commits once;
application exceptions and SQLite failures roll back the complete transaction,
and the connection is always closed. This boundary will allow a future
repository to allocate a display ID and insert its record atomically.

### Schema Version 1

Initialization creates all version 1 objects in one transaction and writes the
version only as part of that transaction. Repeated initialization validates
and preserves a valid version 1 database. Older, newer, malformed, partial, or
constraint-incomplete schemas are rejected without rebuilding, downgrading, or
deleting data. Upgrade migrations are deferred.

Version 1 contains:

- `schema_metadata`: one singleton schema-version row.
- `display_id_counters`: independent next values for Account, Category, and
  Transaction display IDs. CHECK constraints, a primary key, and triggers
  prevent invalid keys, non-positive values, deletion, and counter regression.
- `accounts`: UUID identity, `A-####` display ID, name, Unicode comparison key,
  and active state.
- `categories`: UUID identity, `C-####` display ID, name, Unicode comparison
  key, income/expense type, and active state.
- `transactions`: UUID identity, `T-####` display ID, income/expense type,
  amount, Account/Category name snapshots, nullable managed UUID references,
  description, financial date, and nullable creation/update timestamps.

Account active-name uniqueness uses a partial unique index over a
Python-produced NFC/casefold comparison key. Category uniqueness uses the same
approach scoped by transaction type. Inactive duplicates remain permitted.
SQLite's built-in `lower()` is not a Unicode casefold replacement, so future
repositories are responsible for producing these keys with the existing domain
normalizers.

Nullable Transaction references support current legacy records. When present,
foreign keys use restrictive update/delete behavior; cascading deletion is not
introduced. Indexes cover display IDs, active managed-record lookup, Category
type, Transaction date/type, and both managed UUID references.

Amounts use SQLite `REAL` to preserve the application's current Python
`float` behavior. Moving to decimal text or integer minor units requires a
separate domain-level decision. Transaction dates use ISO `YYYY-MM-DD` text,
and timestamps use canonical ISO-8601 UTC text. Full calendar, timestamp,
and normalization validation remains in the validation/service layer and future
repository conversion code rather than brittle SQL expressions. Version 1 does
not claim SQL-level finite-number validation; tightening non-finite float
behavior requires a separate application decision.

Low-level SQLite failures are chained beneath backend-neutral `StorageError`
exceptions. Unsupported versions use
`UnsupportedSchemaVersionError`, which remains catchable as `StorageError`.

The next persistence milestone may implement Account and Category repository
adapters against these contracts. Production activation, Transaction repository
implementation, backend selection, and JSON migration remain separate work.

---

## Separation of Responsibilities

The current version separates terminal interaction (`main.py`), validation
(`validators.py`), account operations (`account_service.py`), category
operations (`category_service.py`), data records (`account.py`, `category.py`,
and `transaction.py`), transaction application workflows
(`transaction_service.py`), entity-specific repository abstractions and JSON
implementations (`account_repository.py`, `category_repository.py`, and
`transaction_repository.py`), application composition (`application.py`),
domain construction (`transaction_factory.py`),
lookup/search (`search.py`), reporting (`report.py`), formatting
(`formatter.py`), and persistence infrastructure. Account and Category
Management use separate persistence and connect to transactions only through
service query APIs and optional UUID references.

Replacing JSON later requires new implementations of the three repository
protocols plus a new composition function beside `build_json_application()`;
managed-record business rules, Excel services, and CLI workflows do not require
direct storage changes.

---

## Design Principles

The project follows these principles:

- Single Responsibility Principle
- Separation of Concerns
- Reusable business logic
- Incremental refactoring
- Testable modules
- Small focused functions
- Explicit error handling

---

## Long-Term Architecture

The architecture will gradually evolve into a layered design.

```text
Presentation Layer
        │
        ▼
Application Layer
        │
        ▼
Domain Layer
        │
        ▼
Repository Layer
        │
        ▼
Infrastructure Layer
```

Each layer has a single responsibility.

---

## Planned Layers

### Presentation Layer

Responsible for user interaction.

Possible implementations:

- Command Line Interface (CLI)
- Desktop GUI
- Telegram Bot
- REST API

Presentation code should never contain business logic.

---

### Application Layer

Coordinates application workflows.

Responsibilities include:

- Creating transactions
- Updating transactions
- Deleting transactions
- Importing data
- Exporting data
- Coordinating repositories

---

### Domain Layer

Contains business rules and domain models.

Examples:

- Transaction
- Money
- Category
- Account
- TransactionType

The domain layer must not depend on:

- JSON
- SQLite
- Excel
- Telegram
- GUI

---

### Repository Layer

Provides a common interface for data storage.

Future implementations may include:

- JSON Repository
- SQLite Repository
- In-Memory Repository (testing)

Application code should depend on the repository interface rather than a specific implementation.

---

### Infrastructure Layer

Implements external technologies.

Examples:

- SQLite
- JSON
- Excel
- PDF Export
- Telegram API

Infrastructure code should never contain business rules.

---

## Data Flow

The intended workflow is:

```text
Input
    │
    ▼
Validation
    │
    ▼
Application Service
    │
    ▼
Repository
    │
    ▼
Storage
```

Every input source should use the same validation and business logic.

---

## Planned Integrations

Future integrations include:

- Excel Dashboard
- Additional Excel reporting formats
- Telegram Bot
- PDF Reports
- Desktop GUI

These integrations must reuse existing application services instead of implementing duplicate logic.

---

## Storage Strategy

### Current

- JSON

### Planned

- SQLite (Primary)
- JSON (Import / Export)
- CSV (Export)
- Excel (Export)

---

## Testing Strategy

Architecture should support:

- Unit tests
- Integration tests
- Repository tests
- Import/Export tests

Core business logic should be testable without requiring user input or file access.

---

## Future Goals

The long-term architecture should support:

- Multiple accounts
- Multiple currencies
- Budgets
- Recurring transactions
- Transfers
- Advanced reports
- Dashboard generation
- Automation
- Additional user interfaces

These features should be added without major architectural rewrites.

---

## Architecture Principles

Every new feature should follow these rules:

- Reuse existing business logic.
- Keep responsibilities separated.
- Avoid duplicated code.
- Preserve backward compatibility.
- Prefer composition over duplication.
- Keep modules small and focused.
- Add documentation for architectural changes.

---

## Packaging and Delivery Boundary

`pyproject.toml` is the canonical definition for build metadata, supported
Python, dependencies, the flat-module installation map, and the console
script. Setuptools builds the modules already present in `src/`; packaging does
not introduce a second application architecture or move business logic.

The installed startup flow is:

```text
expense-tracker
    -> main:main
    -> existing CLI menus
    -> build_json_application()
    -> application services and adapters
```

`python3 src/main.py` reaches the same callable through the module's guarded
runner. Importing `main` constructs one side-effect-free, immutable application
service aggregate for compatibility with the existing handler surface; it does
not enter the input loop or create/read/write runtime files. Explicit factory
calls can construct isolated applications for other workspace roots without
sharing mutable state.

Default JSON paths and default Excel output are current-working-directory
relative (`data/` and `exports/`). This makes the working directory the
explicit runtime workspace for both source and installed execution and keeps
mutable data outside the wheel, site-packages, and virtual environments.
Changing the process working directory selects a different independent
workspace; records from another workspace are not discovered automatically.

GitHub Actions is delivery infrastructure rather than business logic. For
pushes and pull requests targeting `main`, its Python 3.10/3.13 matrix installs
`.[dev]`, runs the complete pytest suite, compiles `src` and `tests`, checks the
event's changed content for whitespace errors, builds both distributions,
installs the built wheel into a clean environment, and smoke-tests its console
command with deterministic exit input.
