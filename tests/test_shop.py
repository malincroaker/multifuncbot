from concurrent.futures import ThreadPoolExecutor

import pytest

from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.modules.shop.service import ShopService


@pytest.fixture
def shop(tmp_path):
    return ShopService(Database(tmp_path / "db"))


def checkout(shop, owner=1, key="checkout-0001"):
    return shop.checkout(1, owner, key, "Alex", "@example_user", "pickup", "")


def test_checkout_snapshots_prices_and_does_not_charge(shop):
    shop.set_quantity(1, 1, "notebook", 2)
    order = checkout(shop)
    assert order["total"] == 178000
    assert order["status"] == "awaiting_payment"
    shop.set_quantity(1, 1, "notebook", 10)
    assert shop.get_order(1, 1, order["id"])["total"] == 178000


def test_retrying_checkout_does_not_duplicate_or_clear_new_cart(shop):
    shop.set_quantity(1, 1, "notebook", 1)
    with ThreadPoolExecutor(2) as pool:
        orders = list(pool.map(lambda _: checkout(shop), range(2)))
    assert orders[0]["id"] == orders[1]["id"]
    shop.set_quantity(1, 1, "mug", 1)
    assert checkout(shop)["id"] == orders[0]["id"]
    assert shop.cart(1, 1)["count"] == 1


def test_order_ownership_and_payment_state_machine(shop):
    shop.set_quantity(1, 1, "notebook", 1)
    order = checkout(shop)
    with pytest.raises(DomainError):
        shop.simulate(1, 2, order["id"], "success")
    assert shop.simulate(1, 1, order["id"], "failure")["status"] == "payment_failed"
    assert shop.simulate(1, 1, order["id"], "success")["status"] == "paid"
    assert shop.simulate(1, 1, order["id"], "success")["status"] == "paid"
    with pytest.raises(DomainError):
        shop.simulate(1, 1, order["id"], "cancel")


@pytest.mark.parametrize("quantity", [-1, 21, True, 1.5])
def test_quantity_validation(shop, quantity):
    with pytest.raises(DomainError):
        shop.set_quantity(1, 1, "notebook", quantity)


def test_empty_cart_and_delivery_address_are_validated(shop):
    with pytest.raises(DomainError):
        checkout(shop)
    shop.set_quantity(1, 1, "mug", 1)
    with pytest.raises(DomainError):
        shop.checkout(1, 1, "checkout-0001", "Alex", "@example_user", "delivery", "")
