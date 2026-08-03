# Smart Expense Tracker

Smart Expense Tracker is a local command-line application for recording
income and expenses. Starting with v1.5.0, SQLite is the default storage
backend, with automatic non-destructive migration from existing JSON
workspaces and an explicit JSON compatibility mode.

## Version status

**Smart Expense Tracker v1.5.0** is the current released version. It uses
SQLite as the default storage backend, automatically migrates valid legacy JSON
data on first startup when no SQLite database exists, and keeps JSON available
through an explicit compatibility override.

## Features

- Use a selected-date transaction workspace that starts on today
- Add income and expense transactions for today or a selected historical date
- View, update, and delete transactions within the active financial date
- Move a transaction explicitly from one financial date to another
- Browse populated transaction dates and their transaction counts
- Add, view, rename, deactivate, and reactivate accounts
- Add, view, rename, activate, and deactivate income/expense categories
- Search and filter by exact date or inclusive date range
- Calculate all-time, daily, and inclusive date-range financial reports
- Export all transactions and financial summaries to an Excel workbook
- Generate a guided Excel import template from active Accounts and Categories
- Validate, preview, and atomically import new transactions from `.xlsx`
- Validate amounts, dates, transaction types, and required fields
- Persist data locally in SQLite by default
- Keep an internal UUID separate from the user-facing display ID
- Write JSON atomically to reduce the risk of partial-file corruption
- Migrate validated JSON data to SQLite without modifying the JSON source

## Project structure

```text
smart-expense-tracker/
├── .github/workflows/ci.yml # Automated test and build quality gates
├── data/                    # Workspace SQLite or compatibility JSON data
├── pyproject.toml           # Canonical packaging and dependency metadata
├── src/
│   ├── main.py              # CLI and workflow orchestration
│   ├── account.py           # Account dataclass
│   ├── account_service.py   # Account validation and business operations
│   ├── account_storage.py   # Validated, locked account JSON persistence
│   ├── category.py          # Category dataclass
│   ├── category_service.py  # Category validation and business operations
│   ├── category_storage.py  # Validated, locked category JSON persistence
│   ├── json_storage.py      # Shared atomic JSON writer
│   ├── sqlite_database.py   # SQLite connection and transaction boundary
│   ├── sqlite_schema.py     # Versioned SQLite schema validation
│   ├── sqlite_migration.py  # Non-destructive JSON-to-SQLite migration
│   ├── sqlite_backup.py     # Validated atomic backup/offline restore CLI
│   ├── sqlite_*_repository.py # SQLite repository implementations
│   ├── storage.py           # Versioned, locked transaction JSON storage
│   ├── transaction_repository.py
│   ├── transaction_service.py
│   ├── clock.py             # Injectable date/time providers
│   ├── date_policy.py       # Shared financial-date query policy
│   ├── formatter.py         # Transaction display formatting
│   ├── validators.py        # User-input validation
│   ├── transaction.py       # Transaction dataclass
│   ├── transaction_factory.py
│   ├── id_generator.py      # UUID and display-ID formatting/calculation
│   ├── report.py            # Summary and filtering logic
│   ├── excel_exporter.py    # Formatted, atomic .xlsx report generation
│   ├── excel_workbook.py    # Shared workbook contract and atomic output
│   ├── excel_import.py      # Defensive workbook parsing and row issues
│   ├── excel_import_service.py # Resolution, preview, duplicates, persistence
│   ├── excel_template.py    # Guided import-template generation
│   └── search.py            # Search and exact display-ID lookup
├── tests/                   # pytest automated tests
├── requirements.txt
└── README.md
```

## Installation

Python 3.10 or newer is required.

Create and activate a virtual environment:

```bash
python3 -m venv .venv
source .venv/bin/activate
```

On Windows PowerShell, activate it with:

```powershell
.venv\Scripts\Activate.ps1
```

Install the project and its development dependencies:

```bash
python -m pip install -e ".[dev]"
```

`pyproject.toml` is the canonical dependency definition. For compatibility,
running `python -m pip install -r requirements.txt` from the repository root
performs the same editable development installation. A runtime-only
installation uses `python -m pip install .`.

## Running the application

After installation, run:

```bash
expense-tracker
```

The direct development workflow remains available from the repository root:

```bash
python3 src/main.py
```

Runtime data is resolved from `data/` beneath the current working directory.
SQLite is primary; compatibility JSON files use the same directory. Run the
command from the workspace whose data you intend to use. This preserves
the repository-root workflow and prevents an installed wheel from writing data
inside site-packages or a virtual environment. Default Excel output similarly
uses `exports/` beneath the current working directory.

