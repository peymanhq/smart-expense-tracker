# Smart Expense Tracker — Roadmap

## Completed foundation (1.x)

- Transaction, Account, and Category workflows
- Exact Decimal money amounts and managed references
- SQLite repositories, atomic schema migration, and validated backup/restore
- Excel import/export/template adapters
- Single-user Telegram add/balance/summary adapter
- Packaging, coverage, typing, lint, dependency audit, and CI gates

## Hardening completed after 1.6

- Retired JSON code, flags, migration, packaging, and tests
- Added optimistic concurrency to Transaction replacement
- Added SQL query/pagination/summary contracts
- Added physical integrity checks and private file permissions
- Added timestamped backup rotation with bounded retention
- Removed CLI application-service rebinding
- Routed installed commands through the project namespace

## 2.0 — Domain correctness

Detailed contracts and migration gates are in `V2_DESIGN.md`.

1. Introduce `Money` and explicit ISO currency semantics.
2. Add account opening balances and balance queries.
3. Add first-class transfers, including cross-currency debit/credit amounts.
4. Remove the flat-module packaging compatibility surface.

Each item ships behind its own atomic schema migration, repository contract,
service tests, CLI tests, backup/restore rehearsal, and rollback documentation.

## 2.1 — Reporting

- Monthly cash-flow and category trends
- Per-account and per-currency balances
- Transfer-aware reports that never count transfers as income or expense
- Excel dashboard sheets over repository projections

## 2.2 — Adapter parity and operations

- Telegram transaction update/delete and transfer entry
- Structured, privacy-redacted operational logs
- Documented scheduled off-device backup and restore drill
- Optional notification adapter behind application-service ports

## Explicit non-goals

- Reintroducing a JSON runtime backend
- Silently guessing the currency of legacy amounts
- Summing different currencies without an explicit conversion policy
- Encoding transfers as paired income/expense records
