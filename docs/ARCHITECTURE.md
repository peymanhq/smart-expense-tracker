# Smart Expense Tracker — Architecture

## Overview

Smart Expense Tracker is designed as a modular Python application with a clear separation of responsibilities.

The project follows an incremental architecture. Each version improves the internal design while preserving existing functionality.

The long-term objective is to build a maintainable, testable, and extensible finance application.

---

## Current Architecture (v1.0.0 Release Candidate)

The current application follows this structure:

```text
User
  │
  ▼
main.py
  │
  ├── transaction_factory.py
  ├── validators.py
  ├── storage.py
  ├── report.py
  ├── search.py
  ├── formatter.py
  │
  ▼
transaction.py
  │
  ▼
transactions.json
```

### Module Responsibilities

| Module | Responsibility |
|---------|----------------|
| `main.py` | CLI interaction and workflow orchestration |
| `transaction.py` | Transaction data model |
| `transaction_factory.py` | Transaction creation |
| `validators.py` | Input validation |
| `storage.py` | JSON persistence |
| `report.py` | Financial calculations |
| `search.py` | Search and filtering |
| `formatter.py` | Terminal formatting |
| `id_generator.py` | UUID creation and display-ID formatting, parsing, and legacy-state calculation |

`main.py` currently coordinates update and deletion workflows; there is no
separate `update.py` module.

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

---

## Separation of Responsibilities

The current version separates terminal interaction (`main.py`), validation
(`validators.py`), transaction construction (`transaction_factory.py`), the
domain record (`transaction.py`), lookup and search (`search.py`), reporting
(`report.py`), formatting (`formatter.py`), and persistence (`storage.py`).
`main.py` is still both the CLI and workflow coordinator; a distinct
application-service layer remains future work.

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
