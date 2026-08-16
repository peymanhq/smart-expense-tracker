"""Telegram presentation handlers for the single-user bot MVP."""

import warnings
from collections.abc import MutableMapping
from datetime import date
from decimal import Decimal
from typing import Any, cast

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    ConversationHandler,
    MessageHandler,
    filters,
)
from telegram.warnings import PTBUserWarning

from persistence_errors import StorageError
from report import FinancialSummary
from telegram_application import TelegramApplicationService, TelegramCategoryReport
from transaction_service import TransactionServiceError

(
    SELECT_TYPE,
    SELECT_ACCOUNT,
    SELECT_CATEGORY,
    ENTER_AMOUNT,
    ENTER_DESCRIPTION,
    CONFIRM,
    REPORT_SELECT_CATEGORY,
    REPORT_SELECT_PERIOD,
    REPORT_ENTER_START,
    REPORT_ENTER_END,
) = range(10)
DRAFT_KEY = "telegram_transaction_draft"
CATEGORY_REPORT_DRAFT_KEY = "telegram_category_report_draft"
UNAUTHORIZED_MESSAGE = "You are not authorized to use this bot."
MAX_CATEGORY_REPORT_TRANSACTIONS = 10
TELEGRAM_MESSAGE_LIMIT = 4096

HELP_TEXT = """Available commands:
/start - Show the welcome message
/help - Show this help
/add - Add an income or expense transaction
/cancel - Cancel the active operation
/balance - Show the all-time financial balance
/summary - Show today's financial summary
/category - Show a Category report"""


def _create_conversation_handler(**kwargs: Any) -> ConversationHandler:
    """Build the deliberate per-user conversation without a noisy PTB warning."""
    with warnings.catch_warnings():
        warnings.filterwarnings(
            "ignore",
            message="If 'per_message=False'.*",
            category=PTBUserWarning,
        )
        return ConversationHandler(**kwargs)


def _summary_text(title: str, summary: FinancialSummary) -> str:
    return (
        f"{title}\n"
        f"Total Income: {summary.total_income:.2f}\n"
        f"Total Expense: {summary.total_expense:.2f}\n"
        f"Balance: {summary.balance:.2f}\n"
        f"Transaction Count: {summary.transaction_count}"
    )


def _short_text(value: object, limit: int = 80) -> str:
    text = str(value).replace("\n", " ").strip()
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _category_report_text(
    report: TelegramCategoryReport,
    period: str,
) -> str:
    category = report.category
    financial = report.financial
    summary = financial.summary
    total = (
        summary.total_income
        if category.transaction_type == "income"
        else summary.total_expense
    )
    status = "Active" if category.is_active else "Inactive"
    lines = [
        "Category Report",
        f"Category: {_short_text(category.name)} ({category.display_id})",
        f"Type: {category.transaction_type.title()}",
        f"Status: {status}",
        f"Period: {period}",
        f"Total {category.transaction_type.title()}: {total:.2f}",
        f"Transaction Count: {summary.transaction_count}",
    ]
    shown = financial.transactions[:MAX_CATEGORY_REPORT_TRANSACTIONS]
    if shown:
        lines.extend(("", "Recent transactions:"))
        lines.extend(
            f"{transaction.display_id} | "
            f"{transaction.transaction_date.isoformat()} | "
            f"{transaction.amount:.2f} | "
            f"{_short_text(transaction.description)}"
            for transaction in shown
        )
        if len(financial.transactions) > len(shown):
            lines.append(
                f"Showing {len(shown)} of {len(financial.transactions)} transactions."
            )
    else:
        lines.extend(("", "No matching transactions found."))
    return "\n".join(lines)[:TELEGRAM_MESSAGE_LIMIT]


