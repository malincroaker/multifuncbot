import time

import pytest
from fastapi.testclient import TestClient
from test_web_auth import TOKEN, signed_data

from multifuncbot.core.config import Settings
from multifuncbot.web import create_app

HEADERS = {"X-Multifuncbot": "1"}


@pytest.fixture
def app(tmp_path):
    return create_app(Settings(database_path=str(tmp_path / "db"), bot_token=TOKEN))


def test_complete_browser_checkout_is_isolated_and_server_priced(app):
    with TestClient(app, headers=HEADERS) as customer, TestClient(app, headers=HEADERS) as other:
        assert customer.post("/api/session").json()["mode"] == "browser"
        other.post("/api/session")
        assert customer.get("/").status_code == 200
        assert customer.get("/images/notebook.svg").status_code == 200
        customer.put("/api/cart/items/notebook", json={"quantity": 2})
        assert other.get("/api/cart").json()["count"] == 0
        body = {
            "request_key": "request-0001",
            "customer_name": "Alex",
            "contact": "@example_user",
            "fulfillment": "delivery",
            "address": "Demo city, Example street 1",
        }
        order = customer.post("/api/orders", json=body).json()
        assert order["total"] == 208000
        assert len(customer.post("/api/orders", json=body).json()["lines"]) == 1
        assert len(customer.get("/api/orders").json()["orders"]) == 1
        assert (
            other.post(
                f"/api/orders/{order['id']}/payment", json={"outcome": "success"}
            ).status_code
            == 409
        )
        response = customer.post(f"/api/orders/{order['id']}/payment", json={"outcome": "success"})
        assert response.json()["status"] == "paid"
        assert response.json()["demo"] is True


def test_forged_identity_price_and_cross_origin_requests_are_rejected(app):
    with TestClient(app, headers=HEADERS) as client:
        assert client.get("/api/cart?user_id=42").status_code == 401
        client.post("/api/session")
        assert (
            client.get("/api/cart", headers={"X-Telegram-Init-Data": "hash=bad"}).status_code == 401
        )
        assert (
            client.put("/api/cart/items/notebook", json={"quantity": 1, "price": 1}).status_code
            == 422
        )
        assert client.put("/api/cart/items/notebook", json={"quantity": True}).status_code == 422
        assert (
            client.post("/api/session", headers={"Origin": "https://evil.example"}).status_code
            == 403
        )
    with TestClient(app) as client:
        assert client.post("/api/session").status_code == 403


def test_verified_telegram_identity_shares_the_bot_cart(app):
    from multifuncbot.core.database import Database
    from multifuncbot.modules.shop.service import ShopService

    with TestClient(
        app, headers={**HEADERS, "X-Telegram-Init-Data": signed_data(now=int(time.time()))}
    ) as client:
        assert client.post("/api/session").json()["mode"] == "telegram"
        client.put("/api/cart/items/mug", json={"quantity": 1})
        # Reopen through the shared database just as the Telegram module does.
        db_path = client.app.state.database_path
        assert ShopService(Database(db_path)).cart(42, 42)["count"] == 1


def test_business_mode_never_creates_an_anonymous_identity(tmp_path):
    app = create_app(Settings(database_path=str(tmp_path / "db"), app_mode="business"))
    with TestClient(app, headers=HEADERS) as client:
        assert client.post("/api/session").status_code == 401


def test_https_tunnel_preserves_origin_checks_and_secure_sessions(tmp_path):
    public_url = "https://shop.example"
    app = create_app(
        Settings(database_path=str(tmp_path / "db"), mini_app_url=public_url)
    )

    async def tunnel(scope, receive, send):
        if scope["type"] == "http":
            scope = {**scope, "scheme": "http"}
        await app(scope, receive, send)

    with TestClient(tunnel, base_url=public_url, headers=HEADERS) as client:
        response = client.post("/api/session", headers={"Origin": public_url})
        assert response.status_code == 200
        assert "Secure" in response.headers["set-cookie"]
        assert client.put(
            "/api/cart/items/mug", json={"quantity": 1}, headers={"Origin": public_url}
        ).status_code == 200
        assert client.get("/api/cart").json()["count"] == 1
        assert client.post(
            "/api/session", headers={"Origin": "https://evil.example"}
        ).status_code == 403
        assert client.post(
            "/api/session", headers={"Origin": "http://shop.example"}
        ).status_code == 403

    with TestClient(app, headers=HEADERS) as local:
        assert local.post(
            "/api/session", headers={"Origin": "http://testserver"}
        ).status_code == 200
        assert local.post(
            "/api/session",
            headers={"Origin": public_url, "X-Forwarded-Host": "shop.example"},
        ).status_code == 403
