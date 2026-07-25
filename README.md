# Smart Expense Tracker

Smart Expense Tracker is a version 1 command-line application for recording
income and expenses in a local JSON file. It supports common transaction
workflows without requiring a database or external service.

## Version status

**Smart Expense Tracker v1.0.0** is the published stable baseline. Development
of **v1.1.0** is in progress. Standalone Account Management and standalone
Category Management are implemented; the rest of v1.1.0 is not complete.

## Features

- Add income and expense transactions
- Add, view, rename, deactivate, and reactivate accounts
- Add, view, rename, activate, and deactivate income/expense categories
- View, search, and filter transactions
- Update or delete a transaction by its display ID
- Calculate total income, total expense, and current balance
- Validate amounts, dates, transaction types, and required fields
- Persist data locally in JSON
- Keep an internal UUID separate from the user-facing display ID
- Write JSON atomically to reduce the risk of partial-file corruption

## Project structure

```text
smart-expense-tracker/
├── data/                    # Runtime JSON data (created when needed)
├── src/
│   ├── main.py              # CLI and workflow orchestration
│   ├── account.py           # Account dataclass
│   ├── account_service.py   # Account validation and business operations
│   ├── account_storage.py   # Validated, locked account JSON persistence
│   ├── category.py          # Category dataclass
│   ├── category_service.py  # Category validation and business operations
│   ├── category_storage.py  # Validated, locked category JSON persistence
│   ├── json_storage.py      # Shared atomic JSON writer
│   ├── storage.py           # JSON loading, validation, and atomic saving
│   ├── formatter.py         # Transaction display formatting
│   ├── validators.py        # User-input validation
│   ├── transaction.py       # Transaction dataclass
│   ├── transaction_factory.py
│   ├── id_generator.py      # UUID and display-ID formatting/calculation
│   ├── report.py            # Summary and filtering logic
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

Install the development dependency:

```bash
python -m pip install -r requirements.txt
```

## Running the application

From the repository root:

```bash
python src/main.py
```

Choose a numbered menu action and follow the prompts. Dates use `YYYY-MM-DD`,
and amounts must be greater than zero.

Example:

```text
=== Smart Expense Tracker ===
1. Add Income
2. Add Expense
...
===>Choose an option: 2
Amount: 12.50
Category: Food
Account: Cash
Description: Lunch
Date: 2026-07-24
Expense saved successfully.
```

Use the shown display ID, such as `T-0001`, when updating or deleting a
transaction. Display-ID lookup ignores surrounding whitespace and letter case,
but otherwise requires an exact match.

Choose **Account Management** to add, list, rename, deactivate, or reactivate
accounts. Accounts use display IDs such as `A-0001`. Deactivation preserves
the account record and reactivation restores it unless another active account
has the same name. Permanent deletion is not available. Account records are
not yet used by transaction entry in this development phase.

Only active account names must be unique. A new account may reuse an inactive
account's name, and an inactive account may be renamed to match an active
account. Reactivation remains blocked until that active-name conflict is
resolved.

Account display-ID input ignores surrounding whitespace, letter case, and
zero-padding differences, so values such as `a-1` resolve to `A-0001`.

Choose **Category Management** to add, list, rename, activate, or deactivate
standalone income and expense categories. Categories use persistent display
IDs such as `C-0001`. The CLI uses a numbered Income/Expense choice, and list
output is ordered by transaction type and then display ID.

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
The current suite contains 131 passing tests.

## JSON persistence

Runtime data is stored in `data/transactions.json`. The stabilized format is:

```json
{
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
            "account": "Cash",
            "description": "Lunch",
            "date": "2026-07-24"
        }
    ]
}
```

The internal `id` is a UUID used to preserve transaction identity. The
`display_id` is the shorter ID shown to users. Both values remain unchanged
during an update.

`metadata.next_display_id` is persistent and monotonically advances when a
transaction is saved. Deleting `T-0003` does not make it available again; the
next saved transaction uses `T-0004`. Older files containing only a JSON list
remain readable. Their safe next value is derived from the highest stored
display ID, and the file is migrated to the metadata format on its next write.

A missing or blank data file is treated as an empty dataset. Malformed JSON or
an invalid top-level structure raises a controlled storage error and is not
overwritten. Saves are written to a temporary file in the data directory and
atomically replace the destination with `os.replace` only after the complete
content is flushed. If writing or replacement fails, the temporary file is
removed and the previous data file remains intact.

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
- No database, GUI, charts, or multi-currency support
- No Excel or PDF export
- No authentication or synchronization
- Transaction persistence still has no concurrent-writer coordination
- Accounts and categories are not yet linked to transactions
- Transactions still store their existing free-text `category` and `account`
  fields; there is no `category_id` or transaction-data migration
- Transfers, default transaction dates, and Excel import/export are not
  implemented
- Transaction JSON validation remains primarily structural; account JSON
  and category JSON validate field types, UUID and display-ID formats, and
  uniqueness invariants