class TelegramHandlers:
    """Receive Telegram updates and delegate application work."""

    def __init__(
        self,
        service: TelegramApplicationService,
        *,
        allowed_user_id: int,
    ) -> None:
        self._service = service
        self._allowed_user_id = allowed_user_id

    async def _reply(
        self,
        update: Update,
        text: str,
        *,
        reply_markup: InlineKeyboardMarkup | None = None,
    ) -> None:
        message = update.effective_message
        if message is not None:
            await message.reply_text(text, reply_markup=reply_markup)

    async def _authorize(self, update: Update) -> bool:
        user = update.effective_user
        if user is not None and user.id == self._allowed_user_id:
            return True
        query = update.callback_query
        if query is not None:
            await query.answer(UNAUTHORIZED_MESSAGE, show_alert=True)
        else:
            await self._reply(update, UNAUTHORIZED_MESSAGE)
        return False

    @staticmethod
    def _user_data(
        context: ContextTypes.DEFAULT_TYPE,
    ) -> MutableMapping[str, object]:
        user_data = context.user_data
        if user_data is None:
            raise RuntimeError("Telegram user data is unavailable.")
        return user_data

    @classmethod
    def _draft(
        cls,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> MutableMapping[str, object]:
        user_data = cls._user_data(context)
        draft = user_data.get(DRAFT_KEY)
        if not isinstance(draft, MutableMapping):
            draft = {}
            user_data[DRAFT_KEY] = draft
        return cast(MutableMapping[str, object], draft)

    @classmethod
    def _clear_draft(cls, context: ContextTypes.DEFAULT_TYPE) -> None:
        cls._user_data(context).pop(DRAFT_KEY, None)

    @classmethod
    def _report_draft(
        cls,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> MutableMapping[str, object]:
        user_data = cls._user_data(context)
        draft = user_data.get(CATEGORY_REPORT_DRAFT_KEY)
        if not isinstance(draft, MutableMapping):
            draft = {}
            user_data[CATEGORY_REPORT_DRAFT_KEY] = draft
        return cast(MutableMapping[str, object], draft)

    @classmethod
    def _clear_report_draft(cls, context: ContextTypes.DEFAULT_TYPE) -> None:
        cls._user_data(context).pop(CATEGORY_REPORT_DRAFT_KEY, None)

    @classmethod
    def _clear_all_drafts(cls, context: ContextTypes.DEFAULT_TYPE) -> None:
        cls._clear_draft(context)
        cls._clear_report_draft(context)

    async def start(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        await self._reply(
            update,
            "Welcome to Smart Expense Tracker.\n\n" + HELP_TEXT,
        )

    async def help(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        await self._reply(update, HELP_TEXT)

    async def balance(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        try:
            summary = self._service.all_time_summary()
        except StorageError:
            await self._reply(update, "Unable to load the financial balance.")
            return
        await self._reply(update, _summary_text("All-time Balance", summary))

    async def summary(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if not await self._authorize(update):
            return
        try:
            report_date = self._service.today()
            summary = self._service.summary_for_date(report_date)
        except (StorageError, ValueError):
            await self._reply(update, "Unable to load today's summary.")
            return
        await self._reply(
            update,
            _summary_text(
                f"Today's Summary ({report_date.isoformat()})",
                summary,
            ),
        )

    async def category_report(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        self._clear_all_drafts(context)
        try:
            categories = self._service.list_report_categories()
        except StorageError:
            await self._reply(update, "Unable to load categories for reporting.")
            return ConversationHandler.END
        if not categories:
            await self._reply(update, "No categories are available for reporting.")
            return ConversationHandler.END
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        (
                            f"{category.name} ({category.transaction_type.title()}"
                            f"{'' if category.is_active else ', inactive'})"
                        ),
                        callback_data=f"report-category:{category.id}",
                    )
                ]
                for category in categories
            ]
        )
        await self._reply(
            update,
            "Choose a category for the report:",
            reply_markup=keyboard,
        )
        return REPORT_SELECT_CATEGORY

    async def choose_report_category(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return REPORT_SELECT_CATEGORY
        await query.answer()
        category_id = (query.data or "").partition(":")[2]
        try:
            category = self._service.require_report_category(category_id)
        except StorageError:
            self._clear_report_draft(context)
            await query.edit_message_text("Unable to load the selected category.")
            return ConversationHandler.END
        except ValueError as error:
            self._clear_report_draft(context)
            await query.edit_message_text(str(error))
            return ConversationHandler.END
        draft = self._report_draft(context)
        draft["category_id"] = category.id
        keyboard = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "Today",
                        callback_data="report-period:today",
                    ),
                    InlineKeyboardButton(
                        "All time",
                        callback_data="report-period:all",
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "Date range",
                        callback_data="report-period:range",
                    )
                ],
            ]
        )
        await query.edit_message_text(
            f"Category: {category.name}\nChoose the report period:",
            reply_markup=keyboard,
        )
        return REPORT_SELECT_PERIOD

    def _load_category_report(
        self,
        context: ContextTypes.DEFAULT_TYPE,
        *,
        period: str,
        transaction_date: date | None = None,
        start_date: date | None = None,
        end_date: date | None = None,
    ) -> str:
        draft = self._report_draft(context)
        category_id = cast(str, draft["category_id"])
        report = self._service.category_report(
            category_id,
            transaction_date=transaction_date,
            start_date=start_date,
            end_date=end_date,
        )
        return _category_report_text(report, period)

    async def choose_report_period(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return REPORT_SELECT_PERIOD
        await query.answer()
        period = (query.data or "").partition(":")[2]
        if period == "range":
            await query.edit_message_text("Enter the start date (YYYY-MM-DD):")
            return REPORT_ENTER_START
        try:
            if period == "today":
                report_date = self._service.today()
                text = self._load_category_report(
                    context,
                    period=report_date.isoformat(),
                    transaction_date=report_date,
                )
            elif period == "all":
                text = self._load_category_report(context, period="All time")
            else:
                raise ValueError("Invalid report period.")
        except (KeyError, StorageError, ValueError):
            self._clear_report_draft(context)
            await query.edit_message_text("Unable to load the Category report.")
            return ConversationHandler.END
        self._clear_report_draft(context)
        await query.edit_message_text(text)
        return ConversationHandler.END

    async def receive_report_start_date(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        message = update.effective_message
        value = "" if message is None or message.text is None else message.text
        try:
            start_date = self._service.validate_report_date(value.strip())
        except ValueError as error:
            await self._reply(
                update,
                f"Invalid start date: {error}\nEnter the start date (YYYY-MM-DD):",
            )
            return REPORT_ENTER_START
        self._report_draft(context)["start_date"] = start_date
        await self._reply(update, "Enter the end date (YYYY-MM-DD):")
        return REPORT_ENTER_END

    async def receive_report_end_date(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        message = update.effective_message
        value = "" if message is None or message.text is None else message.text
        try:
            end_date = self._service.validate_report_date(value.strip())
            start_date = cast(date, self._report_draft(context)["start_date"])
            text = self._load_category_report(
                context,
                period=f"{start_date.isoformat()} to {end_date.isoformat()}",
                start_date=start_date,
                end_date=end_date,
            )
        except StorageError:
            self._clear_report_draft(context)
            await self._reply(update, "Unable to load the Category report.")
            return ConversationHandler.END
        except KeyError:
            self._clear_report_draft(context)
            await self._reply(
                update,
                "The Category report draft is no longer available. "
                "Start again with /category.",
            )
            return ConversationHandler.END
        except ValueError as error:
            await self._reply(
                update,
                f"Invalid end date or range: {error}\n"
                "Enter the end date (YYYY-MM-DD):",
            )
            return REPORT_ENTER_END
        self._clear_report_draft(context)
        await self._reply(update, text)
        return ConversationHandler.END

    async def add(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        self._clear_all_drafts(context)
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Income", callback_data="type:income"),
                InlineKeyboardButton("Expense", callback_data="type:expense"),
            ]]
        )
        await self._reply(update, "Choose the transaction type:", reply_markup=keyboard)
        return SELECT_TYPE

    async def choose_type(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return SELECT_TYPE
        await query.answer()
        transaction_type = (query.data or "").partition(":")[2]
        self._draft(context)["transaction_type"] = transaction_type
        try:
            accounts = self._service.list_active_accounts()
        except StorageError:
            self._clear_draft(context)
            await query.edit_message_text("Unable to load active accounts.")
            return ConversationHandler.END
        if not accounts:
            self._clear_draft(context)
            await query.edit_message_text(
                "No active accounts are available. Add or activate an account first."
            )
            return ConversationHandler.END
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(account.name, callback_data=f"account:{account.id}")]
             for account in accounts]
        )
        await query.edit_message_text("Choose an active account:", reply_markup=keyboard)
        return SELECT_ACCOUNT

    async def choose_account(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return SELECT_ACCOUNT
        await query.answer()
        draft = self._draft(context)
        account_id = (query.data or "").partition(":")[2]
        transaction_type = cast(str, draft.get("transaction_type", ""))
        try:
            account = self._service.require_active_account(account_id)
            categories = self._service.list_active_categories(transaction_type)
        except (StorageError, ValueError) as error:
            self._clear_draft(context)
            await query.edit_message_text(str(error))
            return ConversationHandler.END
        if not categories:
            self._clear_draft(context)
            await query.edit_message_text(
                f"No active {transaction_type} categories are available."
            )
            return ConversationHandler.END
        draft["account_id"] = account.id
        draft["account_name"] = account.name
        keyboard = InlineKeyboardMarkup(
            [[InlineKeyboardButton(category.name, callback_data=f"category:{category.id}")]
             for category in categories]
        )
        await query.edit_message_text("Choose an active category:", reply_markup=keyboard)
        return SELECT_CATEGORY

    async def choose_category(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return SELECT_CATEGORY
        await query.answer()
        draft = self._draft(context)
        category_id = (query.data or "").partition(":")[2]
        transaction_type = cast(str, draft.get("transaction_type", ""))
        try:
            category = self._service.require_active_category(
                category_id,
                transaction_type,
            )
        except (StorageError, ValueError) as error:
            self._clear_draft(context)
            await query.edit_message_text(str(error))
            return ConversationHandler.END
        draft["category_id"] = category.id
        draft["category_name"] = category.name
        await query.edit_message_text("Enter a positive amount:")
        return ENTER_AMOUNT

    async def receive_amount(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        message = update.effective_message
        value = "" if message is None or message.text is None else message.text
        try:
            amount = self._service.validate_amount(value)
        except ValueError as error:
            await self._reply(update, f"Invalid amount: {error}\nEnter a positive amount:")
            return ENTER_AMOUNT
        self._draft(context)["amount"] = amount
        await self._reply(update, "Enter a required description:")
        return ENTER_DESCRIPTION

    async def receive_description(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        message = update.effective_message
        value = "" if message is None or message.text is None else message.text
        try:
            description = self._service.validate_description(value)
            transaction_date = self._service.today()
        except ValueError as error:
            await self._reply(
                update,
                f"Invalid description: {error}\nEnter a required description:",
            )
            return ENTER_DESCRIPTION
        draft = self._draft(context)
        draft["description"] = description
        draft["transaction_date"] = transaction_date
        preview = (
            "Confirm transaction:\n"
            f"Date: {transaction_date.isoformat()}\n"
            f"Type: {cast(str, draft['transaction_type']).title()}\n"
            f"Account: {draft['account_name']}\n"
            f"Category: {draft['category_name']}\n"
            f"Amount: {cast(Decimal, draft['amount']):.2f}\n"
            f"Description: {description}"
        )
        keyboard = InlineKeyboardMarkup(
            [[
                InlineKeyboardButton("Confirm", callback_data="confirm:add"),
                InlineKeyboardButton("Cancel", callback_data="cancel:add"),
            ]]
        )
        await self._reply(update, preview, reply_markup=keyboard)
        return CONFIRM

    async def confirm(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        if query is None:
            return CONFIRM
        await query.answer()
        draft = self._user_data(context).get(DRAFT_KEY)
        if not isinstance(draft, MutableMapping):
            await query.edit_message_text(
                "The transaction draft is no longer available. Start again with /add."
            )
            return ConversationHandler.END
        try:
            transaction = self._service.add_transaction(
                transaction_date=cast(date, draft["transaction_date"]),
                transaction_type=cast(str, draft["transaction_type"]),
                amount=cast(Decimal, draft["amount"]),
                description=cast(str, draft["description"]),
                account_id=cast(str, draft["account_id"]),
                category_id=cast(str, draft["category_id"]),
            )
        except KeyError:
            await query.edit_message_text(
                "The transaction draft is incomplete. Start again with /add."
            )
            self._clear_draft(context)
            return ConversationHandler.END
        except (StorageError, TransactionServiceError, ValueError) as error:
            await query.edit_message_text(f"Transaction was not saved: {error}")
            self._clear_draft(context)
            return ConversationHandler.END
        self._clear_draft(context)
        await query.edit_message_text(
            f"Transaction {transaction.display_id} was added successfully."
        )
        return ConversationHandler.END

    async def cancel(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        user_data = self._user_data(context)
        had_transaction_draft = DRAFT_KEY in user_data
        had_report_draft = CATEGORY_REPORT_DRAFT_KEY in user_data
        self._clear_all_drafts(context)
        if had_transaction_draft:
            message = "Operation cancelled. No transaction was saved."
        elif had_report_draft:
            message = "Category report cancelled."
        else:
            message = "There is no active operation to cancel."
        await self._reply(update, message)
        return ConversationHandler.END

    async def cancel_button(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> int:
        if not await self._authorize(update):
            return ConversationHandler.END
        query = update.callback_query
        self._clear_draft(context)
        if query is not None:
            await query.answer()
            await query.edit_message_text(
                "Operation cancelled. No transaction was saved."
            )
        return ConversationHandler.END

    async def use_buttons(
        self,
        update: Update,
        context: ContextTypes.DEFAULT_TYPE,
    ) -> None:
        if await self._authorize(update):
            await self._reply(update, "Please use one of the available buttons.")

    def conversation_handler(self) -> ConversationHandler:
        text_input = filters.TEXT & ~filters.COMMAND
        command_fallbacks: list = [
            CommandHandler("cancel", self.cancel),
            CommandHandler("start", self.start),
            CommandHandler("help", self.help),
            CommandHandler("balance", self.balance),
            CommandHandler("summary", self.summary),
        ]
        return _create_conversation_handler(
            entry_points=[
                CommandHandler("add", self.add),
                CommandHandler("category", self.category_report),
            ],
            states={
                SELECT_TYPE: [
                    CallbackQueryHandler(self.choose_type, pattern=r"^type:(income|expense)$"),
                    MessageHandler(text_input, self.use_buttons),
                ],
                SELECT_ACCOUNT: [
                    CallbackQueryHandler(self.choose_account, pattern=r"^account:"),
                    MessageHandler(text_input, self.use_buttons),
                ],
                SELECT_CATEGORY: [
                    CallbackQueryHandler(self.choose_category, pattern=r"^category:"),
                    MessageHandler(text_input, self.use_buttons),
                ],
                ENTER_AMOUNT: [MessageHandler(text_input, self.receive_amount)],
                ENTER_DESCRIPTION: [
                    MessageHandler(text_input, self.receive_description)
                ],
                CONFIRM: [
                    CallbackQueryHandler(self.confirm, pattern=r"^confirm:add$"),
                    CallbackQueryHandler(self.cancel_button, pattern=r"^cancel:add$"),
                    MessageHandler(text_input, self.use_buttons),
                ],
                REPORT_SELECT_CATEGORY: [
                    CallbackQueryHandler(
                        self.choose_report_category,
                        pattern=r"^report-category:",
                    ),
                    MessageHandler(text_input, self.use_buttons),
                ],
                REPORT_SELECT_PERIOD: [
                    CallbackQueryHandler(
                        self.choose_report_period,
                        pattern=r"^report-period:(today|all|range)$",
                    ),
                    MessageHandler(text_input, self.use_buttons),
                ],
                REPORT_ENTER_START: [
                    MessageHandler(text_input, self.receive_report_start_date)
                ],
                REPORT_ENTER_END: [
                    MessageHandler(text_input, self.receive_report_end_date)
                ],
            },
            fallbacks=command_fallbacks,
            allow_reentry=True,
        )
