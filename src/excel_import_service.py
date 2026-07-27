"""Application workflow for Excel transaction import analysis and persistence."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from account import Account, account_name_key
from category import Category, category_name_key
from excel_import import (
    ExcelImportError,
    ExcelImportIssue,
    ParsedExcelImport,
    parse_excel_transactions,
)
from transaction import (
    Transaction,
    TransactionComparisonKey,
    normalized_transaction_description,
    transaction_comparison_key,
)
from transaction_service import (
    FutureTransactionDateError,
    TransactionBulkConflictError,
    TransactionBulkValidationError,
    TransactionCreateRequest,
    TransactionService,
)

AccountList = Callable[[], list[Account]]
CategoryList = Callable[[], list[Category]]


class InvalidExcelImportPreviewError(ExcelImportError, ValueError):
    """Raised when callers try to persist an invalid preview."""


class ExcelImportPersistenceConflictError(ExcelImportError):
    """Raised when persisted data changes after a valid preview."""

    def __init__(
        self,
        row_number: int,
        *,
        matching_display_id: str | None = None,
        earlier_row_number: int | None = None,
    ) -> None:
        self.row_number = row_number
        self.matching_display_id = matching_display_id
        self.earlier_row_number = earlier_row_number
        if matching_display_id is not None:
            detail = f"existing transaction {matching_display_id}"
        else:
            detail = f"earlier Excel row {earlier_row_number}"
        super().__init__(
            f"Row {row_number}: duplicate conflict with {detail}; "
            "nothing was imported."
        )


class ExcelImportPersistenceValidationError(ExcelImportError):
    """Raised when a managed row changes after preview and before import."""

    def __init__(self, row_number: int, reason: Exception) -> None:
        self.row_number = row_number
        self.reason = reason
        super().__init__(
            f"Row {row_number}: data changed after preview: {reason}; "
            "nothing was imported."
        )


@dataclass(frozen=True)
class ResolvedExcelImportRow:
    """A valid parsed row with managed references resolved to UUIDs."""

    row_number: int
    transaction_date: date
    transaction_type: str
    amount: float
    description: str
    account_name: str
    account_id: str
    category_name: str
    category_id: str

    def comparison_key(self) -> TransactionComparisonKey:
        return (
            self.transaction_date,
            self.transaction_type,
            self.amount,
            normalized_transaction_description(self.description),
            self.account_id,
            self.category_id,
        )

    def create_request(self) -> TransactionCreateRequest:
        return TransactionCreateRequest(
            transaction_date=self.transaction_date,
            transaction_type=self.transaction_type,
            amount=self.amount,
            category=self.category_name,
            account=self.account_name,
            description=self.description,
            account_id=self.account_id,
            category_id=self.category_id,
        )


@dataclass(frozen=True)
class ExcelImportPreview:
    """Complete import analysis suitable for CLI preview and persistence."""

    source_path: Path
    worksheet_name: str
    total_physical_data_rows: int
    empty_rows_ignored: int
    candidates: tuple[ResolvedExcelImportRow, ...]
    issues: tuple[ExcelImportIssue, ...]

    @property
    def valid_candidate_count(self) -> int:
        return len(self.candidates)

    @property
    def invalid_row_count(self) -> int:
        return len(
            {
                issue.row_number
                for issue in self.issues
                if issue.code != "duplicate_conflict"
            }
        )

    @property
    def duplicate_conflict_count(self) -> int:
        return len(
            {
                issue.row_number
                for issue in self.issues
                if issue.code == "duplicate_conflict"
            }
        )

    @property
    def income_transaction_count(self) -> int:
        return sum(
            row.transaction_type == "income" for row in self.candidates
        )

    @property
    def expense_transaction_count(self) -> int:
        return sum(
            row.transaction_type == "expense" for row in self.candidates
        )

    @property
    def total_income(self) -> float:
        return sum(
            row.amount
            for row in self.candidates
            if row.transaction_type == "income"
        )

    @property
    def total_expense(self) -> float:
        return sum(
            row.amount
            for row in self.candidates
            if row.transaction_type == "expense"
        )

    @property
    def net_balance_impact(self) -> float:
        return self.total_income - self.total_expense

    @property
    def is_valid(self) -> bool:
        return not self.issues


@dataclass(frozen=True)
class ExcelImportResult:
    """Successful atomic import result."""

    source_path: Path
    worksheet_name: str
    transactions: tuple[Transaction, ...]
    total_income: float
    total_expense: float
    net_balance_impact: float

    @property
    def imported_count(self) -> int:
        return len(self.transactions)


def _issue(
    row_number: int,
    message: str,
    code: str,
    *,
    field: str | None = None,
    supplied_value: object | None = None,
    matching_display_id: str | None = None,
    earlier_row_number: int | None = None,
) -> ExcelImportIssue:
    return ExcelImportIssue(
        row_number=row_number,
        message=message,
        code=code,
        field=field,
        supplied_value=supplied_value,
        matching_display_id=matching_display_id,
        earlier_row_number=earlier_row_number,
    )


def _existing_comparison_key(
    transaction: Transaction,
    accounts_by_name: dict[str, list[Account]],
    categories_by_name: dict[str, list[Category]],
) -> TransactionComparisonKey | None:
    """Resolve legacy snapshots when possible for stored duplicate checks."""
    account_id = transaction.account_id
    if account_id is None:
        account_id = next(
            (
                account.id
                for account in accounts_by_name.get(
                    account_name_key(transaction.account),
                    [],
                )
                if account.is_active
            ),
            None,
        )
    category_id = transaction.category_id
    if category_id is None:
        category_id = next(
            (
                category.id
                for category in categories_by_name.get(
                    category_name_key(transaction.category),
                    [],
                )
                if category.is_active
                and category.transaction_type == transaction.type
            ),
            None,
        )
    if account_id is None or category_id is None:
        return transaction_comparison_key(transaction)
    return (
        transaction.transaction_date,
        transaction.type,
        transaction.amount,
        normalized_transaction_description(transaction.description),
        account_id,
        category_id,
    )


class ExcelImportService:
    """Analyze workbooks and delegate one atomic mutation to transactions."""

    def __init__(
        self,
        transaction_service: TransactionService,
        *,
        account_list: AccountList,
        category_list: CategoryList,
    ) -> None:
        self._transaction_service = transaction_service
        self._account_list = account_list
        self._category_list = category_list

    def _resolve_account(
        self,
        row_number: int,
        supplied_name: str,
        accounts_by_name: dict[str, list[Account]],
    ) -> tuple[Account | None, ExcelImportIssue | None]:
        matches = accounts_by_name.get(account_name_key(supplied_name), [])
        active = next(
            (account for account in matches if account.is_active),
            None,
        )
        if active is not None:
            return active, None
        if matches:
            return None, _issue(
                row_number,
                f"Account '{supplied_name}' is inactive.",
                "inactive_account",
                field="Account",
                supplied_value=supplied_name,
            )
        return None, _issue(
            row_number,
            f"Account '{supplied_name}' was not found.",
            "unknown_account",
            field="Account",
            supplied_value=supplied_name,
        )

    def _resolve_category(
        self,
        row_number: int,
        supplied_name: str,
        transaction_type: str,
        categories_by_name: dict[str, list[Category]],
    ) -> tuple[Category | None, ExcelImportIssue | None]:
        matches = categories_by_name.get(
            category_name_key(supplied_name),
            [],
        )
        matching_type = [
            category
            for category in matches
            if category.transaction_type == transaction_type
        ]
        active = next(
            (category for category in matching_type if category.is_active),
            None,
        )
        if active is not None:
            return active, None
        if matching_type:
            return None, _issue(
                row_number,
                f"Category '{supplied_name}' is inactive.",
                "inactive_category",
                field="Category",
                supplied_value=supplied_name,
            )
        if matches:
            return None, _issue(
                row_number,
                f"Category '{supplied_name}' is not compatible with "
                f"{transaction_type.title()} transactions.",
                "category_type_mismatch",
                field="Category",
                supplied_value=supplied_name,
            )
        return None, _issue(
            row_number,
            f"Category '{supplied_name}' was not found.",
            "unknown_category",
            field="Category",
            supplied_value=supplied_name,
        )

    def analyze(self, source: Path | str) -> ExcelImportPreview:
        """Parse, resolve, validate, and detect every duplicate conflict."""
        parsed: ParsedExcelImport = parse_excel_transactions(source)
        accounts_by_name: dict[str, list[Account]] = {}
        for account in self._account_list():
            accounts_by_name.setdefault(
                account_name_key(account.name),
                [],
            ).append(account)
        categories_by_name: dict[str, list[Category]] = {}
        for category in self._category_list():
            categories_by_name.setdefault(
                category_name_key(category.name),
                [],
            ).append(category)

        issues = list(parsed.issues)
        resolved_rows: list[ResolvedExcelImportRow] = []
        for row in parsed.rows:
            row_issues: list[ExcelImportIssue] = []
            try:
                accepted_date = (
                    self._transaction_service.validate_transaction_date(
                        row.transaction_date
                    )
                )
            except FutureTransactionDateError as error:
                row_issues.append(
                    _issue(
                        row.row_number,
                        f"Date is not allowed: {error}",
                        "invalid_date",
                        field="Date",
                        supplied_value=row.transaction_date,
                    )
                )
                accepted_date = None
            account, account_issue = self._resolve_account(
                row.row_number,
                row.account_name,
                accounts_by_name,
            )
            if account_issue is not None:
                row_issues.append(account_issue)
            category, category_issue = self._resolve_category(
                row.row_number,
                row.category_name,
                row.transaction_type,
                categories_by_name,
            )
            if category_issue is not None:
                row_issues.append(category_issue)
            if row_issues:
                issues.extend(row_issues)
                continue
            assert accepted_date is not None
            assert account is not None
            assert category is not None
            resolved_rows.append(
                ResolvedExcelImportRow(
                    row_number=row.row_number,
                    transaction_date=accepted_date,
                    transaction_type=row.transaction_type,
                    amount=row.amount,
                    description=row.description,
                    account_name=account.name,
                    account_id=account.id,
                    category_name=category.name,
                    category_id=category.id,
                )
            )

        existing_by_key = {
            key: transaction
            for transaction in self._transaction_service.list_transactions()
            if (
                key := _existing_comparison_key(
                    transaction,
                    accounts_by_name,
                    categories_by_name,
                )
            )
            is not None
        }
        accepted_rows: list[ResolvedExcelImportRow] = []
        earlier_rows: dict[TransactionComparisonKey, int] = {}
        for row in resolved_rows:
            key = row.comparison_key()
            existing = existing_by_key.get(key)
            if existing is not None:
                issues.append(
                    _issue(
                        row.row_number,
                        "Duplicate transaction matches existing transaction "
                        f"{existing.display_id}.",
                        "duplicate_conflict",
                        matching_display_id=existing.display_id,
                    )
                )
                continue
            earlier_row = earlier_rows.get(key)
            if earlier_row is not None:
                issues.append(
                    _issue(
                        row.row_number,
                        "Duplicate transaction matches earlier Excel row "
                        f"{earlier_row}.",
                        "duplicate_conflict",
                        earlier_row_number=earlier_row,
                    )
                )
                continue
            earlier_rows[key] = row.row_number
            accepted_rows.append(row)

        return ExcelImportPreview(
            source_path=parsed.source_path,
            worksheet_name=parsed.worksheet_name,
            total_physical_data_rows=parsed.total_physical_data_rows,
            empty_rows_ignored=parsed.empty_rows_ignored,
            candidates=tuple(accepted_rows),
            issues=tuple(sorted(issues, key=lambda issue: issue.row_number)),
        )

    def persist(self, preview: ExcelImportPreview) -> ExcelImportResult:
        """Persist one valid preview through one atomic service call."""
        if not preview.is_valid:
            raise InvalidExcelImportPreviewError(
                "Excel import preview contains validation or duplicate issues."
            )
        requests = [row.create_request() for row in preview.candidates]
        try:
            transactions = self._transaction_service.add_transactions(requests)
        except TransactionBulkValidationError as error:
            row = preview.candidates[error.candidate_index]
            raise ExcelImportPersistenceValidationError(
                row.row_number,
                error.reason,
            ) from error
        except TransactionBulkConflictError as error:
            row = preview.candidates[error.candidate_index]
            earlier_row_number = (
                preview.candidates[error.earlier_candidate_index].row_number
                if error.earlier_candidate_index is not None
                else None
            )
            raise ExcelImportPersistenceConflictError(
                row.row_number,
                matching_display_id=error.matching_display_id,
                earlier_row_number=earlier_row_number,
            ) from error
        return ExcelImportResult(
            source_path=preview.source_path,
            worksheet_name=preview.worksheet_name,
            transactions=tuple(transactions),
            total_income=preview.total_income,
            total_expense=preview.total_expense,
            net_balance_impact=preview.net_balance_impact,
        )
