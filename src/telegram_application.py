"""Telegram-facing use cases built from backend-neutral application services."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from account import Account
from application import ApplicationServices
from category import Category
from report import (
    FinancialSummary,
    calculate_financial_summary,
    generate_daily_summary,
)
from transaction import Transaction
from validators import (
    AmountInput,
    validate_amount,
    validate_required_text,
    validate_transaction_type,
)

TodayProvider = Callable[[], date]


@dataclass(frozen=True)
class TelegramApplicationService:
    """Expose the Telegram MVP workflows without Telegram or persistence APIs."""

    application: ApplicationServices
    today_provider: TodayProvider

    def today(self) -> date:
        """Return the configured Telegram financial date."""
        return self.application.transaction_service.validate_transaction_date(
            self.today_provider()
        )

    def list_active_accounts(self) -> list[Account]:
        return self.application.active_account_list()

    def list_active_categories(self, transaction_type: str) -> list[Category]:
        accepted_type = validate_transaction_type(transaction_type)
        return self.application.active_category_list(
            transaction_type=accepted_type,
        )

    def require_active_account(self, account_id: str) -> Account:
        account = self.application.account_lookup(account_id)
        if account is None or not account.is_active:
            raise ValueError("Selected account is no longer active.")
        return account

    def require_active_category(
        self,
        category_id: str,
        transaction_type: str,
    ) -> Category:
        accepted_type = validate_transaction_type(transaction_type)
        category = self.application.category_lookup(category_id)
        if category is None or not category.is_active:
            raise ValueError("Selected category is no longer active.")
        if category.transaction_type != accepted_type:
            raise ValueError(
                "Selected category is not compatible with the transaction type."
            )
        return category

    def validate_amount(self, value: AmountInput) -> Decimal:
        return validate_amount(value)

    def validate_description(self, value: str) -> str:
        return validate_required_text(value, "Description")

    def add_transaction(
        self,
        *,
        transaction_date: date,
        transaction_type: str,
        amount: AmountInput,
        description: str,
        account_id: str,
        category_id: str,
    ) -> Transaction:
        """Validate and persist one managed transaction through the service."""
        accepted_description = self.validate_description(description)
        return self.application.transaction_service.add_transaction(
            transaction_date=transaction_date,
            transaction_type=transaction_type,
            amount=amount,
            account="",
            category="",
            description=accepted_description,
            account_id=account_id,
            category_id=category_id,
        )

    def all_time_summary(self) -> FinancialSummary:
        transactions = self.application.transaction_service.list_transactions()
        return calculate_financial_summary(transactions)

    def today_summary(self) -> FinancialSummary:
        return self.summary_for_date(self.today())

    def summary_for_date(self, transaction_date: date) -> FinancialSummary:
        transactions = self.application.transaction_service.list_transactions()
        accepted_date = (
            self.application.transaction_service.validate_transaction_date(
                transaction_date
            )
        )
        return generate_daily_summary(transactions, accepted_date)
