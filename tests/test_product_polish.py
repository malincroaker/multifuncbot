import asyncio
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from multifuncbot.app import build_application
from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import pending
from multifuncbot.core.router import Router
from multifuncbot.modules.booking.service import BookingService
from multifuncbot.modules.leads.service import LeadService


@pytest.fixture
def router(tmp_path):
    return Router(Database(tmp_path / "db"), Settings())


def actions(screen):
    return [button.action for row in screen.rows for button in row]


@pytest.mark.parametrize(
    "module,child",
    [
        ("guide", "guide:open"),
        ("booking", "booking:new"),
        ("leads", "leads:new"),
        ("shop", "shop:cart"),
    ],
)
def test_showcase_exit_only_on_scenario_introduction(router, module, child):
    assert "home" in actions(router.action(1, 1, f"enter:{module}"))
    screen = router.action(1, 1, child)
    assert "home" not in actions(screen)
    assert f"{module}:menu" in actions(screen)
    assert "home" in actions(router.action(1, 1, "scenario"))


def test_stepwise_one_clear_guide_entry_keeps_progress(router):
    screen = router.action(1, 1, "enter:guide")
    assert "guide:new" not in actions(screen)
    router.action(1, 1, "guide:open")
    router.action(1, 1, "guide:next")
    router.action(1, 1, "guide:menu")
    assert "Шаг 2" in router.action(1, 1, "guide:open").text


def test_studio_human_dates_and_timezone_and_cart_symmetry(router):
    intro = router.action(1, 1, "enter:booking")
    assert "MSK" in intro.text and "Europe/Moscow" not in intro.text
    router.action(1, 1, "booking:new")
    router.action(1, 1, "booking:service:haircut")
    screen = router.action(1, 1, "booking:specialist:anna")
    dates = [b for row in screen.rows for b in row if b.action.startswith("booking:day:")]
    assert dates and not dates[0].text.startswith("2026-")
    router.action(1, 1, "enter:shop")
    screen = router.action(1, 1, "shop:add:mug")
    assert "1 190 ₽" in screen.text
    assert [b.text for b in screen.rows[0]][::2] == ["−", "+"]
    assert len([b for row in screen.rows for b in row if b.action == "shop:menu"]) == 1
    assert "не опубликован" in router.action(1, 1, "shop:miniapp").text


def test_lead_statuses_are_reversible_with_required_rejection_reason_and_notification(router):
    service = router.features["leads"].service
    lead = service.create(
        1, 1, {"request": "Fix my laptop", "name": "Alex", "contact": "@example_user"}
    )
    for status in ("in_progress", "paused", "in_progress", "done", "in_progress"):
        service.change_status(1, lead, status)
    with pytest.raises(DomainError):
        service.change_status(1, lead, "rejected")
    service.change_status(1, lead, "rejected", "Сейчас нет свободного мастера")
    assert "нет свободного" in service.get(1, lead)["comment"]
    assert "сообщение клиенту" in pending(router.db)[-1]["message"].lower()
    assert "Сейчас нет свободного" in pending(router.db)[-1]["message"]
    service.change_status(1, lead, "new")
    assert service.get(1, lead)["status"] == "new"
    assert len(service.history(1, lead)) == 7
    with pytest.raises(DomainError):
        service.get(2, lead)


def test_existing_leads_are_retained_when_history_is_initialized(tmp_path):
    db = Database(tmp_path / "db")
    db.initialize(
        "CREATE TABLE leads (id INTEGER PRIMARY KEY, tenant INTEGER, owner_id INTEGER, "
        "request TEXT, name TEXT, contact TEXT, status TEXT DEFAULT 'new', created_at TEXT);"
    )
    with db.connect(write=True) as connection:
        connection.execute(
            "INSERT INTO leads VALUES(1,1,1,'Old task','Alex','@example_user','new','2026')"
        )
    service = LeadService(db, Settings())
    service.change_status(1, 1, "in_progress")
    assert service.get(1, 1)["request"] == "Old task"


