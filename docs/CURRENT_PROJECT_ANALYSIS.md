# Smart Expense Tracker — Current Project Analysis

## Executive Summary

The Smart Expense Tracker v1.0.0 release candidate is a small and readable
command-line application with a reasonable initial separation between input
handling, validation, persistence, querying, reporting, and formatting. It is
ready for release but has not yet been published.

The completed version 1 stabilization added automated regression tests,
persistent display-ID state, shared exact display-ID lookup, accurate update
results, controlled JSON errors, legacy-file compatibility, and atomic JSON
writes. The project remains primarily module-based rather than layered:
`main.py` directly coordinates business logic and persistence, the domain model
permits invalid states, and JSON storage still does not coordinate concurrent
writers or provide schema versioning.

The highest-priority improvements are:

1. Use an exact monetary representation instead of `float`.
2. Enforce model invariants.
3. Expand automated coverage as new behavior is added.
4. Separate the CLI from application workflows.
5. Introduce a repository abstraction and migrate storage to SQLite.

---

## 1. Current Architecture

The application currently follows this flow:

```text
CLI and orchestration
        main.py
           |
           +-- transaction_factory.py -- validators.py
           +-- storage.py
           +-- report.py
           +-- search.py
           +-- formatter.py
                         |
                         v
                   transaction.py
                         |
                         v
              data/transactions.json
```

### 1.1 Presentation and Orchestration

`src/main.py` is responsible for:

- Displaying the interactive menu
- Reading user input
- Coordinating create, read, update, and delete operations
- Running search and filter operations
- Printing results and errors

It currently serves as the presentation layer, application layer, and dependency-composition root.

### 1.2 Domain Model

`src/transaction.py` defines a single `Transaction` dataclass containing:

- Internal UUID
- Human-readable display ID
- Transaction type
- Amount
- Category
- Account
- Description
- Date

The model only stores data. It does not enforce its own invariants, so invalid objects can be created outside the factory.

### 1.3 Construction and Validation

`src/transaction_factory.py` creates transactions and delegates input validation to `src/validators.py`.

This is a useful separation because transaction creation and normalization have a centralized path. However, data loaded directly from JSON bypasses this path.

### 1.4 Persistence

`src/storage.py` implements JSON-based persistence:

- Load all transactions
- Append a transaction
- Update a transaction
- Delete a transaction
- Find a transaction by display ID

Each write operation reads or rewrites the complete JSON file.

### 1.5 Queries, Reports, and Formatting

- `src/report.py` calculates financial totals and filters transactions.
- `src/search.py` performs free-text searches.
- `src/formatter.py` renders transactions for terminal output.

These modules contain mostly pure functions, which makes them suitable for isolated testing and reuse.

---

## 2. Strengths

- The project is small and easy to navigate.
- Modules have broadly understandable responsibilities.
- Validation is centralized instead of being duplicated across menu handlers.
- Search, filtering, and summary calculations are mostly pure functions.
- The `Transaction` dataclass provides a clear initial data structure.
- UUIDs are used as stable internal identifiers.
- ISO-formatted dates make the current string comparisons predictable.
- The menu dispatch dictionary is simpler than a large conditional chain.

---

## 3. Correctness Issues

### 3.1 Display-ID Stabilization — Completed

The first display ID is consistently `T-0001`. Persistent metadata prevents
reuse after deletion, and exact case-insensitive lookup is shared by search,
update, and deletion.

### 3.2 Floating-Point Money

Amounts are converted to `float`. Binary floating-point values cannot represent many decimal fractions exactly:

```text
0.1 + 0.2 = 0.30000000000000004
```

Formatting to two decimal places may conceal the issue, but calculations, exports, comparisons, and future reporting can expose it.

**Recommendation:** Use `Decimal` with an explicit rounding policy, or store amounts as integer minor units.

### 3.3 JSON Safety — Stabilized with Remaining Limits

The storage layer now uses same-directory temporary files, flushes and syncs
content, and atomically replaces the destination. Failed writes clean up their
temporary files and preserve the previous file. Malformed or structurally
invalid JSON raises `StorageError`, while legacy list-only JSON remains
readable.

Concurrent processes can still overwrite each other's changes, and there is no
backup or explicit schema-version mechanism. SQLite remains a future option.

### 3.4 Invalid `display_id` State

The transaction factory accepts `display_id: str | None`, but `Transaction.display_id` is declared as `str`. Other functions immediately call methods such as `.upper()` and `.startswith()` on it.

The factory can therefore create an object that violates assumptions elsewhere in the program.

**Recommendation:** Require a valid display ID or make ID allocation part of a single application service.

### 3.5 Display-ID Search — Completed

Free-text search includes `display_id`, and exact normalized lookup supports
transaction workflows.

### 3.6 Update Result Handling — Completed

The CLI checks the boolean result from `update_transaction()` and reports
not-found outcomes accurately. Storage also preserves the existing UUID and
display ID.

---

## 4. Code Smells and Maintainability Risks

### High Priority

#### Growing God Module

`main.py` mixes:

- Terminal input and output
- Workflow coordination
- Error handling
- Persistence calls
- Presentation logic

As more features are added, this file will become difficult to test and maintain.

#### Global Storage Configuration

The storage layer uses global functions and a global `DATA_FILE`. This makes tests, alternate data locations, and replacement storage backends unnecessarily difficult.

#### Anemic Domain Model

The model accepts raw values without protecting invariants. JSON loading also constructs `Transaction` objects directly and bypasses factory validation.