Changing directories selects a different, independent workspace. For example,
running once from `Documents` and later from `Desktop` uses different `data/`
directories, so the earlier records will appear missing until the command is
run again from `Documents`. Use one consistent workspace directory for normal
operation.

## Storage backends

SQLite is the default. Start normally to create or open
`data/smart_expense_tracker.sqlite3` in the current workspace:

```bash
expense-tracker
```

If the SQLite database does not exist but any recognized JSON persistence file
does, startup validates and migrates the JSON workspace automatically. UUIDs,
display IDs, timestamps, managed references, and next-ID counters are preserved;
the source JSON files are not changed or deleted. A malformed JSON source stops
startup instead of silently creating an empty database.

Automatic migration runs only when the SQLite database path does not exist. An
existing empty database suppresses automation; when compatibility JSON also
exists, the CLI prints the exact explicit-migration setting instead of silently
presenting the situation as complete. An explicit migration command remains
available for controlled recovery or an immediate retry:

```bash
SMART_EXPENSE_TRACKER_BACKEND=sqlite \
SMART_EXPENSE_TRACKER_MIGRATE_JSON=1 \
expense-tracker
```

Migration validates and snapshots all JSON records under their existing locks,
preserves UUIDs, display IDs, timestamps, managed references, and next-ID
counters, then imports them through one SQLite transaction. Source JSON files
are never changed or deleted. The destination must be empty, or exactly match a
previous completed migration. After migration, omit
`SMART_EXPENSE_TRACKER_MIGRATE_JSON`; otherwise later SQLite changes will
correctly make the stale JSON snapshot differ and migration will be refused.

Use the JSON repository only as an explicit compatibility backend:

```bash
SMART_EXPENSE_TRACKER_BACKEND=json expense-tracker
```

Switching backends selects independent live stores. After SQLite receives new
writes, preserved JSON is a stale compatibility snapshot rather than a live
mirror.

### SQLite backup and rollback runbook

Stop every Smart Expense Tracker process that uses the workspace before a
restore or backend cutover. Create a backup outside the live `data/` directory:

```bash
expense-tracker-storage \
  --workspace /path/to/workspace \
  backup /safe/path/smart-expense-before-change.sqlite3
```

Existing backup destinations are refused. Use `--overwrite` only when replacing
that exact backup is intentional. The command validates the source schema,
copies through SQLite's online backup API into a same-directory temporary file,
validates the copy, flushes it, and atomically replaces the requested output.

Before a restore, first create another backup of the current live database.
Then, while all application processes remain stopped, run:

```bash
expense-tracker-storage \
  --workspace /path/to/workspace \
  restore /safe/path/smart-expense-before-change.sqlite3 \
  --confirm-overwrite
```

The confirmation flag is mandatory when a live database exists. The backup is
validated before the live path is touched, and restore uses validated temporary
output plus atomic replacement.

For immediate rollback directly after JSON migration, before any SQLite-only
writes, unset both SQLite environment variables and start normally to return to
the unchanged JSON source. After new SQLite writes, JSON is stale and must not
be treated as a lossless rollback target. Continue with SQLite or restore a
known SQLite backup instead.

Choose **Transaction Management** to open a date-scoped workspace. It starts
with today as the active date. Change the active date to enter or manage
historical transactions; adding a transaction uses that active date and does
not prompt for another date. The active date lasts only for that workspace
session, and reopening the workspace starts from today again.

Example:

```text
=== Transaction Management ===
Active date: 2026-07-24
1. Add transaction
2. View transactions
3. Update transaction
4. Delete transaction
5. Change active date
6. Browse transaction dates
7. Return to today
0. Back
===>Choose an option: 1
Choose transaction type: 2
Amount: 12.50
Account ID: A-0001
Category ID: C-0001
Description: Lunch
Transaction T-0001 added for 2026-07-24.
```

Transaction-date input accepts numeric `YYYY-M-D` or `YYYY-MM-DD` text,
normalizes it to `YYYY-MM-DD`, rejects impossible calendar dates, and does not
allow future financial dates.

Use the shown display ID, such as `T-0001`, when updating or deleting a
transaction. Display-ID lookup ignores surrounding whitespace and letter case,
but otherwise requires an exact match. An update or deletion must be initiated
from the transaction's active date. Updates may explicitly move the transaction
to another valid date.

Search supports no date constraint, one exact financial date, or an inclusive
date range. The Python filtering API also supports one-sided ranges. Results
are ordered by newest financial date and then ascending numeric display ID.
Financial Reports provides all-time, daily, and inclusive date-range totals for
income, expenses, balance, and transaction count.

