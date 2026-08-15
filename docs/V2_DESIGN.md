# Version 2 Domain Design

## Goal and constraints

Version 2 adds currency, opening balances, and transfers while preserving the
current adapter → service → repository architecture. Migration must be atomic,
must not infer a currency from locale or timezone, and must be reversible from
a validated pre-upgrade backup.

## Domain contracts

### Money

`Money` is a value object containing a positive or signed `Decimal` (depending
on use case) and a three-letter uppercase ISO 4217 currency code. Persistence
uses canonical decimal text and the currency code. Arithmetic is allowed only
for equal currencies; mixed-currency addition raises a domain error.

Legacy unitless amounts migrate with currency `XXX` (ISO “no currency”). A user
must explicitly assign a currency before creating currency-aware balances or
transfers. Changing the currency of an account that already has movements is
blocked; re-denomination is a separate audited use case.

### Opening balance

An Account gains optional `opening_amount`, `opening_currency`, and
`opening_date`. The service requires the opening currency to match the account
currency. It is not represented as income and does not use a Category.

For account `A` at date `D`:

```text
balance = opening balance
        + income movements through D
        - expense movements through D
        + incoming transfer credits through D
        - outgoing transfer debits through D
```

### Transfer

Transfer is a separate aggregate with UUID/display ID, source and destination
Account IDs, debit Money, credit Money, financial date, description, and UTC
audit timestamps. Source and destination must differ and both must be active at
creation time. Same-currency transfers require equal amounts. Cross-currency
transfers store both actual amounts; the effective rate is derived for display
and is never used to rewrite history.

Transfer creation, replacement, and deletion are single SQLite transactions
with optimistic concurrency. Transfers never appear in income/expense totals.

## Persistence evolution

### Schema v3 — currency and opening balance

- Add Account currency/opening columns with strict checks.
- Add a currency snapshot to Transaction so historical meaning survives an
  Account rename or later policy change.
- Add indexes for `(account_id, transaction_date)` balance queries.
- Migrate existing rows to `XXX`; do not guess USD, IQD, IRR, or another code.

### Schema v4 — transfers

- Add `transfers` with restrictive Account foreign keys.
- Add a monotonic `transfer` display-ID counter and date/account indexes.
- Extend schema validation, backup validation, integrity tests, and corruption
  tests before enabling the service.

Every migration runs inside `BEGIN IMMEDIATE`, validates the resulting schema
and data, and rolls back fully on failure. The operator creates and verifies a
backup before upgrade; downgrade is offline restore, not reverse SQL.

## Application boundaries

- `Money` and `Transfer`: domain models and invariant validation
- `TransferRepository`: persistence protocol and stale-write errors
- `SQLiteTransferRepository`: SQL mapping and atomic mutations
- `AccountBalanceQuery`: repository projection, not Python full-table loading
- `TransferService`: managed-account checks, clocks, and use-case orchestration
- CLI/Telegram/Excel: presentation only; no balance arithmetic or SQL

`ApplicationServices` composes the new services without global rebinding.

## Delivery sequence and acceptance gates

1. Add `Money`, validators, and isolated domain tests with no schema change.
2. Ship schema v3 migration plus repository parity and rollback tests.
3. Add opening-balance service and per-account/per-currency balance query.
4. Ship schema v4 and first-class same-currency transfers.
5. Add cross-currency debit/credit values and reporting labels.
6. Extend CLI, then Telegram and Excel after service contracts stabilize.
7. Rehearse backup → upgrade → integrity check → restore on a copied workspace.

No phase passes unless pytest/coverage, mypy, Ruff, dependency audit, compile,
package build, installed-command smoke tests, and `git diff --check` all pass.

## Reporting rules

- Never aggregate different currency codes into one number.
- Group summaries by currency when more than one exists.
- Exclude transfers from income, expense, and category-spending totals.
- Include transfers only in account balance and cash-movement views.
- Preserve original debit and credit values for cross-currency transfers.
