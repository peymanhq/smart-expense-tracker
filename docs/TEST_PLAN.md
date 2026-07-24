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

The pytest suite covers:

- Valid transaction creation and normalization
- Validation failures for amount, transaction type, category, account, and date
- Saving and loading the current metadata-based JSON structure
- Initial display-ID formatting, parsing, and sequence calculation
- Persistent display-ID advancement and non-reuse after deletion
- Exact, whitespace-tolerant, case-insensitive display-ID lookup
- Successful update and not-found behavior
- Preservation of internal UUID and display ID during updates
- Successful and unsuccessful deletion
- Income, expense, balance, and empty-report calculations
- Missing and empty data files
- Malformed JSON and structurally invalid documents
- Legacy list-only JSON loading and migration on the next write
- Failed atomic replacement, preservation of the previous file, and temporary
  file cleanup
- Isolation from the real application data file through `tmp_path` and
  `monkeypatch`

Run the suite from the repository root:

```bash
python -m pytest -q
```

---

# Manual and Release Verification

The v1.0.0 release-candidate verification also confirmed:

1. Python source and tests compile successfully.
2. `git diff --check` completes successfully.
3. The CLI starts and exits normally.
4. An add/delete/add sequence advances the display ID.
5. Deleting the highest display ID does not make it reusable.
6. The repository's legacy list-only JSON shape loads successfully.
7. A simulated failed `os.replace` leaves the previous file unchanged and
   removes its temporary file.
8. `data/transactions.json` remains unchanged throughout verification.

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

The next planned development version, v1.1.0, includes continuous integration,
broader workflow coverage, and quality tooling. Future interfaces such as a GUI
or Telegram bot will require end-to-end tests. SQLite, import/export, and
integration-specific tests remain future work and are not part of the v1.0.0
release candidate.

---

# Release Requirements

A release should not be created unless:

- Critical tests pass.
- No known blocking bugs remain.
- Documentation is updated.
- The changelog and release notes are complete.
