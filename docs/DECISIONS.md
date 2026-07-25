# Smart Expense Tracker — Architecture Decisions

This document records important architectural and technical decisions made during the development of the project.

Each decision includes its context, rationale, and consequences.

---

# ADR-001

## Title

Use UUID as the internal transaction identifier.

## Status

Accepted

## Context

Transactions require a stable identifier that never changes.

Users should not interact with this identifier directly.

## Decision

Every transaction receives an internal UUID.

## Consequences

- Stable references
- Safe updates
- Future database compatibility

---

# ADR-002

## Title

Use Display IDs for user interaction.

## Status

Accepted

## Context

UUIDs are difficult for users to remember.

## Decision

Use human-readable IDs such as:

```text
T-0001
```

for searching and updating transactions.

## Consequences

- Better usability
- Easier searching
- Cleaner reports

---

# ADR-003

## Title

Keep validation separate from the Transaction model.

## Status

Accepted

## Context

Validation should be reusable by multiple input methods.

## Decision

Validation logic remains in dedicated validator modules.

## Consequences

The same validation can later be reused by:

- CLI
- Excel
- Telegram
- GUI
- API

---

# ADR-004

## Title

Use JSON for Version 1.

## Status

Accepted

## Context

The first version should remain simple and easy to understand.

## Decision

Store transactions in JSON.

## Consequences

Simple implementation.

Migration to SQLite is planned for Version 2.

---

# ADR-005

## Title

SQLite will become the primary storage.

## Status

Planned

## Context

JSON has limitations for reliability and scalability.

## Decision

Future versions will migrate to SQLite.

## Consequences

- Atomic transactions
- Better performance
- Reliable storage
- Easier querying

---

# ADR-006

## Title

Business logic must remain independent of the user interface.

## Status

Accepted

## Decision

Future interfaces such as CLI, GUI, Telegram Bot, and API must reuse the same application services.

## Consequences

New interfaces can be added without rewriting business logic.

---

# ADR-007

## Title

Documentation belongs in the docs directory.

## Status

Accepted

## Decision

All project documentation is stored inside:

```text
docs/
```

except:

```text
README.md
```

## Consequences

Cleaner project structure.

Consistent documentation layout.

---

# ADR-008

## Title

Incremental development instead of complete rewrites.

## Status

Accepted

## Decision

The project evolves through small, tested improvements.

Large rewrites should be avoided.

## Consequences

- Easier maintenance
- Better testing
- Lower risk

---

# ADR-009

## Title

Support multiple transaction input methods.

## Status

Planned

## Context

Transactions may originate from different sources.

## Decision

Supported input methods will include:

- CLI
- Excel Import
- Telegram Bot
- GUI
- Future API

All input sources must reuse the same validation and application logic.

## Consequences

Consistent behavior regardless of how transactions are created.

---

# ADR-010

## Title

Persist monotonic display-ID metadata.

## Status

Accepted

## Context

Calculating the next ID only from existing transactions can reuse the highest
ID after deletion.

## Decision

Store `metadata.next_display_id` in the JSON document and only advance it.

## Consequences

IDs are not reused and remain predictable. The file format gains metadata that
must be maintained with every successful save.

---

# ADR-011

## Title

Keep legacy list-only JSON readable.

## Status

Accepted

## Context

Existing users may have transaction files created before metadata was added.

## Decision

Accept a top-level list, derive the next safe value from its highest valid
display ID, and write the current structure on the next save.

## Consequences

Upgrades require no manual migration. Legacy loading adds a compatibility path
that must remain covered by tests.

---

# ADR-012

## Title

Use one exact display-ID lookup.

## Status

Accepted

## Context

Separate lookup implementations can disagree about case, whitespace, or partial
matches.

## Decision

Use `find_transaction_by_display_id()` for search-oriented lookup, update, and
deletion. Normalize whitespace and case while requiring an exact match.

## Consequences

User workflows behave consistently and duplicated lookup logic is avoided.
Exact matching intentionally rejects partial IDs.

---

# ADR-013

## Title

Write JSON through atomic replacement.

## Status

Accepted

## Context

Writing directly to the destination can leave partial JSON if serialization or
filesystem work fails.

## Decision

Write, flush, and `fsync` a same-directory temporary file, then replace the
destination with `os.replace`. Remove the temporary file on failure.

## Consequences

Failed replacements preserve the previous file and temporary artifacts are
cleaned up. Whole-file writes and concurrent-writer limitations still remain.

---

# ADR-014

## Title

Use temporary files for storage tests.

## Status

Accepted

## Context

Tests must not read from or write to real application data.

## Decision

Redirect `storage.DATA_FILE` to a pytest `tmp_path` for every storage test.

## Consequences

Tests are isolated and repeatable, and `data/transactions.json` is protected.
This requires storage configuration to be monkeypatched in the current design.

---

# ADR-015

## Title

Store standalone accounts separately with persistent display-ID state.

## Status

Accepted

## Context

Version 1.1.0 introduces Account Management without changing the v1.0
transaction schema or linking transactions to managed accounts.

## Decision

Store account records and the next display-ID number together in one
`data/accounts.json` document and use the shared atomic JSON writer. Validate
account fields and uniqueness at the storage boundary and lock complete
read-modify-write account operations across processes.

Continue reading the earlier list-only account file and companion
`accounts_state.json`, then migrate their safe next ID into the current
single-document format on the next save.

Keep account validation and mutation rules in `account_service.py`, separate
from the passive `Account` dataclass and the CLI.

## Consequences

- Existing transaction data and behavior remain unchanged.
- Deactivated accounts stay available for history and their IDs are not reused.
- Deactivated accounts can be reactivated when no active name conflict exists.
- Account changes and display-ID advancement succeed or fail as one file write.
- Concurrent application instances do not silently overwrite account changes.
- Malformed account records fail with controlled storage errors.
- Account workflows can later be reused by interfaces other than the CLI.
- Accounts and transactions remain intentionally unconnected in this phase.

---

# ADR-016

## Title

Store standalone categories as a validated list with separate monotonic state.

## Status

Accepted

## Context

Version 1.1.0 needs Category Management without adding `category_id` to
transactions or changing the published transaction JSON schema. There is no
existing production Category format requiring migration.

## Decision

Use a passive `Category` dataclass and keep business rules in
`category_service.py`. Store records as a JSON list in `data/categories.json`
and the next display-ID number in `data/categories_state.json`. Protect the
complete read-modify-write workflow with a category file lock and use the
shared atomic JSON writer for each file.

Active names are unique by NFC-normalized, case-insensitive name plus
transaction type. Inactive names are reusable. Validate the exact Category
schema and counter compatibility at the storage boundary. When allocating an
ID, persist advanced state before the category list so a failed list write can
create a gap but cannot allow ID reuse. Recover missing state from the highest
stored `C-####` ID.

## Consequences

- Categories remain standalone and transactions retain their v1.0 schema.
- The same active name can exist once for income and once for expense.
- Deactivated records and identifiers remain available and are never deleted.
- Concurrent mutations do not silently lose records or duplicate identifiers.
- Corrupt category records or state fail with controlled `StorageError`.
- There is no unnecessary legacy Category format.