Choose **Export transactions to Excel** from the main menu to create a
formatted workbook. Press Enter at the destination prompt to use
`exports/smart_expense_tracker_YYYY-MM-DD.xlsx`, or enter another path. A
missing extension is normalized to `.xlsx`; other extensions are rejected. If
the destination exists, the CLI asks before overwriting it.

The export workbook contains:

- **Transactions** — display ID, financial transaction date, readable type,
  amount, description, resolved Account and Category names, and optional
  creation/update timestamps. Internal UUIDs are not exposed.
- **Summary** — total income, total expense, balance, and total/income/expense
  transaction counts.
- **Category Summary** — category/type totals and counts, with income and
  expense groups kept separate.

For example, choose menu option `7`, press Enter to accept the default path,
and confirm overwrite only if a report for that date already exists. Workbook
writes use a temporary file and atomic replacement, so a failed save does not
leave a partial final report.

Choose **Generate Excel import template** to create
`exports/smart_expense_tracker_import_template_YYYY-MM-DD.xlsx`. The workbook
contains visible **Instructions**, **Transactions**, and **Reference Data**
worksheets. The entry sheet has dropdowns for `Income`/`Expense`, active
Account names, and active Categories filtered by each row's selected Type.
Changing Type does not clear an earlier Category selection, so select the
Category again; the importer remains authoritative and rejects stale,
incompatible values. Reference Data never exposes internal UUIDs.

Choose **Import transactions from Excel** and provide an `.xlsx` file with a
worksheet named exactly `Transactions`. Its required headers are:

```text
Date | Type | Amount | Description | Account | Category
```

Header matching ignores surrounding whitespace and letter case. Additional
columns are allowed; Display ID, UUID, Created At, and Updated At values never
control imported identity. `Transaction Date` is accepted only as the
compatibility name used by v1.2.0/v1.3.0 exports. New exports and templates use
the canonical `Date` header.

Dates may be real Excel dates/datetimes or the application's supported
`YYYY-M-D`/`YYYY-MM-DD` text. Types are `Income` or `Expense`; amounts must be
finite and greater than zero. Account and Category fields resolve trimmed,
Unicode-normalized, case-insensitive names to active managed records. The
Category must match the transaction type. Completely empty rows are ignored;
all other invalid rows are reported with their Excel row numbers.

Before confirmation, the CLI shows transaction counts, income, expense, and
net impact. It also checks deterministic duplicates against stored
transactions and earlier workbook rows using financial date, type, amount,
normalized description, Account UUID, and Category UUID. Any validation or
duplicate conflict imports zero rows. On confirmation, all rows receive new
UUIDs, monotonic display IDs, and timestamps, then persist through one lock and
one atomic JSON replacement. Excel import creates new transactions only; it
does not update records, restore IDs/timestamps, create Accounts/Categories, or
partially import a workbook.

Choose **Account Management** to add, list, rename, deactivate, or reactivate
accounts. Accounts use display IDs such as `A-0001`. Deactivation preserves
the account record and reactivation restores it unless another active account
has the same name. Permanent deletion is not available. Account records are
used by transaction entry and updates through managed selection.

Only active account names must be unique. A new account may reuse an inactive
account's name, and an inactive account may be renamed to match an active
account. Reactivation remains blocked until that active-name conflict is
resolved.

Account display-ID input ignores surrounding whitespace, letter case, and
zero-padding differences, so values such as `a-1` resolve to `A-0001`.

Choose **Category Management** to add, list, rename, activate, or deactivate
income and expense categories. Categories use persistent display IDs such as
`C-0001`. The CLI uses a numbered Income/Expense choice, and list output is
ordered by transaction type and then display ID. Transaction entry and updates
offer active categories compatible with the transaction type.

Only active category names must be unique within the same transaction type,
using trimmed, Unicode-normalized, case-insensitive comparison. `Food /
expense` and `Food / income` may coexist. An inactive name may be reused or
renamed to match an active category, but activation is blocked while an active
category of the same type has that name.

## Running tests

```bash
python -m pytest -q
```

Tests use pytest temporary paths and do not write to application data files.
The v1.5.0 release verification suite contains 609 passing tests.
Compile the source and verify whitespace:

```bash
python -m compileall -q src tests
git diff --check
```

Build the source distribution and wheel:

```bash
python -m build
```

GitHub Actions runs these test, compile, whitespace, build, and installed-command
checks on Python 3.10 and 3.13 for changes targeting `main`.

