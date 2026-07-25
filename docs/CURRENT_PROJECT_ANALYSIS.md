# Smart Expense Tracker — Current Project Analysis

## Executive Summary

Smart Expense Tracker is a local command-line application under v1.1.0
development. Account Management, Category Management, and Date-based
Transaction Management are implemented on top of JSON persistence.

The transaction path now has explicit boundaries:

```text
main.py
    -> TransactionService
    -> TransactionRepository
    -> JsonTransactionRepository / storage.py
    -> shared atomic JSON writer
```

The completed date feature adds a selected-date workspace, historical entry,
date-scoped CRUD, explicit date movement, populated-date browsing, exact/range
search, and daily/range reports. Transaction mutations are locked, creation
allocates display IDs atomically, and schema version 3 remains compatible with
legacy transaction files.

The current automated suite contains 339 passing tests. Transaction persistence
tests use temporary files and do not modify runtime JSON data.

## Current Architecture

### Presentation

`main.py` owns terminal input/output and the active workspace date. The active
date starts from an injected today provider, lasts only for one Transaction
Management session, and is not persisted.

The CLI does not allocate transaction display IDs, generate timestamps, or
access transaction JSON directly.

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
`JsonTransactionRepository` implements them with the current flat JSON
document. This permits a future storage replacement without introducing JSON
access into application or presentation code.

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

## Compatibility

Transaction schema version 3 stores `transaction_date`, timestamps, and
optional Account and Category UUID references. Missing schema metadata is
treated as version 1. Schema versions 1 and 2, legacy top-level lists, and
legacy `date` fields remain readable. Missing reference fields load as `None`.

Matching `date` and `transaction_date` fields are accepted; conflicts fail.
Missing historical timestamps load as `None`, are never invented, and
`created_at=None` remains missing after an update. Reads never migrate data.
The next successful mutation writes schema version 3 and represents missing
references explicitly as JSON `null`.

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

### Exact Money

Amounts still use binary `float`. Replacing them with `Decimal` or integer minor
units requires an explicit migration and rounding policy and remains separate
future work.

### Managed References

Transactions can store optional managed-record UUIDs alongside required
snapshot names. `TransactionService` receives public UUID lookup callables from
`main.py`. Newly supplied references must exist and be active; managed category
types must match. Preserved inactive historical references are not revalidated
during unrelated updates, and managed snapshots cannot be edited without a new
reference.

Transaction add and update now list active records by display ID and submit the
selected UUIDs. Categories are listed for the resulting transaction type.
Empty update selections preserve historical references, including inactive
ones, and legacy snapshot-only records can be linked by choosing an active
record. Explicit unlinking and automatic migration of historical snapshot-only
values remain future work.

Account, Category, and Transaction data still use separate JSON files and
locks, so cross-file referential integrity is deliberately soft.

### Flat JSON Limits

Locking prevents lost read-modify-write mutations, but every transaction change
still rewrites the whole file. JSON is appropriate for the current scale;
SQLite remains planned for stronger constraints, querying, migrations, and
larger datasets.

### Project Tooling

Packaging, continuous integration, linting, static type checking, and coverage
thresholds remain planned.

## Recommended Next Work

Keep future work scoped and incremental:

1. Define exact-money representation and migration.
2. Design account/category transaction references.
3. Improve packaging and automated quality checks.
4. Add Excel/PDF export and charts only after the data contracts are stable.
5. Introduce SQLite through another `TransactionRepository` implementation.

Multiple accounts, multiple currencies, transfers, dashboards, a GUI, and
external interfaces remain roadmap items and are not implemented by the
date-based transaction feature.
