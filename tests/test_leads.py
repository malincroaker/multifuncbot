import pytest

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.core.router import Router
from multifuncbot.modules.leads.service import validate_field


def test_lead_review_is_required_and_duplicate_confirmation_is_safe(tmp_path):
    router = Router(Database(tmp_path / "db"), Settings(enabled_modules=("leads",)))
    router.action(1, 1, "enter:leads")
    router.action(1, 1, "leads:new")
    router.action(1, 1, "leads:confirm")
    service = router.features["leads"].service
    assert service.list(1) == []
    for text in ("Fix a broken laptop", "Alex", "@example_user"):
        router.text(1, 1, text)
    assert service.list(1) == []
    router.action(1, 1, "leads:confirm")
    router.action(1, 1, "leads:confirm")
    assert len(service.list(1)) == 1
    assert service.list(2) == []


def test_business_customer_cannot_advance_leads(tmp_path):
    router = Router(
        Database(tmp_path / "db"),
        Settings(enabled_modules=("leads",), app_mode="business", admin_ids=(99,)),
    )
    router.action(1, 1, "enter:leads")
    screen = router.action(1, 1, "leads:advance:1")
    assert "Нет доступа" in screen.text


@pytest.mark.parametrize("value", ["abc", "123", "<script>", "@x", "x\ny@example.com"])
def test_invalid_contacts_are_rejected(value):
    with pytest.raises(DomainError):
        validate_field("contact", value)
