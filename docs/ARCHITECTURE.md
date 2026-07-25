# Smart Expense Tracker — Architecture

## Overview

Smart Expense Tracker is designed as a modular Python application with a clear separation of responsibilities.

The project follows an incremental architecture. Each version improves the internal design while preserving existing functionality.

The long-term objective is to build a maintainable, testable, and extensible finance application.

---

## Current Architecture (v1.1.0 Development)

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
  ├── transaction_factory.py
  ├── validators.py
  ├── storage.py
  ├── report.py
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
| `transaction.py` | Transaction data model |
| `transaction_factory.py` | Transaction creation |
| `validators.py` | Input validation |
| `storage.py` | JSON persistence |
| `report.py` | Financial calculations and transaction filtering |
| `search.py` | Transaction search and display-ID lookup |
| `formatter.py` | Terminal formatting |
| `id_generator.py` | UUID creation and display-ID formatting, parsing, and legacy-state calculation |

`main.py` currently coordinates update and deletion workflows; there is no
separate `update.py` module.

Account workflows use a focused application-service module so their business
rules remain independent of CLI input and output.

Category workflows use the same focused service boundary and remain
independent of transaction creation.

---

## Current Workflows

### Transaction Creation

1. `main.py` asks `storage.py` for the next persisted display ID.
2. `transaction_factory.py` validates and normalizes input through
   `validators.py`.
3. The factory creates a `Transaction` with an internal UUID and user-facing
   display ID.
4. `storage.py` appends the transaction, advances the display-ID metadata, and
   atomically writes the document.

### Search, Update, and Deletion

`search.py` provides `find_transaction_by_display_id()`, the shared lookup used
by the CLI update flow and by storage update and deletion operations. It trims
whitespace, compares case-insensitively, and requires an exact display-ID
match. General search also includes the display ID among its searchable fields.

During an update, storage finds the current transaction again, preserves its
internal UUID and display ID, and replaces only its editable data. The boolean
update result is checked by the CLI so a missing transaction is not reported as
successfully updated.

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

### Category Management

`category_service.py` trims and NFC-normalizes names, canonicalizes transaction
types to `income` or `expense`, and returns explicit operation results for add,
rename, activate, and deactivate behavior. Active-name uniqueness is scoped by
transaction type and compared case-insensitively. Inactive names may be reused;
activation is rejected if it would conflict with an active category of the
same type. Listing is deterministic: transaction type, then numeric display ID.
Display-ID lookup follows Account Management normalization while still
requiring an exact complete category ID.

---

## JSON Persistence

The current document structure is:

```json
{
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
            "account": "Cash",
            "description": "Lunch",
            "date": "2026-07-24"
        }
    ]
}
```

`metadata.next_display_id` is a persistent monotonic counter. Deleting the
highest transaction does not decrease it, so a deleted display ID is not
reused. Legacy files whose top level is a transaction list remain readable;
their next safe value is derived from the highest valid display ID, and they
are migrated to the current structure on the next write.

Missing and empty files represent an empty dataset. Malformed JSON, invalid
top-level structures, invalid metadata, and malformed transaction entries
raise a controlled `StorageError`.

Writes use a temporary file in the destination directory. Storage serializes
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
readable and migrate on the next save. Accounts remain standalone and do not
alter the v1.0 transaction JSON schema.

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

---

## Separation of Responsibilities

The current version separates terminal interaction (`main.py`), validation
(`validators.py`), account operations (`account_service.py`), category
operations (`category_service.py`), data records (`account.py`, `category.py`,
and `transaction.py`), transaction construction
(`transaction_factory.py`), lookup and search (`search.py`), reporting
(`report.py`), formatting (`formatter.py`), and persistence. `main.py` remains
the transaction workflow coordinator, while Account and Category Management
use focused application-service boundaries.

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

- Excel Import
- Excel Export
- Excel Dashboard
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
