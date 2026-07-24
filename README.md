# Smart Expense Tracker

Smart Expense Tracker is a version 1 command-line application for recording
income and expenses in a local JSON file. It supports common transaction
workflows without requiring a database or external service.

## Version status

The current release candidate is **Smart Expense Tracker v1.0.0**. Version 1
stabilization is complete, and the project is ready for its first official
release. It has not yet been published. The implemented scope is intentionally
limited to the command-line and JSON features described below.

The next planned development version is **v1.1.0**.

## Features

- Add income and expense transactions
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

## Running tests

```bash
python -m pytest -q
```

Tests use pytest temporary paths and do not write to
`data/transactions.json`. The v1.0.0 release-candidate suite contains 27
passing tests.

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

## Known limitations

- Local, single-user command-line application only
- No database, GUI, charts, or multi-currency support
- No Excel or PDF export
- No authentication, synchronization, or concurrent-writer coordination
- JSON schema validation is structural; it does not re-run interactive input
  validators on every loaded field
