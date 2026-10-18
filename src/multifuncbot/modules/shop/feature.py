from uuid import uuid4

from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Screen, home_button
from multifuncbot.modules.shop.catalog import PRODUCTS
from multifuncbot.modules.shop.service import ShopService, customer_field

STATUSES = {
    "awaiting_payment": ("Ожидает демо-оплаты", "Awaiting demo payment"),
    "paid": ("Демо-оплата успешна", "Demo payment successful"),
    "payment_failed": ("Демо-оплата отклонена", "Demo payment failed"),
    "cancelled": ("Отменён", "Cancelled"),
}


class Shop:
    name = "shop"

    def __init__(self, service):
        self.service = service

    def title(self, ctx):
        return ctx.tr("Магазин · Каталог и заказ", "Shop · Catalogue and checkout")

    def start(self, ctx):
        rows = []
        if ctx.settings.mini_app_url:
            rows.append(
                [
                    Button(
                        ctx.tr("Открыть Mini App", "Open Mini App"),
                        url=ctx.settings.mini_app_url,
                        web_app=True,
                    )
                ]
            )
        rows.extend(
            [
                [Button(ctx.tr("Каталог в чате", "Chat catalogue"), "shop:catalog")],
                [Button(ctx.tr("Корзина", "Cart"), "shop:cart")],
                [Button(ctx.tr("Мои заказы", "My orders"), "shop:orders")],
            ]
        )
        if ctx.can_admin:
            rows.append([Button(ctx.tr("Кабинет администратора", "Admin view"), "shop:admin")])
        return Screen(
            ctx.tr(
                "Магазин «Место» · Демо\n\nКанцелярия для хороших идей. "
                "Каталог, корзина и оформление заказа в Mini App или в чате. "
                "Оплата имитируется: настоящие деньги не списываются.",
                "Mesto Shop · Demo\n\nStationery for good ideas. "
                "Browse, add to cart and check out in the Mini App or chat. "
                "Payments are simulated: no real money is charged.",
            ),
            rows + [home_button(ctx)],
            back="home",
            refresh="shop:menu",
        )

    def catalog(self, ctx):
        return Screen(
            ctx.tr("Добавьте товар в корзину:", "Add a product to your cart:"),
            [
                [
                    Button(
                        f"{product['title'][ctx.language]} · {product['price'] // 100} ₽",
                        f"shop:add:{key}",
                    )
                ]
                for key, product in PRODUCTS.items()
            ]
            + [[Button(ctx.tr("Открыть корзину", "Open cart"), "shop:cart")], home_button(ctx)],
            back="shop:menu",
            refresh="shop:catalog",
        )

    def cart(self, ctx):
        cart = self.service.cart(ctx.tenant, ctx.user_id)
        text = ctx.tr("Корзина\n", "Cart\n")
        rows = []
        for line in cart["lines"]:
            text += f"\n{line['title'][ctx.language]} × {line['quantity']} · "
            text += f"{line['line_total'] // 100} ₽"
            rows.append(
                [
                    Button(f"− {line['title'][ctx.language]}", f"shop:remove:{line['id']}"),
                    Button("+", f"shop:add:{line['id']}"),
                ]
            )
        text += ctx.tr(
            f"\n\nИтого: {cart['subtotal'] // 100} ₽",
            "\n\nTotal: " + f"{cart['subtotal'] // 100} ₽",
        )
        if cart["count"]:
            rows.append(
                [Button(ctx.tr("Оформить · самовывоз", "Checkout · pickup"), "shop:checkout")]
            )
        else:
            text += ctx.tr("\nКорзина пока пуста.", "\nYour cart is empty.")
        return Screen(
            text,
            rows + [[Button(ctx.tr("Каталог", "Catalogue"), "shop:catalog")], home_button(ctx)],
            back="shop:menu",
            refresh="shop:cart",
        )

    def checkout_flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        field = self.field(draft)
        if field == "customer_name":
            text = ctx.tr("Как к вам обращаться?", "What is your name?")
        elif field == "contact":
            text = ctx.tr(
                "Укажите телефон, email или @username. Можно вымышленные для демо.",
                "Enter a phone, email or @username. Fictional details are fine for the demo.",
            )
        else:
            text = ctx.tr("Проверьте данные · Демо, самовывоз\n", "Review · Demo, pickup\n")
            text += f"\n{draft['customer_name']}\n{draft['contact']}"
            return Screen(
                text,
                [
                    [Button(ctx.tr("Создать демо-заказ", "Place demo order"), "shop:place")],
                    home_button(ctx),
                ],
                back="shop:back",
            )
        rows = []
        if field in draft:
            text += ctx.tr("\n\nТекущий ответ: ", "\n\nCurrent answer: ") + draft[field]
            rows.append([Button(ctx.tr("Оставить этот ответ", "Keep this answer"), "shop:keep")])
        return Screen(text, rows + [home_button(ctx)], back="shop:back")

    @staticmethod
    def field(draft):
        return draft.get("_field") or next(
            (key for key in ("customer_name", "contact") if key not in draft), "review"
        )

    def advance_field(self, ctx, draft):
        fields = ("customer_name", "contact", "review")
        draft["_field"] = fields[min(fields.index(self.field(draft)) + 1, len(fields) - 1)]
        ctx.save(self.name, draft)

    def order_screen(self, ctx, order, *, admin=False):
        text = f"#{order['id'][:8]} · {order['total'] // 100} ₽\n"
        text += ctx.tr(*STATUSES[order["status"]])
        text += f"\n{order['customer_name']} · {order['contact']}"
        for line in order["lines"]:
            text += f"\n{line['title'][ctx.language]} × {line['quantity']}"
        if order["fulfillment"] == "delivery":
            text += f"\n{order['address']}"
        text += ctx.tr(
            "\n\nДемонстрация. Деньги не списываются.", "\n\nDemonstration. No money is charged."
        )
        rows = []
        if not admin and order["status"] in ("awaiting_payment", "payment_failed"):
            for label, en, outcome in (
                ("Успешная оплата", "Successful payment", "success"),
                ("Отказ оплаты", "Payment failure", "failure"),
                ("Отмена", "Cancel", "cancel"),
            ):
                rows.append([Button(ctx.tr(label, en), f"shop:pay:{order['id']}:{outcome}")])
        return Screen(
            text,
            rows + [home_button(ctx)],
            back="shop:admin" if admin else "shop:orders",
            refresh=f"shop:{'adminorder' if admin else 'order'}:{order['id']}",
        )

    def action(self, ctx, action):
        command, _, value = action.partition(":")
        if command in ("menu", "catalog", "cart", "orders", "admin"):
            ctx.save(self.name, {})
        if command in ("back", "keep"):
            draft = ctx.state(self.name)
            if not draft:
                return self.cart(ctx)
            field = self.field(draft)
            if command == "back":
                if field == "customer_name":
                    ctx.save(self.name, {})
                    return self.cart(ctx)
                draft["_field"] = "contact" if field == "review" else "customer_name"
                ctx.save(self.name, draft)
            elif field in draft:
                self.advance_field(ctx, draft)
            return self.checkout_flow(ctx)
        if command == "catalog":
            return self.catalog(ctx)
        if command in ("add", "remove"):
            cart = self.service.cart(ctx.tenant, ctx.user_id)
            quantity = next((line["quantity"] for line in cart["lines"] if line["id"] == value), 0)
            self.service.set_quantity(
                ctx.tenant, ctx.user_id, value, quantity + (1 if command == "add" else -1)
            )
            return self.cart(ctx)
        if command == "cart":
            return self.cart(ctx)
        if command == "checkout":
            if not self.service.cart(ctx.tenant, ctx.user_id)["count"]:
                return self.cart(ctx)
            ctx.save(self.name, {"request_key": uuid4().hex, "_field": "customer_name"})
            return self.checkout_flow(ctx)
        if command == "place":
            draft = ctx.state(self.name)
            if not all(key in draft for key in ("request_key", "customer_name", "contact")):
                return self.checkout_flow(ctx)
            order = self.service.checkout(
                ctx.tenant,
                ctx.user_id,
                draft["request_key"],
                draft["customer_name"],
                draft["contact"],
                "pickup",
                "",
            )
            ctx.save(self.name, {})
            return self.order_screen(ctx, order)
        if command == "pay":
            order_id, _, outcome = value.partition(":")
            order = self.service.simulate(ctx.tenant, ctx.user_id, order_id, outcome)
            return self.order_screen(ctx, order)
        if command == "order":
            return self.order_screen(ctx, self.service.get_order(ctx.tenant, ctx.user_id, value))
        if command == "adminorder":
            if not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            return self.order_screen(ctx, self.service.admin_order(ctx.tenant, value), admin=True)
        if command in ("orders", "admin"):
            if command == "admin" and not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            orders = self.service.list_orders(
                ctx.tenant, None if command == "admin" else ctx.user_id
            )
            return Screen(
                ctx.tr("Демо-заказы", "Demo orders")
                if orders
                else ctx.tr("Заказов пока нет.", "No orders yet."),
                [
                    [
                        Button(
                            f"#{order['id'][:8]} · {order['total'] // 100} ₽ · "
                            + ctx.tr(*STATUSES[order["status"]]),
                            f"shop:{'adminorder' if command == 'admin' else 'order'}:{order['id']}",
                        )
                    ]
                    for order in orders
                ]
                + [home_button(ctx)],
                back="shop:menu",
                refresh=f"shop:{command}",
            )
        if command == "resume" and ctx.state(self.name):
            return self.checkout_flow(ctx)
        return self.start(ctx)

    def text(self, ctx, text):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        field = self.field(draft)
        if field in ("customer_name", "contact"):
            draft["_field"] = field
            draft[field] = customer_field(field, text)
            self.advance_field(ctx, draft)
        return self.checkout_flow(ctx)


def create(db, settings):
    return Shop(ShopService(db, settings))
