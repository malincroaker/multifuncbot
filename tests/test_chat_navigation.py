import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import CallbackQuery, Chat, Message, Update, User
from telegram.error import BadRequest, TimedOut

from multifuncbot.app import build_application
from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.models import Button, Screen
from multifuncbot.core.router import Router
from multifuncbot.telegram_ui import TelegramUI


@pytest.fixture
def db(tmp_path):
    return Database(tmp_path / "db")


@pytest.fixture
def bot():
    return SimpleNamespace(
        send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)),
        edit_message_text=AsyncMock(),
        delete_message=AsyncMock(),
        edit_message_reply_markup=AsyncMock(),
        send_document=AsyncMock(return_value=SimpleNamespace(message_id=101)),
        edit_message_caption=AsyncMock(),
    )


def run(coro):
    return asyncio.run(coro)


def test_one_screen_survives_restart_and_rejects_repeated_and_legacy_clicks(db, bot):
    ui = TelegramUI(db)
    screen = Screen("One", [[Button("Next", "guide:next")]])
    run(ui.render(bot, 1, 1, screen))
    old = bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert ui.resolve(1, 1, 100, old) == "guide:next"
    ui = TelegramUI(Database(db.path))
    run(ui.render(bot, 1, 1, Screen("Two", [[Button("Back", "guide:back")]])))
    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.call_args.kwargs["message_id"] == 100
    new = bot.edit_message_text.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert ui.resolve(1, 1, 100, new) == "guide:back"
    assert ui.resolve(1, 1, 100, old) is None
    assert ui.resolve(1, 1, 99, new) is None
    assert ui.resolve(2, 2, 100, new) is None
    assert ui.resolve(1, 1, 100, "guide:next") is None
    assert len(new.encode()) <= 64


def test_deleted_screen_recovers_but_network_timeout_does_not_duplicate(db, bot):
    ui = TelegramUI(db)
    screen = Screen("Menu", [[Button("Shop", "enter:shop")]])
    run(ui.render(bot, 1, 1, screen))
    bot.edit_message_text.side_effect = TimedOut()
    with pytest.raises(TimedOut):
        run(ui.render(bot, 1, 1, screen))
    assert bot.send_message.await_count == 1
    bot.edit_message_text.side_effect = BadRequest("Message to edit not found")
    bot.send_message.return_value = SimpleNamespace(message_id=102)
    run(ui.render(bot, 1, 1, screen))
    assert bot.send_message.await_count == 2
    assert db.state(1, 1, "telegram_ui")["message_id"] == 102


def test_pdf_is_reused_and_text_navigation_remains_available(db, bot, tmp_path):
    pdf = tmp_path / "example.pdf"
    pdf.write_bytes(b"demo")
    bot.send_message.return_value = SimpleNamespace(message_id=102)
    ui = TelegramUI(db)
    screen = Screen("Guide", [[Button("Back", "guide:back")]], document=pdf)
    run(ui.render(bot, 1, 1, screen))
    bot.edit_message_caption.side_effect = BadRequest("Message is not modified")
    run(TelegramUI(db).render(bot, 1, 1, screen))
    assert bot.send_document.await_count == 1
    assert bot.send_message.await_count == 1
    assert bot.edit_message_text.await_count == 1


def test_deleted_pdf_can_be_downloaded_again_and_document_failure_keeps_navigation(
    db, bot, tmp_path
):
    pdf = tmp_path / "example.pdf"
    pdf.write_bytes(b"demo")
    bot.send_message.return_value = SimpleNamespace(message_id=102)
    ui = TelegramUI(db)
    screen = Screen("Guide", [[Button("Back", "guide:back")]], document=pdf)
    run(ui.render(bot, 1, 1, screen))
    bot.edit_message_caption.side_effect = BadRequest("Message to edit not found")
    bot.send_document.return_value = SimpleNamespace(message_id=103)
    bot.send_message.return_value = SimpleNamespace(message_id=104)
    run(ui.render(bot, 1, 1, screen))
    assert bot.send_document.await_count == 2
    bot.edit_message_caption.side_effect = TimedOut()
    run(ui.render(bot, 1, 1, screen))
    assert "PDF временно недоступен" in bot.edit_message_text.call_args.kwargs["text"]
    assert bot.send_message.await_count == 2


