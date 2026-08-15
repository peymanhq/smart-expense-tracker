import asyncio
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from account import Account
from category import Category
from report import FinancialSummary
from telegram.ext import ConversationHandler

from telegram_handlers import (
    CONFIRM,
    DRAFT_KEY,
    ENTER_AMOUNT,
    ENTER_DESCRIPTION,
    SELECT_ACCOUNT,
    SELECT_CATEGORY,
    SELECT_TYPE,
    TelegramHandlers,
    UNAUTHORIZED_MESSAGE,
)
from transaction import Transaction

ALLOWED_USER_ID = 123456789
ACCOUNT_ID = "00000000-0000-4000-8000-000000000001"
CATEGORY_ID = "00000000-0000-4000-8000-000000000002"
TODAY = date(2026, 8, 4)


def run(coroutine):
    return asyncio.run(coroutine)


def make_context():
    return SimpleNamespace(user_data={})


def make_message_update(
    text: str = "",
    *,
    user_id: int = ALLOWED_USER_ID,
):
    message = SimpleNamespace(text=text, reply_text=AsyncMock())
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=message,
        callback_query=None,
    )
    return update, message


def make_callback_update(
    data: str,
    *,
    user_id: int = ALLOWED_USER_ID,
):
    query = SimpleNamespace(
        data=data,
        answer=AsyncMock(),
        edit_message_text=AsyncMock(),
    )
    update = SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id),
        effective_message=None,
        callback_query=query,
    )
    return update, query


def make_service() -> Mock:
    service = Mock()
    service.list_active_accounts.return_value = [
        Account(ACCOUNT_ID, "A-0001", "Cash")
    ]
    service.list_active_categories.return_value = [
        Category(CATEGORY_ID, "C-0001", "Food", "expense")
    ]
    service.require_active_account.return_value = Account(
        ACCOUNT_ID,
        "A-0001",
        "Cash",
    )
    service.require_active_category.return_value = Category(
        CATEGORY_ID,
        "C-0001",
        "Food",
        "expense",
    )
    service.validate_amount.side_effect = lambda value: Decimal(value)
    service.validate_description.side_effect = lambda value: value.strip()
    service.today.return_value = TODAY
    service.all_time_summary.return_value = FinancialSummary(
        Decimal("100"),
        Decimal("25"),
        Decimal("75"),
        2,
    )
    service.summary_for_date.return_value = FinancialSummary(
        Decimal("0"),
        Decimal("25"),
        Decimal("-25"),
        1,
    )
    service.add_transaction.return_value = Transaction(
        id="00000000-0000-4000-8000-000000000003",
        display_id="T-0001",
        type="expense",
        amount=Decimal("25"),
        category="Food",
        account="Cash",
        description="Lunch",
        transaction_date=TODAY,
        account_id=ACCOUNT_ID,
        category_id=CATEGORY_ID,
    )
    return service


def test_unauthorized_user_is_rejected_before_service_call() -> None:
    service = make_service()
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)
    update, message = make_message_update(user_id=999)

    result = run(handlers.add(update, make_context()))

    assert result == ConversationHandler.END
    message.reply_text.assert_awaited_once_with(
        UNAUTHORIZED_MESSAGE,
        reply_markup=None,
    )
    service.list_active_accounts.assert_not_called()


def test_start_help_balance_and_summary_commands() -> None:
    service = make_service()
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)

    for callback in (handlers.start, handlers.help, handlers.balance, handlers.summary):
        update, message = make_message_update()
        run(callback(update, make_context()))
        message.reply_text.assert_awaited_once()

    service.all_time_summary.assert_called_once_with()
    service.summary_for_date.assert_called_once_with(TODAY)


