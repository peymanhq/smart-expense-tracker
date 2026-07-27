"""Service tests that do not depend on JSON paths or storage helpers."""

from dataclasses import replace

from account import Account
from account_service import AccountService
from category import Category
from category_service import CategoryService


class FakeAccountRepository:
    def __init__(self) -> None:
        self.records: list[Account] = []
        self.next_number = 1

    def list_all(self) -> list[Account]:
        return list(self.records)

    def get_by_id(self, account_id: str) -> Account | None:
        return next(
            (record for record in self.records if record.id == account_id),
            None,
        )

    def get_by_display_id(self, display_id: str) -> Account | None:
        normalized = display_id.strip().upper()
        if normalized.startswith("A-") and normalized[2:].isdigit():
            normalized = f"A-{int(normalized[2:]):04d}"
        return next(
            (
                record
                for record in self.records
                if record.display_id == normalized
            ),
            None,
        )

    def create(self, account_id: str, name: str) -> Account:
        account = Account(
            account_id,
            f"A-{self.next_number:04d}",
            name,
        )
        self.next_number += 1
        self.records.append(account)
        return account

    def replace(self, expected: Account, replacement: Account) -> Account:
        index = self.records.index(expected)
        persisted = replace(
            replacement,
            id=expected.id,
            display_id=expected.display_id,
        )
        self.records[index] = persisted
        return persisted


class FakeCategoryRepository:
    def __init__(self) -> None:
        self.records: list[Category] = []
        self.next_number = 1

    def list_all(self) -> list[Category]:
        return list(self.records)

    def get_by_id(self, category_id: str) -> Category | None:
        return next(
            (record for record in self.records if record.id == category_id),
            None,
        )

    def get_by_display_id(self, display_id: str) -> Category | None:
        normalized = display_id.strip().upper()
        if normalized.startswith("C-") and normalized[2:].isdigit():
            normalized = f"C-{int(normalized[2:]):04d}"
        return next(
            (
                record
                for record in self.records
                if record.display_id == normalized
            ),
            None,
        )

    def create(
        self,
        category_id: str,
        name: str,
        transaction_type: str,
    ) -> Category:
        category = Category(
            category_id,
            f"C-{self.next_number:04d}",
            name,
            transaction_type,
        )
        self.next_number += 1
        self.records.append(category)
        return category

    def replace(
        self,
        expected: Category,
        replacement: Category,
    ) -> Category:
        index = self.records.index(expected)
        persisted = replace(
            replacement,
            id=expected.id,
            display_id=expected.display_id,
            transaction_type=expected.transaction_type,
        )
        self.records[index] = persisted
        return persisted


def test_account_service_uses_repository_without_json_paths() -> None:
    repository = FakeAccountRepository()
    service = AccountService(repository)

    created = service.add_account("  Café  ").account
    assert created is not None
    assert created.display_id == "A-0001"
    assert service.add_account("Cafe\u0301").success is False

    deactivated = service.deactivate_account("a-1").account
    assert deactivated is not None
    renamed = service.rename_account("A-0001", " Wallet ").account
    assert renamed is not None
    activated = service.activate_account("A-1").account

    assert activated is not None
    assert activated.id == created.id
    assert activated.display_id == created.display_id
    assert activated.name == "Wallet"
    assert activated.is_active is True
    assert service.list_accounts() == [activated]
    assert service.get_account_by_id(created.id) == activated


def test_category_service_uses_repository_without_json_paths() -> None:
    repository = FakeCategoryRepository()
    service = CategoryService(repository)

    expense = service.add_category("  Café  ", "expense").category
    income = service.add_category("Cafe\u0301", "income").category
    assert expense is not None
    assert income is not None
    assert service.add_category("CAFÉ", "expense").success is False

    deactivated = service.deactivate_category("c-1").category
    assert deactivated is not None
    assert service.add_category("café", "expense").success is True
    assert service.activate_category("C-0001").success is False
    renamed = service.rename_category("C-1", " Dining ").category

    assert renamed is not None
    assert renamed.id == expense.id
    assert renamed.display_id == expense.display_id
    assert renamed.transaction_type == "expense"
    assert renamed.is_active is False
    assert [item.display_id for item in service.list_categories()] == [
        "C-0001",
        "C-0003",
        "C-0002",
    ]
    assert service.get_category_by_id(income.id) == income