def test_unexpected_edit_error_does_not_create_extra_screen(db, bot):
    ui = TelegramUI(db)
    screen = Screen("Menu", [[Button("Back", "home")]])
    run(ui.render(bot, 1, 1, screen))
    bot.edit_message_text.side_effect = BadRequest("Reply markup is invalid")
    with pytest.raises(BadRequest):
        run(ui.render(bot, 1, 1, screen))
    assert bot.send_message.await_count == 1


def test_click_consumed_before_delivery_failure_and_long_actions_fit_telegram_limit(db, bot):
    ui = TelegramUI(db)
    action = "shop:adminorder:" + "a" * 32
    run(ui.render(bot, 1, 1, Screen("Order", [[Button("Open", action)]])))
    callback = bot.send_message.call_args.kwargs["reply_markup"].inline_keyboard[0][0].callback_data
    assert len(callback.encode()) <= 64
    assert ui.resolve(1, 1, 100, callback) == action
    ui.invalidate(1, 1)
    bot.edit_message_text.side_effect = TimedOut()
    with pytest.raises(TimedOut):
        run(ui.render(bot, 1, 1, Screen("Placed", [[Button("Menu", "home")]])))
    assert ui.resolve(1, 1, 100, callback) is None


def test_booking_back_reaches_every_step_and_invalidates_changed_specialist(db):
    router = Router(db, Settings())

    def act(value):
        return router.action(1, 1, value)

    act("enter:booking")
    act("booking:new")
    act("booking:service:haircut")
    act("booking:specialist:anna")
    day = router.features["booking"].service.days()[0]
    act(f"booking:day:{day}")
    slot = router.features["booking"].service.slots(1, "anna", day)[0]
    act(f"booking:slot:{slot}")
    assert "время" in act("back").text
    assert "дату" in act("back").text
    assert "специалиста" in act("back").text
    act("booking:specialist:alex")
    assert "starts_at" not in db.state(1, 1, "booking")
    assert router.features["booking"].service.list(1) == []
    act("back")
    assert "услугу" in act("back").text
    assert "Студия" in act("back").text


def test_lead_back_preserves_answers_and_can_replace_one(db):
    router = Router(db, Settings())
    router.action(1, 1, "enter:leads")
    router.action(1, 1, "leads:new")
    for value in ("Fix my laptop", "Alex", "@example_user"):
        router.text(1, 1, value)
    router.action(1, 1, "back")
    screen = router.action(1, 1, "back")
    assert "Alex" in screen.text
    assert db.state(1, 1, "leads")["contact"] == "@example_user"
    router.text(1, 1, "Alice")
    router.action(1, 1, "leads:keep")
    router.action(1, 1, "leads:confirm")
    assert router.features["leads"].service.list(1)[0]["name"] == "Alice"


def test_shop_checkout_back_keeps_cart_and_admin_detail_returns_to_admin(db):
    router = Router(db, Settings())

    def act(value):
        return router.action(1, 1, value)

    act("enter:shop")
    act("shop:add:notebook")
    act("shop:checkout")
    router.text(1, 1, "Alex")
    router.text(1, 1, "@example_user")
    act("back")
    act("back")
    assert db.state(1, 1, "shop")["contact"] == "@example_user"
    assert "Корзина" in act("back").text
    assert db.state(1, 1, "shop") == {}
    assert router.features["shop"].service.cart(1, 1)["count"] == 1
    service = router.features["shop"].service
    order = service.checkout(1, 1, "request-key", "Alex", "@example_user", "pickup", "")
    act("shop:admin")
    act(f"shop:adminorder:{order['id']}")
    screen = act("back")
    assert any(b.action.startswith("shop:adminorder:") for row in screen.rows for b in row)


def test_language_and_error_return_to_previous_screen_without_repeating_action(db):
    router = Router(db, Settings())
    router.action(1, 1, "lang:ru")
    router.action(1, 1, "enter:shop")
    cart = router.action(1, 1, "shop:add:notebook")
    router.action(1, 1, "language")
    assert router.action(1, 1, "back").text == cart.text
    router.action(1, 1, "shop:add:unknown")
    assert router.action(1, 1, "back").text == cart.text
    assert router.features["shop"].service.cart(1, 1)["count"] == 1


