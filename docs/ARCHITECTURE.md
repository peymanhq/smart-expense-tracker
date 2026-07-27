# Smart Expense Tracker — Architecture

## Overview

Smart Expense Tracker is designed as a modular Python application with a clear separation of responsibilities.

The project follows an incremental architecture. Each version improves the internal design while preserving existing functionality.

The long-term objective is to build a maintainable, testable, and extensible finance application.

---

## Current Architecture (post-v1.3.0 development)

The current application follows this structure:

```text
User
  │
  ▼
main.py
  │
  ├── account_service.py
  │     ├── account_storage.py
  │     └── account.py
  ├── category_service.py
  │     ├── category_storage.py
  │     └── category.py
  ├── transaction_service.py
  │     ├── transaction_repository.py
  │     │     └── storage.py
  │     ├── transaction_factory.py
  │     ├── clock.py
  │     └── date_policy.py
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
| `account.py` | Account data model |
| `account_service.py` | Account validation and add, rename, deactivate, and activate rules |
| `account_storage.py` | Validated, locked account persistence and legacy migration |
| `category.py` | Passive standalone Category data model |
| `category_service.py` | Category validation, listing, and mutation rules |
| `category_storage.py` | Validated, locked category-list and counter persistence |
| `json_storage.py` | Shared atomic JSON writing |
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
`TransactionService` coordinates transaction workflows without terminal or
JSON access. `TransactionRepository` isolates the application layer from the
current JSON implementation.

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

`main.py` also composes `TransactionService` with the public Account and
Category UUID query functions. The service receives only lookup callables and
does not know Account/Category file paths or storage formats.

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

Account workflows use a focused application-service module so their business
rules remain independent of CLI input and output.

Category workflows use the same focused service boundary and remain
independent of transaction persistence details.

The function-oriented account and category services also expose public,
read-only managed-record queries. Account queries list all or only active
records and resolve canonical UUIDs or normalized display IDs. Category queries
add active-state and transaction-type filters while retaining the established
type-then-display-ID ordering. UUID and display-ID lookup includes inactive
records so historical callers can still resolve them; active-only lists are the
boundary used by transaction selection workflows. These queries return new
collections, propagate storage errors, and do not modify persisted data.
`main.py` binds the active-list and normalized display-ID query functions to
runtime paths for transaction selection. Display IDs remain user-facing keys;
the selected domain UUIDs cross into `TransactionService`.

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
and coordinates add, rename, deactivate, and activate operations. Mutations
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
rename, activate, and deactivate behavior. Active-name uniqueness is scoped by
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

---

## Separation of Responsibilities

The current version separates terminal interaction (`main.py`), validation
(`validators.py`), account operations (`account_service.py`), category
operations (`category_service.py`), data records (`account.py`, `category.py`,
and `transaction.py`), transaction application workflows
(`transaction_service.py`), repository abstraction and JSON implementation
(`transaction_repository.py`), construction (`transaction_factory.py`),
lookup/search (`search.py`), reporting (`report.py`), formatting
(`formatter.py`), and persistence infrastructure. Account and Category
Management use separate persistence and connect to transactions only through
service query APIs and optional UUID references.

Replacing JSON later requires another `TransactionRepository` implementation;
the transaction service and CLI workflow do not need direct storage changes.

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
    -> existing CLI menus and dependency construction
    -> application services and adapters
```

`python3 src/main.py` reaches the same callable through the module's guarded
runner. Importing `main` constructs dependencies but does not enter the input
loop or read/write runtime files.

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
