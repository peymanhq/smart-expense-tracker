# Smart Expense Tracker

Smart Expense Tracker is a local, SQLite-only personal-finance application with
a command-line interface, a single-user Telegram bot, and safe Excel import and
export workflows.

## Requirements and installation

Python 3.10 or newer is required.

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[dev]"
```

## Commands

```bash
expense-tracker
expense-tracker-storage --help
expense-tracker-telegram
```

The active workspace is the current working directory. Runtime data is stored
in `data/smart_expense_tracker.sqlite3`; generated workbooks default to
`exports/`. Use one consistent working directory for one financial workspace.

## Features

- Income and expense transaction CRUD in a selected financial-date workspace
- Managed Accounts and income/expense Categories
- Stable internal UUIDs and user-facing monotonic display IDs
- Exact `Decimal` amounts and timezone-aware UTC metadata
- Exact-date, range, text, Account, Category, and type filtering
- All-time, daily, range, and UUID-stable Category reports
- Validated atomic Excel import, export, and template generation
- Validated SQLite backup and explicitly confirmed offline restore
- Authorized single-user Telegram add, balance, daily-summary, and Category-report
  workflows

## Telegram bot

```bash
export TELEGRAM_BOT_TOKEN="<bot-token>"
export TELEGRAM_ALLOWED_USER_ID="<numeric-user-id>"
export SMART_EXPENSE_TRACKER_WORKSPACE="$(pwd)"
export TELEGRAM_TIMEZONE="Asia/Baghdad"
expense-tracker-telegram
```

The bot uses foreground long polling and supports `/start`, `/help`, `/add`,
`/cancel`, `/balance`, `/summary`, and `/category`. Category reports support
today, all time, or an inclusive date range. Draft conversations remain in
memory.

## Backup and restore

Create backups outside the live `data/` directory:

```bash
expense-tracker-storage --workspace /path/to/workspace \
  backup /safe/path/tracker.sqlite3
```

Create timestamped backups and retain only the newest seven managed files:

```bash
expense-tracker-storage --workspace /path/to/workspace \
  rotate /safe/path/tracker-backups --keep 7
```

Rotation only removes files matching the program's
`smart-expense-tracker-*.sqlite3` naming contract. It does not provide an
off-device copy; replicate the backup directory independently.

Stop all processes using the workspace before restore and first preserve the
current live database:

```bash
expense-tracker-storage --workspace /path/to/workspace \
  restore /safe/path/tracker.sqlite3 --confirm-overwrite
```

## Quality gates

```bash
python -m pytest --cov --cov-report=term -q
python -m mypy
python -m ruff check src tests
python -m pip_audit --skip-editable
python -m compileall -q src tests
git diff --check
python -m build
```

The project deliberately supports one persistence engine. Legacy JSON backend,
migration code, and compatibility tests were retired after SQLite became the
authoritative store. Existing local JSON files are never deleted automatically.

See [Architecture](docs/ARCHITECTURE.md), [Test Plan](docs/TEST_PLAN.md), and
[Roadmap](docs/ROADMAP.md).
