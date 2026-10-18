from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta

import pytest

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.modules.booking.service import BookingService


@pytest.fixture
def service(tmp_path):
    return BookingService(
        Database(tmp_path / "db"), Settings(), clock=lambda: datetime(2026, 10, 19, 6, tzinfo=UTC)
    )


def test_racing_customers_cannot_take_the_same_slot(service):
    slot = service.slots(0, "anna", service.days()[0])[0]

    def book(owner):
        try:
            return service.book(0, owner, owner, "haircut", "anna", slot)
        except DomainError:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(book, (1, 2)))
    assert sum(result is not None for result in results) == 1
    assert len(service.list(0)) == 1


def test_demo_tenants_and_specialists_have_separate_slots(service):
    slot = service.slots(1, "anna", service.days()[0])[0]
    service.book(1, 1, 1, "haircut", "anna", slot)
    service.book(2, 2, 2, "haircut", "anna", slot)
    service.book(1, 1, 1, "haircut", "alex", slot)
    assert len(service.list(1)) == 2
    assert len(service.list(2)) == 1


def test_cancel_checks_owner_and_releases_slot(service):
    slot = service.slots(0, "anna", service.days()[0])[0]
    booking = service.book(0, 1, 1, "haircut", "anna", slot)
    with pytest.raises(DomainError):
        service.change_status(0, 2, booking, "cancelled")
    service.change_status(0, 1, booking, "cancelled")
    assert slot in service.slots(0, "anna", service.days()[0])


def test_only_confirmed_future_bookings_receive_persisted_reminders(service):
    slot = service.slots(1, "anna", service.days()[0])[0]
    booking = service.book(1, 1, 1, "haircut", "anna", slot)
    now = datetime.fromisoformat(slot) - timedelta(minutes=30)
    assert service.due_reminders(now) == []
    service.change_status(1, 1, booking, "confirmed", admin=True)
    assert len(service.due_reminders(now)) == 1
    service.mark_reminded(booking)
    restarted = BookingService(service.db, service.settings)
    assert restarted.due_reminders(now) == []