### Medium Priority

- Transaction formatting is duplicated in `main.py` and `formatter.py`.
- The field name `type` shadows Python's built-in `type`.
- Dates are stored as strings rather than typed `date` values.
- Invalid transaction-type filters silently return no results.
- Filtering repeatedly creates intermediate lists.
- Currency is not represented in the model.
- Imports depend on the current source layout instead of an installable package.
- Comments and menu text contain spelling and naming inconsistencies.

### Project Hygiene

- No formatter, linter, or static type checker configuration
- No continuous integration workflow
- No coverage target
- No documented backup, recovery, or data-migration process

The v1.0.0 release candidate has 27 passing pytest tests, a declared pytest
dependency, supported Python guidance in the README, a changelog, release
notes, and stabilized project documentation. Tests use temporary files and
leave the real application data unchanged.

---

## 5. Recommended Version 2.0 Architecture

A pragmatic v2.0 should introduce an application-service layer and a repository boundary without overengineering:

```text
Command-line interface
          |
          v
ExpenseTrackerService
          |
          +-- TransactionRepository interface
          |       +-- SQLiteRepository
          |       +-- InMemoryRepository for tests
          |
          +-- Domain model and value objects
          |       +-- Transaction
          |       +-- Money
          |       +-- TransactionType
          |       +-- Account
          |       +-- Category
          |
          +-- Query and reporting services
```

Suggested package structure:

```text
src/smart_expense_tracker/
|-- cli.py
|-- application/
|   |-- services.py
|   `-- queries.py
|-- domain/
|   |-- transaction.py
|   |-- money.py
|   `-- exceptions.py
|-- infrastructure/
|   |-- sqlite_repository.py
|   `-- json_importer.py
`-- reporting/
    |-- summaries.py
    `-- exporters.py
```

### Why SQLite?

SQLite is a better primary store for v2.0 because it provides:

- Atomic transactions
- Unique constraints
- Indexes
- Efficient filtering and sorting
- Better concurrent-access behavior
- Schema migrations
- Reliable local storage without a database server

JSON should remain available as an import and export format.

---

## 6. Version 2.0 Roadmap

### Phase 1 — Stabilize Version 1 Behavior — Completed for v1.0.0

- Replace `float` money with `Decimal` or integer minor units.
- Require valid IDs during construction.
- Centralize transaction formatting.

Display-ID generation and non-reuse, display-ID search, update reliability,
safe JSON persistence, legacy compatibility, and a 27-test regression suite
are complete. Exact money, stricter construction invariants, and formatting
cleanup remain planned for version 1.2 or later.

### Phase 2 — Establish Application Boundaries

- Convert `src` into an installable `smart_expense_tracker` package.
- Define a `TransactionRepository` protocol.
- Move workflows into an `ExpenseTrackerService`.
- Restrict `input()` and `print()` to the CLI layer.
- Introduce domain-specific exceptions.
- Introduce value objects or enums for money and transaction type.
- Use typed dates in the domain.
- Inject repository and ID-generator dependencies.

**Exit criterion:** Core workflows can run in tests without terminal input or real files.

### Phase 3 — Migrate Persistence

- Add a SQLite repository.
- Define a schema and migration process.
- Add unique constraints for internal and display IDs.
- Store monetary amounts exactly.
- Provide a one-time JSON import command.
- Add backup and restore commands.
- Retain JSON and CSV export support.
- Document migration and recovery procedures.

**Exit criterion:** Updates are atomic, interrupted writes do not corrupt data, and v1 data can be migrated safely.

### Phase 4 — Add Finance Features

- Budgets by category and period
- Recurring transactions
- Multiple accounts with opening balances
- Transfers between accounts
- Managed categories and tags
- Monthly cash-flow reports
- Spending breakdowns
- Sorting, pagination, and flexible date ranges
- CSV, Excel, and PDF exports
- Explicit currency configuration

Multi-currency conversion should only be added after defining exchange-rate sources and historical-rate behavior.

### Phase 5 — Release Readiness

- Add Ruff and consistent formatting.
- Add static type checking.
- Add CI for supported Python versions.
- Define coverage thresholds for domain and persistence code.
- Add integration tests using temporary SQLite databases.
- Provide a console command such as `expense-tracker`.
- Rewrite the README with:
  - Installation
  - Usage examples
  - Data location
  - Migration instructions
  - Backup and restore
  - Troubleshooting
- Adopt semantic versioning.
- Maintain a changelog.
- Test the JSON-to-SQLite upgrade against realistic v1 data.

---

## 7. Recommended Implementation Order

The recommended order for the next development cycle is:

1. Correct monetary representation.
2. Expand tests alongside new behavior.
3. Strengthen remaining model invariants.
4. Separate the CLI from application workflows.
5. Introduce the repository abstraction.
6. Migrate primary storage to SQLite.
7. Add new user-facing features.

The project is small enough to improve incrementally. A complete rewrite would add unnecessary risk. The safer strategy is to protect current behavior with tests and then refactor the architecture in controlled stages.

---

## 8. Overall Conclusion

The Smart Expense Tracker v1.0.0 release candidate has a tested, reliable base
for its version 1 command-line scope. Its pure query and validation functions
provide useful building blocks for future development.

After v1.0.0 is published, planned v1.1.0 work should focus on exact financial
calculations, stronger domain invariants, clearer application boundaries,
packaging, and continuous integration. SQLite and broader finance features
remain future version 2 work and are not part of the current release candidate.