def test_complete_add_conversation_persists_only_after_confirmation() -> None:
    service = make_service()
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)
    context = make_context()

    update, _ = make_message_update("/add")
    assert run(handlers.add(update, context)) == SELECT_TYPE
    service.add_transaction.assert_not_called()

    update, query = make_callback_update("type:expense")
    assert run(handlers.choose_type(update, context)) == SELECT_ACCOUNT
    query.edit_message_text.assert_awaited_once()

    update, _ = make_callback_update(f"account:{ACCOUNT_ID}")
    assert run(handlers.choose_account(update, context)) == SELECT_CATEGORY

    update, _ = make_callback_update(f"category:{CATEGORY_ID}")
    assert run(handlers.choose_category(update, context)) == ENTER_AMOUNT

    update, _ = make_message_update("25")
    assert run(handlers.receive_amount(update, context)) == ENTER_DESCRIPTION

    update, message = make_message_update("  Lunch  ")
    assert run(handlers.receive_description(update, context)) == CONFIRM
    preview = message.reply_text.await_args.args[0]
    assert "Date: 2026-08-04" in preview
    assert "Type: Expense" in preview
    assert "Account: Cash" in preview
    assert "Category: Food" in preview
    assert "Amount: 25.00" in preview
    assert "Description: Lunch" in preview
    service.add_transaction.assert_not_called()

    update, query = make_callback_update("confirm:add")
    assert run(handlers.confirm(update, context)) == ConversationHandler.END

    service.add_transaction.assert_called_once_with(
        transaction_date=TODAY,
        transaction_type="expense",
        amount=Decimal("25"),
        description="Lunch",
        account_id=ACCOUNT_ID,
        category_id=CATEGORY_ID,
    )
    assert DRAFT_KEY not in context.user_data
    query.edit_message_text.assert_awaited_once_with(
        "Transaction T-0001 was added successfully."
    )


def test_invalid_amount_and_description_remain_in_the_current_state() -> None:
    service = make_service()
    service.validate_amount.side_effect = ValueError("Amount must be positive.")
    service.validate_description.side_effect = ValueError("Description is required.")
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)
    context = make_context()

    update, amount_message = make_message_update("0")
    assert run(handlers.receive_amount(update, context)) == ENTER_AMOUNT
    assert "Invalid amount" in amount_message.reply_text.await_args.args[0]

    update, description_message = make_message_update("   ")
    assert run(handlers.receive_description(update, context)) == ENTER_DESCRIPTION
    assert "Invalid description" in description_message.reply_text.await_args.args[0]


def test_cancel_command_and_button_clear_draft_without_persistence() -> None:
    service = make_service()
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)

    for callback_kind in ("command", "button"):
        context = make_context()
        context.user_data[DRAFT_KEY] = {"transaction_type": "expense"}
        if callback_kind == "command":
            update, response = make_message_update("/cancel")
            result = run(handlers.cancel(update, context))
            response.reply_text.assert_awaited_once()
        else:
            update, response = make_callback_update("cancel:add")
            result = run(handlers.cancel_button(update, context))
            response.edit_message_text.assert_awaited_once()
        assert result == ConversationHandler.END
        assert DRAFT_KEY not in context.user_data

    service.add_transaction.assert_not_called()


def test_add_ends_cleanly_when_no_active_accounts_or_categories_exist() -> None:
    service = make_service()
    handlers = TelegramHandlers(service, allowed_user_id=ALLOWED_USER_ID)

    service.list_active_accounts.return_value = []
    context = make_context()
    context.user_data[DRAFT_KEY] = {"transaction_type": "expense"}
    update, query = make_callback_update("type:expense")
    assert run(handlers.choose_type(update, context)) == ConversationHandler.END
    assert "No active accounts" in query.edit_message_text.await_args.args[0]

    service.list_active_accounts.return_value = [
        Account(ACCOUNT_ID, "A-0001", "Cash")
    ]
    service.list_active_categories.return_value = []
    context.user_data[DRAFT_KEY] = {"transaction_type": "expense"}
    update, query = make_callback_update(f"account:{ACCOUNT_ID}")
    assert run(handlers.choose_account(update, context)) == ConversationHandler.END
    assert "No active expense categories" in query.edit_message_text.await_args.args[0]


def test_conversation_registers_cancel_fallback_for_every_state() -> None:
    handlers = TelegramHandlers(make_service(), allowed_user_id=ALLOWED_USER_ID)
    conversation = handlers.conversation_handler()

    assert set(conversation.states) == {
        SELECT_TYPE,
        SELECT_ACCOUNT,
        SELECT_CATEGORY,
        ENTER_AMOUNT,
        ENTER_DESCRIPTION,
        CONFIRM,
    }
    assert any(
        getattr(handler, "commands", frozenset()) == frozenset({"cancel"})
        for handler in conversation.fallbacks
    )
