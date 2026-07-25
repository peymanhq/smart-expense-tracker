# Smart Expense Tracker — Test Plan

## Purpose

This document records the automated and manual verification used to protect
Smart Expense Tracker from regressions.

---

# v1.0.0 Release-Candidate Result

The current automated suite completes successfully:

```text
27 passed
```

All storage tests replace the configured application path with pytest temporary
files. Automated and manual verification therefore protect the real
`data/transactions.json` file.

---

# Automated Tests

The current v1.1.0 development suite completes successfully:

```text
248 passed
```

The pytest suite covers:

- Valid transaction creation and normalization
- Deterministic injected today and timezone-aware UTC clock behavior
- Same-timestamp creation metadata and advancing update metadata
- Shared future-date, exact-date, and range validation
- Date-scoped transaction creation, listing, update, deletion, and movement
- Active-date mismatch versus global not-found error behavior
- Selected-date workspace defaults, reset behavior, cancellation, and empty dates
- Populated-date browsing, counts, ordering, and singular/plural output
- Validation failures for amount, transaction type, category, account, and date
- Saving and loading transaction schema version 2
- Missing schema version, legacy top-level lists, and legacy `date` compatibility
- Matching/conflicting legacy and current date fields
- Preservation of missing legacy timestamps during load and update
- Unsupported future schemas and malformed-record rejection without rewriting
- Initial display-ID formatting, parsing, and sequence calculation
- Persistent display-ID advancement and non-reuse after deletion
- Complete create/replace/delete and compatibility mutation locking
- Concurrent creation without lost records or duplicate display IDs
- Duplicate internal/display IDs and regressed counter rejection
- Exact, whitespace-tolerant, case-insensitive display-ID lookup
- Successful update and not-found behavior
- Preservation of internal UUID and display ID during updates
- Successful and unsuccessful deletion
- Exact-date, inclusive closed-range, and one-sided API search
- AND-composed filters and deterministic date/display-ID ordering
- Financial-date selection independent of creation timestamps
- All-time, daily, range, and empty-period report calculations
- Missing and empty data files
- Malformed JSON and structurally invalid documents
- Legacy list-only JSON loading and migration on the next write
- Failed atomic replacement, preservation of the previous file, and temporary
  file cleanup
- Isolation from the real application data file through `tmp_path` and
  `monkeypatch`
- Account creation, whitespace normalization, and required-name validation
- Case-insensitive duplicate active-account rejection
- Sequential persistent account display IDs and non-reuse after deactivation
- Account JSON saving, loading, missing/blank files, and malformed JSON
- Account renaming with UUID and display-ID preservation
- Duplicate rename, missing account, deactivation, and state-specific results
- Account reactivation with identity preservation and duplicate-name protection
- Account-reactivation access through the CLI submenu
- Enter-to-return pause after account-management operations
- Unicode-normalized duplicate-name rejection
- Normalized account display-ID lookup
- Concurrent account additions without duplicate IDs or lost updates
- Strict account field, UUID, display-ID, and uniqueness validation
- Invalid account metadata and legacy state rejection
- Controlled malformed JSON, invalid UTF-8, and lock-setup errors
- Legacy account-list and state migration to the atomic document format
- Complete-document preservation after a failed account save
- Preservation of deactivated account records in storage
- Category name trimming, Unicode normalization, required-name validation, and
  canonical lowercase transaction types
- Active category-name uniqueness within transaction type, cross-type reuse,
  inactive-name reuse, and activation conflict protection
- Sequential persistent category display IDs, non-reuse, missing-state
  recovery, and malformed or regressed state rejection
- Category list saving/loading, missing/blank files, malformed JSON, invalid
  UTF-8, controlled directory errors, and failed atomic replacement
- Strict Category field, UUID, display-ID, transaction-type, boolean, exact
  field-set, identifier, and active-name validation
- Category rename, activate, and deactivate results with identity, type, and
  activity-state preservation
- Deterministic Category listing and normalized exact display-ID lookup
- Concurrent category additions without duplicate IDs or lost updates
- Category Management main-menu dispatch, numbered type choice, view
  formatting, submenu Back behavior, and controlled service/storage errors

Run the suite from the repository root:

```bash
python -m pytest -q
```

---

# Manual and Release Verification

The Date-based Transaction Management verification also confirms:

1. Python source and tests compile successfully.
2. `git diff --check` completes successfully.
3. The selected-date CLI workspace starts and resets to injected today.
4. Today and historical add/view/update/delete workflows use the active date.
5. Transaction movement, future-date rejection, and active-date mismatch
   messages behave as specified.
6. Exact/range search and all-time/daily/range reports select financial dates.
7. Add/delete/add advances the display ID without reuse.
8. Legacy list-only JSON loads without inventing timestamps.
9. A simulated failed `os.replace` leaves the previous file unchanged and
   removes its temporary file.
10. All persistence and CLI tests use disposable paths or in-memory fakes.
11. Runtime files under `data/` remain unchanged throughout verification.

---

# Test Environment and Principles

- Keep tests small, independent, isolated, and repeatable.
- Test behavior rather than private implementation details.
- Add a regression test for every confirmed bug.
- Never modify real user data.
- Use temporary files and directories for persistence tests.
- Do not remove a valid test merely to make the suite pass.

---

# Future Testing

Continuous integration and quality tooling remain planned. Future interfaces
such as a GUI or Telegram bot will require end-to-end tests. SQLite,
account/category transaction references, Decimal money, import/export, and
integration-specific tests remain future work.

---

# Release Requirements

A release should not be created unless:

- Critical tests pass.
- No known blocking bugs remain.
- Documentation is updated.
- The changelog and release notes are complete.
