from uuid import uuid4

from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Screen, home_button, scenario_exit_button
from multifuncbot.core.presentation import money
from multifuncbot.modules.shop.catalog import PRODUCTS
from multifuncbot.modules.shop.service import ShopService, customer_field

STATUSES = {
    "awaiting_payment": ("🕓 Ожидает демо-оплаты", "🕓 Awaiting demo payment"),
    "paid": ("✅ Демо-оплата успешна", "✅ Demo payment successful"),
    "payment_failed": ("❌ Демо-оплата отклонена", "❌ Demo payment failed"),
    "cancelled": ("🚫 Отменён", "🚫 Cancelled"),
}


class Shop:
    name = "shop"
    menu_names = ("Магазин", "Shop")

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
        else:
            rows.append(
                [Button(ctx.tr("Mini App · как открыть", "Mini App · how to open"), "shop:miniapp")]
            )
        rows.extend(
            [
                [Button(ctx.tr("Каталог в чате", "Chat catalogue"), "shop:catalog")],
                [Button(ctx.tr("Корзина", "Cart"), "shop:cart")],
                [Button(ctx.tr("Мои заказы", "My orders"), "shop:orders")],
            ]
        )
        if ctx.can_admin:
            rows.append([Button(ctx.admin_label(), "shop:admin")])
        return Screen(
            ctx.tr(
                "Магазин «Место» · Демо\n\nКанцелярия для хороших идей. "
                "Каталог, корзина и оформление заказа в Mini App или в чате. "
                "Оплата имитируется: настоящие деньги не списываются.",
                "Mesto Shop · Demo\n\nStationery for good ideas. "
                "Browse, add to cart and check out in the Mini App or chat. "
                "Payments are simulated: no real money is charged.",
            ),
            rows + [scenario_exit_button(ctx)],
            back="" if ctx.settings.default_module else "home",
            refresh="shop:menu",
        )

    def catalog(self, ctx):
        ctx.save("shop_view", {"item_back": "shop:catalog"})
        return Screen(
            ctx.tr(
                "Каталог «Место»\n\nВыберите товар, чтобы узнать подробности.",
                "Mesto catalogue\n\nChoose a product to see its details.",
            ),
            [
                [
                    Button(
                        f"{product['title'][ctx.language]} · {money(product['price'])}",
                        f"shop:item:{key}",
                    )
                ]
                for key, product in PRODUCTS.items()
            ]
            + [[Button(ctx.tr("Открыть корзину", "Open cart"), "shop:cart")], home_button(ctx)],
            back="shop:menu",
            refresh="shop:catalog",
        )

    def cart(self, ctx):
        ctx.save("shop_view", {"item_back": "shop:cart"})
        cart = self.service.cart(ctx.tenant, ctx.user_id)
        text = ctx.tr("Корзина\n", "Cart\n")
        rows = []
        for line in cart["lines"]:
            short_title = line["title"][ctx.language].split(" «")[0].split(",")[0]
            text += f"\n{line['title'][ctx.language]}\n"
            text += f"{line['quantity']} × {money(line['price'])} = {money(line['line_total'])}\n"
            rows.append(
                [
                    Button("−", f"shop:remove:{line['id']}"),
                    Button(
                        f"{short_title} · {line['quantity']}",
                        f"shop:item:{line['id']}",
                    ),
                    Button("+", f"shop:add:{line['id']}"),
                ]
            )
        text += ctx.tr(
            f"\nИтого: {money(cart['subtotal'])}",
            f"\nTotal: {money(cart['subtotal'])}",
        )
        if cart["count"]:
            rows.append([Button(ctx.tr("Оформить заказ", "Checkout"), "shop:checkout")])
        else:
            text += ctx.tr("\nКорзина пока пуста.", "\nYour cart is empty.")
        return Screen(
            text,
            rows
            + [
                [Button(ctx.tr("Продолжить покупки", "Continue shopping"), "shop:catalog")],
                home_button(ctx),
            ],
            back="shop:menu",
            refresh="shop:cart",
        )

    def checkout_flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        field = self.field(draft)
        if field == "customer_name":
            text = ctx.tr(
                "Оформление заказа\nСамовывоз · бесплатно\n\nКак к вам обращаться?",
                "Checkout\nPickup · free\n\nWhat is your name?",
            )
        elif field == "contact":
            text = ctx.tr(
                "Укажите телефон, email или @username. Можно вымышленные для демо.",
                "Enter a phone, email or @username. Fictional details are fine for the demo.",
            )
        else:
            text = ctx.tr("Проверьте данные · Демо, самовывоз\n", "Review · Demo, pickup\n")
            text += f"\n{draft['customer_name']}\n{draft['contact']}"
            cart = self.service.cart(ctx.tenant, ctx.user_id)
            for line in cart["lines"]:
                text += f"\n{line['title'][ctx.language]} × {line['quantity']}"
            text += ctx.tr("\n\nИтого · ", "\n\nTotal · ") + money(cart["subtotal"])
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
        text = ctx.tr("Заказ #", "Order #") + order["id"][:8] + "\n"
        text += ctx.tr(*STATUSES[order["status"]])
        text += f"\n\n{order['customer_name']} · {order['contact']}\n"
        for line in order["lines"]:
            text += f"\n{line['title'][ctx.language]} × {line['quantity']} · " + money(
                line["line_total"]
            )
        if order["fulfillment"] == "delivery":
            text += ctx.tr("\n\nДоставка · ", "\n\nDelivery · ") + order["address"]
        else:
            text += ctx.tr("\n\nСамовывоз · бесплатно", "\n\nPickup · free")
        text += ctx.tr("\nИтого · ", "\nTotal · ") + money(order["total"])
        text += ctx.tr(
            "\n\nДемонстрация. Деньги не списываются.", "\n\nDemonstration. No money is charged."
        )
        rows = []
        if not admin and order["status"] in ("awaiting_payment", "payment_failed"):
            for label, en, outcome in (
                ("✅ Демо: оплата успешна", "✅ Demo: successful payment", "success"),
                ("❌ Демо: оплата отклонена", "❌ Demo: payment declined", "failure"),
                ("Отменить заказ", "Cancel order", "cancel"),
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
        if command == "miniapp":
            return Screen(
                ctx.tr(
                    "Магазин в Mini App\n\nКарточки товаров, корзина и оформление заказа "
                    "открываются прямо внутри Telegram.\n\nВ этой демонстрации веб-магазин ещё "
                    "не опубликован. Пока можно пройти весь заказ через «Каталог в чате».",
                    "Shop Mini App\n\nBrowse illustrated products, use the cart and check out "
                    "inside Telegram.\n\nThe web shop is not published yet. You can still try "
                    "the full checkout using the chat catalogue.",
                ),
                [
                    [Button(ctx.tr("Каталог в чате", "Chat catalogue"), "shop:catalog")],
                    home_button(ctx),
                ],
                back="shop:menu",
                refresh="shop:miniapp",
            )
        if command == "item":
            if value not in PRODUCTS:
                raise DomainError("Товар не найден.", "Product not found.")
            product = PRODUCTS[value]
            back = ctx.state("shop_view").get("item_back", "shop:catalog")
            return Screen(
                f"{product['title'][ctx.language]}\n\n{product['description'][ctx.language]}\n\n"
                + money(product["price"]),
                [
                    [Button(ctx.tr("Добавить в корзину", "Add to cart"), f"shop:add:{value}")],
                    [Button(ctx.tr("Открыть корзину", "Open cart"), "shop:cart")],
                    home_button(ctx),
                ],
                back=back,
                refresh=f"shop:item:{value}",
            )
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
                            f"#{order['id'][:8]} · {money(order['total'])} · "
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
