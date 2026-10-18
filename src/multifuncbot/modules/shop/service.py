"""Transactional carts and immutable order snapshots shared by chat and Mini App."""

import json
import re
from uuid import uuid4

from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import enqueue
from multifuncbot.integrations.payments.demo import DemoPayments
from multifuncbot.modules.shop.catalog import PRODUCTS


def customer_field(field, value):
    value = value.strip()
    minimum, maximum = (2, 80) if field == "customer_name" else (3, 120)
    if not minimum <= len(value) <= maximum or any(ord(char) < 32 for char in value):
        raise DomainError(
            "Проверьте имя и контакт: неверная длина или перенос строки.",
            "Check name and contact: invalid length or line break.",
        )
    if field == "contact" and not (
        re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value)
        or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)
        or (re.fullmatch(r"\+?[0-9 ()-]+", value) and 10 <= len(re.sub(r"\D", "", value)) <= 15)
    ):
        raise DomainError(
            "Укажите телефон, email или @username.", "Enter a phone number, email or @username."
        )
    return value


class ShopService:
    def __init__(self, db, settings=None):
        self.db = db
        self.settings = settings
        self.payments = DemoPayments()
        db.initialize("""
            CREATE TABLE IF NOT EXISTS carts (
                tenant INTEGER NOT NULL, owner_id INTEGER NOT NULL,
                product_id TEXT NOT NULL,
                quantity INTEGER NOT NULL CHECK(quantity BETWEEN 1 AND 20),
                PRIMARY KEY (tenant,owner_id,product_id)
            );
            CREATE TABLE IF NOT EXISTS orders (
                id TEXT PRIMARY KEY, tenant INTEGER NOT NULL, owner_id INTEGER NOT NULL,
                request_key TEXT NOT NULL, customer_name TEXT NOT NULL, contact TEXT NOT NULL,
                fulfillment TEXT NOT NULL, address TEXT NOT NULL, lines TEXT NOT NULL,
                subtotal INTEGER NOT NULL, shipping INTEGER NOT NULL, total INTEGER NOT NULL,
                status TEXT NOT NULL DEFAULT 'awaiting_payment',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(tenant,owner_id,request_key)
            );
        """)

    @staticmethod
    def _cart(connection, tenant, owner_id):
        lines = []
        for row in connection.execute(
            "SELECT product_id,quantity FROM carts WHERE tenant=? AND owner_id=? "
            "ORDER BY product_id",
            (tenant, owner_id),
        ):
            product = PRODUCTS[row["product_id"]]
            lines.append(
                {
                    **product,
                    "quantity": row["quantity"],
                    "line_total": product["price"] * row["quantity"],
                }
            )
        return {
            "lines": lines,
            "count": sum(line["quantity"] for line in lines),
            "subtotal": sum(line["line_total"] for line in lines),
        }

    def cart(self, tenant, owner_id):
        with self.db.connect() as connection:
            return self._cart(connection, tenant, owner_id)

    def set_quantity(self, tenant, owner_id, product_id, quantity):
        if product_id not in PRODUCTS or type(quantity) is not int or not 0 <= quantity <= 20:
            raise DomainError(
                "Выберите товар и количество от 0 до 20.",
                "Choose a product and a quantity from 0 to 20.",
            )
        with self.db.connect(write=True) as connection:
            if quantity == 0:
                connection.execute(
                    "DELETE FROM carts WHERE tenant=? AND owner_id=? AND product_id=?",
                    (tenant, owner_id, product_id),
                )
            else:
                connection.execute(
                    "INSERT INTO carts VALUES (?,?,?,?) ON CONFLICT(tenant,owner_id,product_id) "
                    "DO UPDATE SET quantity=excluded.quantity",
                    (tenant, owner_id, product_id, quantity),
                )
            return self._cart(connection, tenant, owner_id)

    @staticmethod
    def _order(row):
        result = dict(row)
        result["lines"] = json.loads(result["lines"])
        result["demo"] = True
        return result

    def checkout(self, tenant, owner_id, request_key, customer_name, contact, fulfillment, address):
        if not re.fullmatch(r"[A-Za-z0-9_-]{8,64}", request_key):
            raise DomainError("Неверный ключ заказа.", "Invalid checkout key.")
        customer_name = customer_field("customer_name", customer_name)
        contact = customer_field("contact", contact)
        if fulfillment not in ("pickup", "delivery"):
            raise DomainError("Выберите способ получения.", "Choose a fulfillment method.")
        address = address.strip() if fulfillment == "delivery" else ""
        if fulfillment == "delivery" and (
            not 8 <= len(address) <= 300 or any(ord(char) < 32 for char in address)
        ):
            raise DomainError(
                "Укажите адрес доставки (8–300 символов).",
                "Enter a delivery address (8–300 characters).",
            )
        with self.db.connect(write=True) as connection:
            existing = connection.execute(
                "SELECT * FROM orders WHERE tenant=? AND owner_id=? AND request_key=?",
                (tenant, owner_id, request_key),
            ).fetchone()
            if existing:
                return self._order(existing)
            cart = self._cart(connection, tenant, owner_id)
            if not cart["lines"]:
                raise DomainError("Корзина пуста.", "Your cart is empty.")
            shipping = 30000 if fulfillment == "delivery" and cart["subtotal"] < 300000 else 0
            order_id = uuid4().hex
            connection.execute(
                "INSERT INTO orders(id,tenant,owner_id,request_key,customer_name,contact,"
                "fulfillment,address,lines,subtotal,shipping,total) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    order_id,
                    tenant,
                    owner_id,
                    request_key,
                    customer_name,
                    contact,
                    fulfillment,
                    address,
                    json.dumps(cart["lines"], ensure_ascii=False),
                    cart["subtotal"],
                    shipping,
                    cart["subtotal"] + shipping,
                ),
            )
            connection.execute(
                "DELETE FROM carts WHERE tenant=? AND owner_id=?", (tenant, owner_id)
            )
            if self.settings and self.settings.app_mode == "business":
                for recipient in self.settings.admin_ids:
                    enqueue(
                        connection,
                        recipient,
                        f"shop:new:{order_id}",
                        f"Новый демо-заказ #{order_id[:8]}. "
                        "/menu → Магазин → Кабинет администратора.",
                        f"New demo order #{order_id[:8]}. /menu → Shop → Admin view.",
                        self.settings.default_language,
                    )
            return self._order(
                connection.execute("SELECT * FROM orders WHERE id=?", (order_id,)).fetchone()
            )

    def get_order(self, tenant, owner_id, order_id):
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE tenant=? AND owner_id=? AND id=?",
                (tenant, owner_id, order_id),
            ).fetchone()
            if not row:
                raise DomainError("Заказ не найден.", "Order not found.")
            return self._order(row)

    def list_orders(self, tenant, owner_id=None):
        with self.db.connect() as connection:
            query = "SELECT * FROM orders WHERE tenant=?"
            params = [tenant]
            if owner_id is not None:
                query += " AND owner_id=?"
                params.append(owner_id)
            return [
                self._order(row)
                for row in connection.execute(
                    query + " ORDER BY created_at DESC, rowid DESC LIMIT 30", params
                )
            ]

    def admin_order(self, tenant, order_id):
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE tenant=? AND id=?", (tenant, order_id)
            ).fetchone()
            if not row:
                raise DomainError("Заказ не найден.", "Order not found.")
            return self._order(row)

    def simulate(self, tenant, owner_id, order_id, outcome):
        with self.db.connect(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM orders WHERE tenant=? AND owner_id=? AND id=?",
                (tenant, owner_id, order_id),
            ).fetchone()
            if not row:
                raise DomainError("Заказ не найден.", "Order not found.")
            status = self.payments.transition(row["status"], outcome)
            connection.execute("UPDATE orders SET status=? WHERE id=?", (status, order_id))
            return {**self._order(row), "status": status}
