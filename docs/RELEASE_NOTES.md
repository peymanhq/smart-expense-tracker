# Smart Expense Tracker v1.0.0

This planned first official release completes the version 1 stabilization
cycle. The v1.0.0 release candidate keeps the application focused on
straightforward local income and expense tracking while making transaction
identity and JSON persistence significantly safer.

## Highlights

- Add, view, search, filter, update, and delete income and expense transactions
  from the command line.
- View income, expense, and balance summaries.
- Use short display IDs such as `T-0001` while retaining a stable internal UUID.
- Find display IDs by exact, case-insensitive matches across search, update, and
  deletion workflows.

Display IDs now advance from persistent metadata. Deleting the transaction with
the highest ID does not cause that ID to be reused, and updates retain both the
original UUID and display ID.

JSON writes now build and flush a temporary file beside the destination before
atomically replacing it. Malformed or structurally invalid JSON is reported as
a controlled storage error, failed writes clean up temporary files, and a
failed replacement leaves the previous data intact.

## Verification

The release has 27 passing pytest tests covering creation, validation, storage,
IDs, search, updates, deletion, reports, malformed and legacy data, and failed
atomic writes. Tests use temporary files rather than the application data file.
Python compilation, `git diff --check`, CLI startup and exit, display-ID
non-reuse, legacy JSON loading, and failed-replacement preservation were also
verified. `data/transactions.json` remained unchanged during verification.

## Upgrading

No manual data migration is required. Existing list-only JSON files remain
readable, and the current metadata-based structure is written on their next
successful save.

## Known Limitations

This remains a local, single-user CLI using floating-point amounts and
whole-file JSON persistence. It has no concurrent-writer coordination,
database, GUI, authentication, synchronization, multi-currency support, or
Excel/PDF export.

## Next Steps

The immediate next step is publishing v1.0.0. After that release, v1.1.0 is the
next planned development version, with application-service and repository
boundaries, exact monetary representation, packaging improvements, and
continuous integration under consideration.
