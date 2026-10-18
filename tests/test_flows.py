import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from telegram import Chat, Message, Update, User

from multifuncbot.app import build_application, markup
from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.router import Router


def assert_screen(screen):
    assert 0 < len(screen.text) <= 4096
    for row in screen.rows:
        for button in row:
            if button.action:
                assert len(button.action.encode()) <= 64
    assert markup(screen).inline_keyboard


@pytest.fixture
def router(tmp_path):
    return Router(Database(tmp_path / "db"), Settings())


def test_complete_booking_and_admin_flow(router):
    def act(value):
        return router.action(1, 1, value)

    for action in (
        "lang:ru",
        "enter:booking",
        "booking:new",
        "booking:service:haircut",
        "booking:specialist:anna",
    ):
        assert_screen(act(action))
    service = router.features["booking"].service
    day = service.days()[0]
    assert_screen(act(f"booking:day:{day}"))
    slot = service.slots(1, "anna", day)[0]
    assert_screen(act(f"booking:slot:{slot}"))
    assert_screen(act("booking:confirm"))
    act("booking:confirm")
    assert len(service.list(1)) == 1
    record = service.list(1)[0]
    assert_screen(act(f"booking:approve:{record['id']}"))
    assert service.list(1)[0]["status"] == "confirmed"
    act(f"booking:cancel:{record['id']}")
    assert service.list(1)[0]["status"] == "cancelled"


def test_switching_scenarios_discards_drafts_but_keeps_completed_data(router):
    router.action(1, 1, "enter:leads")
    router.action(1, 1, "leads:new")
    router.text(1, 1, "Example task")
    router.action(1, 1, "enter:booking")
    assert router.db.state(1, 1, "leads") == {}


def test_admin_can_inspect_another_customers_order_without_payment_controls(tmp_path):
    router = Router(Database(tmp_path / "db"), Settings(app_mode="business", admin_ids=(99,)))
    shop = router.features["shop"].service
    shop.set_quantity(0, 1, "notebook", 1)
    order = shop.checkout(0, 1, "example-order", "Alex", "@example_user", "pickup", "")
    router.action(99, 99, "enter:shop")
    screen = router.action(99, 99, f"shop:adminorder:{order['id']}")
    assert "Alex" in screen.text
    assert not any(button.action.startswith("shop:pay:") for row in screen.rows for button in row)
    router.action(2, 2, "enter:shop")
    assert "Нет доступа" in router.action(2, 2, f"shop:adminorder:{order['id']}").text


def test_chat_shop_checkout_and_payment(router):
    for action in ("enter:shop", "shop:catalog", "shop:add:notebook", "shop:checkout"):
        assert_screen(router.action(1, 1, action))
    router.text(1, 1, "Alex")
    router.text(1, 1, "@example_user")
    assert_screen(router.action(1, 1, "shop:place"))
    order = router.features["shop"].service.list_orders(1, 1)[0]
    assert "успешна" in router.action(1, 1, f"shop:pay:{order['id']}:success").text


def test_telegram_transport_renders_start_without_network(tmp_path):
    app = build_application(
        Settings(bot_token="123:fake-test-token", database_path=str(tmp_path / "db"))
    )
    update = Update(
        1,
        message=Message(
            1, None, Chat(1, "private"), from_user=User(1, "Alex", False), text="/start"
        ),
    )
    bot = SimpleNamespace(send_message=AsyncMock(), send_document=AsyncMock())
    asyncio.run(app.handlers[0][0].callback(update, SimpleNamespace(bot=bot)))
    assert "Choose your language" in bot.send_message.call_args.args[1]
