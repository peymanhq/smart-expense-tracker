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
