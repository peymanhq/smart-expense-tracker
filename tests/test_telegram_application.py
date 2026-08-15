from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

import pytest

from application import build_application
from telegram_application import TelegramApplicationService

TODAY = date(2026, 8, 4)
YESTERDAY = date(2026, 8, 3)
NOW = datetime(2026, 8, 4, 9, 30, tzinfo=timezone.utc)


def build_telegram_service(
    workspace: Path,
    backend: str,
) -> TelegramApplicationService:
    application = build_application(
        workspace,
        backend=backend,
        auto_migrate_json=False,
        today_provider=lambda: TODAY,
        utc_now_provider=lambda: NOW,
    )
    return TelegramApplicationService(application, lambda: TODAY)


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_telegram_application_uses_backend_neutral_managed_workflows(
    tmp_path: Path,
    backend: str,
) -> None:
    service = build_telegram_service(tmp_path, backend)
    cash = service.application.account_service.add_account("Cash").account
    inactive = service.application.account_service.add_account("Old").account
    salary = service.application.category_service.add_category(
        "Salary",
        "income",
    ).category
    food = service.application.category_service.add_category(
        "Food",
        "expense",
    ).category
    assert cash is not None
    assert inactive is not None
    assert salary is not None
    assert food is not None
    service.application.account_service.deactivate_account(inactive.display_id)

    assert service.today() == TODAY
    assert service.list_active_accounts() == [cash]
    assert service.list_active_categories("income") == [salary]
    assert service.list_active_categories("expense") == [food]
    assert service.require_active_account(cash.id) == cash
    assert service.require_active_category(salary.id, "income") == salary

    transaction = service.add_transaction(
        transaction_date=TODAY,
        transaction_type="income",
        amount="1250.50",
        description="Monthly salary",
        account_id=cash.id,
        category_id=salary.id,
    )

    assert transaction.amount == Decimal("1250.50")
    assert transaction.account_id == cash.id
    assert transaction.account == "Cash"
    assert transaction.category_id == salary.id
    assert transaction.category == "Salary"
    assert transaction.transaction_date == TODAY


@pytest.mark.parametrize("backend", ["json", "sqlite"])
def test_telegram_application_calculates_all_time_and_today_summaries(
    tmp_path: Path,
    backend: str,
) -> None:
    service = build_telegram_service(tmp_path, backend)
    account = service.application.account_service.add_account("Cash").account
    income = service.application.category_service.add_category(
        "Salary",
        "income",
    ).category
    expense = service.application.category_service.add_category(
        "Food",
        "expense",
    ).category
    assert account is not None
    assert income is not None
    assert expense is not None

    service.add_transaction(
        transaction_date=YESTERDAY,
        transaction_type="income",
        amount="100",
        description="Previous income",
        account_id=account.id,
        category_id=income.id,
    )
    service.add_transaction(
        transaction_date=TODAY,
        transaction_type="expense",
        amount="25.50",
        description="Lunch",
        account_id=account.id,
        category_id=expense.id,
    )

    all_time = service.all_time_summary()
    today = service.today_summary()

    assert all_time.total_income == Decimal("100")
    assert all_time.total_expense == Decimal("25.50")
    assert all_time.balance == Decimal("74.50")
    assert all_time.transaction_count == 2
    assert today.total_income == Decimal("0")
    assert today.total_expense == Decimal("25.50")
    assert today.balance == Decimal("-25.50")
    assert today.transaction_count == 1


def test_telegram_application_rejects_stale_managed_selections(
    tmp_path: Path,
) -> None:
    service = build_telegram_service(tmp_path, "sqlite")
    account = service.application.account_service.add_account("Cash").account
    category = service.application.category_service.add_category(
        "Food",
        "expense",
    ).category
    assert account is not None
    assert category is not None
    service.application.account_service.deactivate_account(account.display_id)
    service.application.category_service.deactivate_category(category.display_id)

    with pytest.raises(ValueError, match="account is no longer active"):
        service.require_active_account(account.id)
    with pytest.raises(ValueError, match="category is no longer active"):
        service.require_active_category(category.id, "expense")


def test_telegram_application_validates_conversation_values(tmp_path: Path) -> None:
    service = build_telegram_service(tmp_path, "sqlite")

    assert service.validate_amount("10.25") == Decimal("10.25")
    assert service.validate_description("  Lunch  ") == "Lunch"
    with pytest.raises(ValueError, match="greater than zero"):
        service.validate_amount("0")
    with pytest.raises(ValueError, match="Description cannot be empty"):
        service.validate_description("   ")
