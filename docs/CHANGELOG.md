# Changelog

All notable changes to this project will be documented in this file.

The format is based on **Keep a Changelog** and follows **Semantic Versioning**.

---

## [Unreleased]

### Added

- Standalone account creation, listing, renaming, deactivation, and reactivation
- Internal account UUIDs and user-facing `A-0001` display IDs
- Separate atomic JSON persistence for account records and display-ID state
- Account Management CLI submenu
- Focused automated coverage for account rules and persistence

### Changed

- Shared the atomic JSON writer between transaction and account persistence
- Began v1.1.0 development from the published v1.0.0 baseline
- Consolidated account records and display-ID metadata into one atomic document
- Added automatic migration from legacy account-list and state files
- Normalized account display-ID input and Unicode account names
- Paused after account operations until the user returns to the submenu

### Fixed

- Prevented inactive-account renames from triggering active-name conflicts
- Prevented a failed account-state write from partially persisting account data
- Prevented reactivation when it would create duplicate active account names
- Prevented concurrent account operations from losing data or reusing IDs
- Rejected malformed fields, invalid UUIDs, and duplicate account identifiers
- Converted invalid UTF-8 and lock-setup failures into controlled storage errors

---

## [1.0.0] - Released

### Added

- Add income and expense transactions
- View, search, filter, update, and delete transactions
- Financial summary reports
- JSON persistence and input validation
- Internal UUIDs and user-facing display IDs
- Modular project structure
- Persistent monotonic display-ID metadata
- Exact, case-insensitive display-ID lookup for user workflows
- Backward-compatible loading of legacy list-only JSON files
- A 27-test pytest regression suite using temporary data files

### Changed

- Shared display-ID lookup across search, update, and deletion flows
- Preservation of the existing internal UUID and display ID during updates
- Flushed same-directory temporary files and atomic `os.replace` for JSON saves

### Fixed

- Prevented reuse of the highest display ID after its transaction is deleted
- Corrected update result handling for missing records
- Added controlled handling for malformed and structurally invalid JSON
- Cleaned up temporary files after failed writes while preserving previous data

### Testing

- Confirmed 27 passing pytest tests
- Confirmed Python compilation and `git diff --check`
- Confirmed CLI startup and clean exit, add/delete display-ID sequencing,
  legacy JSON loading, and preservation after a simulated replacement failure
- Confirmed `data/transactions.json` remained unchanged during verification

### Documentation

- Prepared README and release documentation for the planned v1.0.0 release

---

## Versioning

This project follows Semantic Versioning.

```text
MAJOR.MINOR.PATCH
```

Example:

```text
1.0.0
```

- MAJOR: Breaking changes
- MINOR: New features
- PATCH: Bug fixes
