"""The optional shop HTTP API. Identity and prices are never taken from client JSON."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from multifuncbot.core.web_auth import BrowserSessions, validate_init_data
from multifuncbot.modules.shop.catalog import PRODUCTS
from multifuncbot.modules.shop.service import ShopService


class Quantity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(ge=0, le=20, strict=True)


class Checkout(BaseModel):
    model_config = ConfigDict(extra="forbid")
    request_key: str = Field(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")
    customer_name: str = Field(min_length=2, max_length=80)
    contact: str = Field(min_length=3, max_length=120)
    fulfillment: Literal["pickup", "delivery"]
    address: str = Field(default="", max_length=300)


class Payment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    outcome: Literal["success", "failure", "cancel"]


def create_router(db, settings):
    router = APIRouter(prefix="/api")
    service = ShopService(db, settings)
    sessions = BrowserSessions(db)

    def principal(request: Request):
        raw = request.headers.get("X-Telegram-Init-Data")
        if raw:
            try:
                return validate_init_data(raw, settings.bot_token)
            except ValueError as error:
                raise HTTPException(
                    401, "Telegram session expired or invalid. Reopen the Mini App."
                ) from error
        if settings.allow_browser_demo and settings.app_mode == "showcase":
            user_id = sessions.resolve(request.cookies.get("multifuncbot_demo"))
            if user_id is not None:
                return user_id
        raise HTTPException(401, "Open the Mini App in Telegram or start a browser demo session.")

    def tenant(user_id):
        return user_id if settings.app_mode == "showcase" else 0

    @router.get("/catalog")
    def catalog():
        return {
            "products": list(PRODUCTS.values()),
            "currency": "RUB",
            "demo": True,
            "delivery_fee": 30000,
            "free_delivery_from": 300000,
        }

    @router.post("/session")
    def session(request: Request, response: Response):
        if request.headers.get("X-Telegram-Init-Data"):
            user_id = principal(request)
            mode = "telegram"
        else:
            if not settings.allow_browser_demo or settings.app_mode != "showcase":
                raise HTTPException(401, "Browser preview is disabled. Open this app in Telegram.")
            user_id = sessions.resolve(request.cookies.get("multifuncbot_demo"))
            if user_id is None:
                token, user_id = sessions.create()
                response.set_cookie(
                    "multifuncbot_demo",
                    token,
                    httponly=True,
                    secure=request.url.scheme == "https",
                    samesite="strict",
                    max_age=86400,
                )
            mode = "browser"
        return {
            "mode": mode,
            "demo": True,
            "language": db.language(user_id) or settings.default_language,
        }

    @router.get("/cart")
    def cart(user_id: int = Depends(principal)):
        return service.cart(tenant(user_id), user_id)

    @router.put("/cart/items/{product_id}")
    def quantity(product_id: str, body: Quantity, user_id: int = Depends(principal)):
        return service.set_quantity(tenant(user_id), user_id, product_id, body.quantity)

    @router.post("/orders")
    def checkout(body: Checkout, user_id: int = Depends(principal)):
        return service.checkout(tenant(user_id), user_id, **body.model_dump())

    @router.get("/orders")
    def orders(user_id: int = Depends(principal)):
        return {"orders": service.list_orders(tenant(user_id), user_id)}

    @router.post("/orders/{order_id}/payment")
    def payment(order_id: str, body: Payment, user_id: int = Depends(principal)):
        return service.simulate(tenant(user_id), user_id, order_id, body.outcome)

    return router