## JSON compatibility persistence

When the explicit JSON compatibility backend is selected, transaction data is
stored in `data/transactions.json`. The stabilized format is:

```json
{
    "schema_version": 3,
    "metadata": {
        "next_display_id": 3
    },
    "transactions": [
        {
            "id": "1a26f4c8-2bcc-4ad4-9f79-3bf07bc8a5ef",
            "display_id": "T-0001",
            "type": "expense",
            "amount": 12.5,
            "category": "Food",
            "category_id": "category-uuid-or-null",
            "account": "Cash",
            "account_id": "account-uuid-or-null",
            "description": "Lunch",
            "transaction_date": "2026-07-24",
            "created_at": "2026-07-24T09:15:00+00:00",
            "updated_at": "2026-07-24T09:15:00+00:00"
        }
    ]
}
```

`transaction_date` is the financial date used by workspaces, search, and
reports. `created_at` and `updated_at` are optional timezone-aware UTC metadata
and never select a financial period. The internal `id` is a UUID used to
preserve transaction identity. The `display_id` is the shorter ID shown to
users. Both values remain unchanged during an update.

`metadata.next_display_id` is persistent and monotonically advances when a
transaction is saved. Deleting `T-0003` does not make it available again; the
next saved transaction uses `T-0004`. Older files containing only a JSON list
remain readable. Their safe next value is derived from the highest stored
display ID. Legacy `date` fields map to `transaction_date`; missing historical
timestamps remain `null` rather than being invented. Reads never migrate data,
while the next successful mutation writes schema version 3. Schema versions 1
and 2 load missing `account_id` and `category_id` values as `None`; schema
version 3 writes missing references explicitly as `null`. The required account
and category names remain stored snapshots and fallbacks.

A missing or blank data file is treated as an empty dataset. Malformed JSON or
an invalid top-level structure raises a controlled storage error and is not
overwritten. Saves are written to a temporary file in the data directory and
atomically replace the destination with `os.replace` only after the complete
content is flushed. If writing or replacement fails, the temporary file is
removed and the previous data file remains intact.

Complete transaction mutations use a cross-process lock. Creation loads the
latest document, allocates and advances the global display-ID counter, validates
the candidate document, and writes it atomically while holding one lock.
Account and category storage remains separate from transaction persistence.

`TransactionService` can accept optional Account and Category UUIDs through
injected public lookups. New managed selections must exist and be active;
managed categories must match the transaction type, and managed names override
caller-provided snapshot text. Omitted references preserve legacy free-text
behavior. Existing inactive references remain valid for unrelated historical
updates.

Transaction add and update prompts list active managed records as
`display ID - name`. Users select those display IDs, while the CLI passes the
corresponding UUIDs to `TransactionService`; display IDs are not stored as
foreign keys. Legacy snapshot-only transactions can be linked during update,
and leaving a replacement blank preserves an inactive historical reference.

Accounts are stored separately in `data/accounts.json` as one document
containing display-ID metadata and the account list. This makes an account
change and its next-ID advancement one atomic file replacement. Account
read-modify-write operations also use a cross-process file lock to prevent
lost updates when multiple application instances run concurrently.

The earlier list-only `accounts.json` and companion `accounts_state.json`
format remains readable. Its highest safe next ID is preserved and migrated
into the single-document format on the next successful account save.

Categories start with the current format: `data/categories.json` is a JSON list
of category objects, and `data/categories_state.json` stores the monotonic
`next_display_id` counter. There is no invented legacy Category format. Both
files use atomic replacement, and complete category read-modify-write
operations use a file lock. Counter state is written before a newly allocated
record, so a failed save may leave an intentional ID gap but cannot reuse an
ID. If state is missing, it is recovered from the highest stored category ID.

## Known limitations

- Local, single-user command-line application only
- No GUI, charts, or multi-currency support
- No PDF export or workbook charts
- No authentication or synchronization
- Transactions use managed Account and Category selection in the CLI, but
  explicit unlinking and automatic legacy reconciliation are not implemented
- Referential integrity remains soft when the JSON compatibility backend is
  selected; primary SQLite storage enforces managed foreign keys
- Transfers are not implemented
- Transaction amounts still use `float`; exact `Decimal` money is deferred

## Release history

### v1.5.0

- SQLite is now the default storage backend.
- Automatic migration from legacy JSON workspaces.
- Atomic backup and restore.
- Complete SQLite repository implementation.

### v1.4.0

- Excel import.
- Excel template generation.
- Safer workbook validation.
