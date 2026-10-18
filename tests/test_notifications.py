from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.notifications import pending, record_delivery
from multifuncbot.modules.leads.service import LeadService
from multifuncbot.modules.shop.service import ShopService


def test_business_notification_is_persisted_but_demo_does_not_spam_admins(tmp_path):
    db = Database(tmp_path / "db")
    draft = {"request": "Example request", "name": "Alex", "contact": "@example_user"}
    LeadService(db, Settings(admin_ids=(99,))).create(1, 1, draft)
    assert pending(db) == []
    service = LeadService(db, Settings(app_mode="business", admin_ids=(99,)))
    service.create(0, 1, draft)
    notification = pending(Database(db.path))[0]
    assert notification["recipient_id"] == 99
    record_delivery(db, notification["id"], success=True)
    assert pending(db) == []


def test_idempotent_checkout_creates_one_notification(tmp_path):
    db = Database(tmp_path / "db")
    service = ShopService(db, Settings(app_mode="business", admin_ids=(99,)))
    service.set_quantity(0, 1, "mug", 1)
    for _ in range(2):
        service.checkout(0, 1, "example-order", "Alex", "@example_user", "pickup", "")
    assert len(pending(db)) == 1