def test_feedback_after_two_hours_only_confirmed_and_owned_is_persistent(tmp_path):
    now = datetime(2026, 10, 19, 6, tzinfo=UTC)
    service = BookingService(Database(tmp_path / "db"), Settings(), clock=lambda: now)
    slot = service.slots(1, "anna", service.days()[0])[0]
    booking = service.book(1, 1, 1, "haircut", "anna", slot)
    service.change_status(1, 1, booking, "confirmed", admin=True)
    start = datetime.fromisoformat(slot)
    assert service.due_feedback(start + timedelta(minutes=119)) == []
    assert len(service.due_feedback(start + timedelta(hours=2))) == 1
    service.clock = lambda: start + timedelta(hours=2)
    with pytest.raises(DomainError):
        service.save_feedback(1, 2, booking, 5, "Great")
    service.save_feedback(1, 1, booking, 5, "Спасибо мастеру")
    service.save_feedback(1, 1, booking, 5, "Спасибо мастеру")
    assert service.due_feedback(service.clock()) == []
    restarted = BookingService(service.db, service.settings, clock=service.clock)
    assert restarted.feedback(1, 1, booking)["rating"] == 5


def test_lead_admin_detail_denied_to_customer_and_comment_flow_is_reviewed(router):
    service = router.features["leads"].service
    lead = service.create(
        1, 1, {"request": "Fix my laptop", "name": "Alex", "contact": "@example_user"}
    )
    router.action(1, 1, "enter:leads")
    router.action(1, 1, f"leads:adminitem:{lead}")
    router.action(1, 1, f"leads:status:{lead}:rejected")
    router.text(1, 1, "Нет подходящего специалиста")
    assert service.get(1, lead)["status"] == "new"
    router.action(1, 1, "leads:status-confirm")
    assert service.get(1, lead)["status"] == "rejected"
    business = Router(router.db, Settings(app_mode="business", admin_ids=(99,)))
    business.action(2, 2, "enter:leads")
    assert "Нет доступа" in business.action(2, 2, f"leads:adminitem:{lead}").text


def test_status_confirmation_cannot_overwrite_newer_decision(router):
    service = router.features["leads"].service
    lead = service.create(
        1, 1, {"request": "Fix my laptop", "name": "Alex", "contact": "@example_user"}
    )
    router.action(1, 1, "enter:leads")
    router.action(1, 1, f"leads:status:{lead}:rejected")
    router.text(1, 1, "No available specialist")
    service.change_status(1, lead, "in_progress")
    screen = router.action(1, 1, "leads:status-confirm")
    assert "уже изменился" in screen.text
    assert service.get(1, lead)["status"] == "in_progress"
    assert len(pending(router.db)) == 1


def test_customer_can_read_own_comment_but_not_another_customers_request(tmp_path):
    db = Database(tmp_path / "db")
    router = Router(db, Settings(app_mode="business", admin_ids=(99,)))
    service = router.features["leads"].service
    lead = service.create(
        0, 1, {"request": "Fix my laptop", "name": "Alex", "contact": "@example_user"}
    )
    service.change_status(0, lead, "rejected", "No available specialist")
    router.action(1, 1, "enter:leads")
    assert "No available specialist" in router.action(1, 1, f"leads:item:{lead}").text
    router.action(2, 2, "enter:leads")
    assert "не найдена" in router.action(2, 2, f"leads:item:{lead}").text
    assert "Нет доступа" in router.action(2, 2, f"leads:status:{lead}:new").text


def test_sample_review_does_not_create_fake_visits_and_business_mode_hides_it(router):
    router.action(1, 1, "enter:booking")
    router.action(1, 1, "booking:demo-review")
    router.action(1, 1, "booking:rating:5")
    router.text(1, 1, "Спасибо!")
    assert "пример" in router.action(1, 1, "booking:feedback-submit").text
    assert router.features["booking"].service.list(1) == []
    business = Router(router.db, Settings(app_mode="business"))
    screen = business.action(2, 2, "enter:booking")
    assert "booking:followup-demo" not in actions(screen)
    assert "только в демо" in business.action(2, 2, "booking:demo-review").text


def test_feedback_notice_is_navigation_only_and_rechecks_owner_and_time(tmp_path):
    router = Router(Database(tmp_path / "db"), Settings())
    service = router.features["booking"].service
    slot = service.slots(1, "anna", service.days()[0])[0]
    booking = service.book(1, 1, 1, "haircut", "anna", slot)
    service.change_status(1, 1, booking, "confirmed", admin=True)
    assert "после" in router.notice(1, 1, f"notice:booking:review:{booking}").text
    service.clock = lambda: datetime.fromisoformat(slot) + timedelta(hours=2)
    assert "отзыв" in router.notice(1, 1, f"notice:booking:review:{booking}").text.lower()
    router.action(1, 1, "booking:rating:4")
    router.text(1, 1, "Helpful specialist")
    router.notice(1, 1, f"notice:booking:review:{booking}")
    assert router.db.state(1, 1, "booking")["rating"] == 4
    assert router.db.state(1, 1, "booking")["comment"] == "Helpful specialist"
    assert "после" in router.notice(2, 2, f"notice:booking:review:{booking}").text
    router.notice(1, 1, f"notice:booking:cancel:{booking}")
    assert service.list(1)[0]["status"] == "confirmed"
    router.action(1, 1, "booking:review:" + str(booking))
    router.action(1, 1, "booking:rating:4")
    router.action(1, 1, "booking:feedback-submit")
    assert service.feedback(1, 1, booking)["rating"] == 4