def test_language_switch_keeps_cart_view_and_repeated_language_command_can_go_back(db):
    router = Router(db, Settings())
    router.action(1, 1, "enter:shop")
    router.action(1, 1, "shop:add:notebook")
    router.action(1, 1, "language")
    router.action(1, 1, "language")
    assert "Корзина" in router.action(1, 1, "back").text
    router.action(1, 1, "language")
    assert "Cart" in router.action(1, 1, "lang:en").text
    assert router.features["shop"].service.cart(1, 1)["count"] == 1


def test_navigation_moves_below_notification_without_deleting_it(db, bot):
    ui = TelegramUI(db)
    screen = Screen("Menu", [[Button("Shop", "enter:shop")]])
    run(ui.render(bot, 1, 1, screen))
    ui.note_message(1, 1, 101)
    bot.send_message.return_value = SimpleNamespace(message_id=102)
    run(ui.render(bot, 1, 1, screen))
    bot.delete_message.assert_awaited_once_with(chat_id=1, message_id=100)
    assert ui.state(1, 1)["message_id"] == 102
    run(ui.render(bot, 1, 1, screen))
    assert bot.send_message.await_count == 2


def test_pdf_moves_screen_below_file_and_failed_deletion_disables_old_keyboard(db, bot, tmp_path):
    ui = TelegramUI(db)
    screen = Screen("Guide", [[Button("PDF", "guide:pdf")]])
    run(ui.render(bot, 1, 1, screen))
    pdf = tmp_path / "guide.pdf"
    pdf.write_bytes(b"demo")
    screen.document = pdf
    bot.send_message.return_value = SimpleNamespace(message_id=102)
    bot.delete_message.side_effect = BadRequest("Message can't be deleted")
    run(ui.render(bot, 1, 1, screen))
    bot.edit_message_reply_markup.assert_awaited_once_with(
        chat_id=1, message_id=100, reply_markup=None
    )
    assert ui.state(1, 1)["document_id"] == 101
    assert ui.state(1, 1)["message_id"] == 102


def test_transport_cleans_input_only_after_render_and_duplicate_click_is_harmless(db, bot):
    app = build_application(Settings(bot_token="123:fake-test-token", database_path=db.path))
    handle = app.handlers[0][0].callback
    user = User(1, "Alex", False)
    chat = Chat(1, "private")
    context = SimpleNamespace(bot=bot)
    bot.answer_callback_query = AsyncMock()
    run(handle(Update(1, message=Message(1, None, chat, from_user=user, text="/start")), context))
    bot.delete_message.assert_awaited_once_with(chat_id=1, message_id=1)

    def click(payload, update_id):
        query = CallbackQuery(
            str(update_id),
            user,
            "instance",
            message=Message(100, None, chat, from_user=User(2, "Bot", True)),
            data=payload,
        )
        query.set_bot(bot)
        run(handle(Update(update_id, callback_query=query), context))

    def button(action):
        state = TelegramUI(db).state(1, 1)
        return f"ui:{state['revision']}:{state['actions'].index(action)}"

    click(button("lang:ru"), 2)
    click(button("enter:shop"), 3)
    click(button("shop:catalog"), 4)
    click(button("shop:item:notebook"), 40)
    add = button("shop:add:notebook")
    click(add, 5)
    click(add, 6)
    assert app.bot_data["router"].features["shop"].service.cart(1, 1)["count"] == 1
    assert bot.send_message.await_count == 1
    assert "устарела" in bot.answer_callback_query.call_args.kwargs["text"]
    # A failed render keeps the user's text available to retry.
    bot.edit_message_text.side_effect = TimedOut()
    with pytest.raises(TimedOut):
        run(
            handle(Update(7, message=Message(7, None, chat, from_user=user, text="/menu")), context)
        )
    assert bot.delete_message.await_count == 1


@pytest.mark.parametrize("module", ["guide", "booking", "leads", "shop"])
def test_each_module_has_an_exit_and_default_module_back_does_not_leave_client_bot(db, module):
    router = Router(db, Settings(enabled_modules=(module,), default_module=module))
    router.action(1, 1, "lang:ru")
    screen = router.action(1, 1, f"enter:{module}")
    assert not any(b.action == "home" for row in screen.rows for b in row)
    router.action(1, 1, "back")
    assert db.state(1, 1, "navigation")["active"] == module
