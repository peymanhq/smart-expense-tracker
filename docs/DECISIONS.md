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

Version 1.1.0 introduces Account Management with separate persistence and later
adds optional managed Account UUID references to transaction schema version 3.

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

Expose read-only service queries for deterministic account listing and lookup
by canonical internal UUID or normalized display ID. Active-only listing is
used by selection workflows, while lookup remains status-independent so
inactive records stay resolvable for history.

## Consequences

- Existing transaction data remains readable without manual migration.
- Deactivated accounts stay available for history and their IDs are not reused.
- Deactivated accounts can be reactivated when no active name conflict exists.
- Account changes and display-ID advancement succeed or fail as one file write.
- Concurrent application instances do not silently overwrite account changes.
- Malformed account records fail with controlled storage errors.
- Account workflows can later be reused by interfaces other than the CLI.
- Accounts retain separate persistence and connect to transactions through
  optional UUID references and stored name snapshots.
- Callers do not need private lookup helpers or direct account JSON access.

---

# ADR-016

## Title

Store standalone categories as a validated list with separate monotonic state.

## Status

Accepted

## Context

Version 1.1.0 needs Category Management with separate persistence and later
adds optional managed Category UUID references to transaction schema version 3.
There is no existing production Category format requiring migration.

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

Expose read-only service queries for deterministic category listing and lookup
by canonical internal UUID or normalized display ID. Listing may filter by
active status and validated transaction type. Lookup remains
status-independent so inactive records stay resolvable for history.

## Consequences

- Categories retain separate persistence; transactions may store their UUIDs
  while keeping required name snapshots.
- The same active name can exist once for income and once for expense.
- Deactivated records and identifiers remain available and are never deleted.
- Concurrent mutations do not silently lose records or duplicate identifiers.
- Corrupt category records or state fail with controlled `StorageError`.
- There is no unnecessary legacy Category format.
- Callers do not need private lookup helpers or direct category JSON access.

---

# ADR-017

## Title

Use `transaction_date` as the financial date.

## Status

Accepted

## Decision

Store a typed `datetime.date` as `transaction_date` and use it for transaction
workspaces, search, and reports. Reject future financial dates through one
shared application policy. Treat `created_at` and `updated_at` only as optional
timezone-aware UTC metadata.

## Consequences

- Historical entry and date movement are explicit.
- Metadata timestamps never determine a reporting period.
- Existing legacy `date` values map to `transaction_date`.
- Missing historical timestamps remain missing and are never invented.
- `float` money remains unchanged; conversion to `Decimal` is separate work.

---

# ADR-018

## Title

Keep the active transaction date as UI session state.

## Status

Accepted

## Decision

The Transaction Management workspace starts from an injected today provider.
Its active date is local to one menu session, is never persisted, and resets by
re-evaluating the provider when the workspace is reopened or Return to today is
selected.

## Consequences

Empty historical dates can be selected without creating data. Cancelled or
invalid actions do not alter the active date.

---

# ADR-019

## Title

Use a transaction application service and repository boundary.

## Status

Accepted

## Decision

`TransactionService` owns application date policy and timestamp behavior.
`TransactionRepository` defines persistence operations, and
`JsonTransactionRepository` implements them with the existing flat JSON
document, storage lock, schema compatibility, display-ID allocation, and atomic
writer.

## Consequences

The CLI does not allocate IDs, generate timestamps, or access JSON. A future
SQLite implementation can replace the repository without moving storage rules
into the CLI. Managed Account and Category references are enforced when newly
supplied.

---

# ADR-020

## Title

Lock complete transaction mutations and retain global monotonic display IDs.

## Status

Accepted

## Decision

Create, replace, delete, and retained compatibility mutations hold one
cross-process lock across their complete read-modify-write operation. Creation
loads the latest document, allocates from `metadata.next_display_id`, appends,
advances the counter, validates the candidate, and atomically writes while
still locked. Display IDs remain global across all financial dates.

## Consequences

Deleted IDs are never reused. Concurrent creation does not lose records or
duplicate display IDs. Duplicate identities and regressed counter state fail
before replacement. Flat JSON storage is retained for this development
version; SQLite remains planned.

---

# ADR-021

## Title

Use inclusive financial-date queries with deterministic ordering.

## Status

Accepted

## Decision

Exact-date and range criteria are mutually exclusive. Ranges include both
boundaries; the Python API also accepts one-sided ranges. Search combines all
criteria with AND semantics and orders results by newest `transaction_date`,
then ascending numeric display ID.

## Consequences

Search and reports share the same pure date-selection policy. Reversed ranges
and future query boundaries are rejected before loading data in application
workflows.

---

# ADR-022

## Title

Advance metadata time on every explicit update request.

## Status

Accepted

## Decision

Calling `TransactionService.update_transaction()` is an update event even when
no editable field value is supplied. It preserves financial content,
transaction UUID, display ID, and `created_at`, and advances only `updated_at`.
For legacy records, `created_at=None` remains `None`.

## Consequences

CLI submissions containing no field changes are recorded consistently as
metadata-only updates. Callers that do not intend an update should not invoke
the method.

---

# ADR-023

## Title

Store optional Account and Category UUID references with name snapshots.

## Status

Accepted

## Context

Transactions need durable managed-record references without breaking existing
free-text records, historical display, search, filtering, reports, or legacy
JSON compatibility.

## Decision

Transaction schema version 3 adds optional `account_id` and `category_id`
fields. Non-null values must be canonical UUID text. The existing required
`account` and `category` strings remain stored snapshots and fallbacks. Legacy
transactions without references load with `None`, and successful later
mutations write those missing references explicitly as JSON `null`.

Internal UUIDs are durable references. Account and Category display IDs remain
interaction identifiers and are not persisted as transaction foreign keys.
Inactive referenced records will remain resolvable for historical transactions
through status-independent UUID lookup.

Each reference is managed independently. A supplied UUID requires its lookup
dependency, must resolve to an active record for a new selection, and replaces
the corresponding caller text with the managed record's current name. An
omitted reference retains legacy free-text behavior for that field.

Updates preserve omitted managed references and snapshots without requiring
active revalidation. Direct snapshot-only edits on preserved managed references
are rejected; changing the managed record requires a new UUID. Explicit
reference clearing remains unsupported.

When transaction type changes, a newly selected category is validated against
the new type. If an existing managed category is preserved, it is resolved
including inactive records and must match the new type. Legacy transactions
with `category_id=None` retain their free-text compatibility behavior.

Transaction add and update use active managed-record lists and normalized
display-ID lookup in the CLI. Display IDs are interaction keys only; the CLI
passes UUIDs to `TransactionService`. Each selection remains independent.
During update, empty input omits the corresponding UUID argument and preserves
the historical reference or legacy snapshot. Legacy records may be linked by
selecting an active record, but automatic reconciliation and explicit unlinking
remain unsupported.

## Consequences

- Schema versions 1, 2, and 3 remain readable without read-time migration.
- Snapshot-only transaction creation remains valid during the integration
  transition.
- Updating unrelated transaction fields preserves existing reference UUIDs.
- Newly supplied managed references enforce existence, active status, and
  category/type compatibility in `TransactionService`.
- Historical inactive references remain valid when they are not being changed.
- CLI Account and Category selection uses display IDs without persisting them
  as foreign keys.
- Separate JSON files and locks provide soft, not database-level, referential
  integrity.
- Explicit unlinking and automatic legacy reconciliation remain future work.