def test_followup_jobs_send_once_and_do_not_request_reviews_for_rejected_visits(tmp_path):
    app = build_application(Settings(bot_token="123:fake", database_path=str(tmp_path / "db")))
    service = app.bot_data["router"].features["booking"].service
    day = service.days()[0]
    slot = service.slots(1, "anna", day)[0]
    approved = service.book(1, 1, 1, "haircut", "anna", slot)
    rejected = service.book(2, 2, 2, "haircut", "anna", slot)
    service.change_status(1, 1, approved, "confirmed", admin=True)
    service.change_status(2, 2, rejected, "rejected", admin=True)
    bot = SimpleNamespace(send_message=AsyncMock(return_value=SimpleNamespace(message_id=100)))
    job = next(job for job in app.job_queue.jobs() if job.name == "reminders")
    service.clock = lambda: datetime.fromisoformat(slot) - timedelta(minutes=30)
    asyncio.run(job.callback(SimpleNamespace(bot=bot)))
    assert "🔔" in bot.send_message.call_args.args[1]
    service.clock = lambda: datetime.fromisoformat(slot) + timedelta(hours=2)
    asyncio.run(job.callback(SimpleNamespace(bot=bot)))
    assert "notice:booking:review:" in str(bot.send_message.call_args.kwargs["reply_markup"])
    asyncio.run(job.callback(SimpleNamespace(bot=bot)))
    assert bot.send_message.await_count == 2
    assert service.due_feedback() == []


def test_old_booking_schema_is_extended_without_losing_records(tmp_path):
    db = Database(tmp_path / "db")
    db.initialize(
        "CREATE TABLE bookings(id INTEGER PRIMARY KEY, tenant INTEGER, owner_id INTEGER, "
        "chat_id INTEGER, service TEXT, specialist TEXT, starts_at TEXT, status TEXT, "
        "reminder_sent INTEGER DEFAULT 0);"
    )
    with db.connect(write=True) as connection:
        connection.execute(
            "INSERT INTO bookings VALUES "
            "(1,1,1,1,'haircut','anna','2026-10-19T07:00:00+00:00','confirmed',0)"
        )
    service = BookingService(db, Settings(), clock=lambda: datetime(2026, 10, 19, 10, tzinfo=UTC))
    assert service.list(1)[0]["service"] == "haircut"
    assert len(service.due_feedback()) == 1
    service.mark_feedback_requested(1)
    assert BookingService(db, Settings(), clock=service.clock).due_feedback() == []


def test_admin_can_cancel_customer_appointment_and_contact_and_miniapp_use_config(tmp_path):
    settings = Settings(
        app_mode="business",
        admin_ids=(99,),
        studio_contact_url="https://t.me/example_studio",
        mini_app_url="https://shop.example/",
    )
    router = Router(Database(tmp_path / "db"), settings)
    service = router.features["booking"].service
    slot = service.slots(0, "anna", service.days()[0])[0]
    booking = service.book(0, 1, 1, "haircut", "anna", slot)
    router.action(99, 99, "enter:booking")
    router.action(99, 99, f"booking:admincancel:{booking}")
    assert service.list(0)[0]["status"] == "cancelled"
    assert "Отменена студией" in pending(router.db)[-1]["message"]
    assert any(
        b.url == settings.studio_contact_url
        for row in router.action(99, 99, "booking:contact").rows
        for b in row
    )
    screen = router.action(1, 1, "enter:shop")
    assert any(b.web_app and b.url == settings.mini_app_url for row in screen.rows for b in row)


@pytest.mark.parametrize(
    "settings",
    [
        {"studio_contact_url": "https://example.com"},
        {"review_delay_hours": 0},
        {"review_delay_hours": 169},
    ],
)
def test_invalid_followup_configuration_is_rejected(settings):
    with pytest.raises(ValueError):
        Settings(**settings)
