from datetime import datetime

from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Context, Screen, home_button
from multifuncbot.modules.booking.service import SERVICES, SPECIALISTS, BookingService

STATUSES = {
    "pending": ("Ожидает подтверждения", "Pending confirmation"),
    "confirmed": ("Подтверждена", "Confirmed"),
    "rejected": ("Отклонена", "Rejected"),
    "cancelled": ("Отменена", "Cancelled"),
}
STAGES = ("service", "specialist", "day", "starts_at", "review")


class Booking:
    name = "booking"

    def __init__(self, service):
        self.service = service

    def title(self, ctx):
        return ctx.tr("Студия · Запись на услуги", "Studio · Appointments")

    def start(self, ctx):
        rows = [
            [Button(ctx.tr("Записаться", "Book an appointment"), "booking:new")],
            [Button(ctx.tr("Мои записи", "My appointments"), "booking:mine")],
        ]
        if ctx.can_admin:
            rows.append([Button(ctx.tr("Кабинет администратора", "Admin view"), "booking:admin")])
        return Screen(
            ctx.tr(
                "Студия «Линия» · Демо\n\nУслуга длится 60 минут. Работаем пн–сб, "
                "10:00–17:00, перерыв 13:00–14:00. Часовой пояс: ",
                "Line Studio · Demo\n\nEach service takes 60 minutes. Mon–Sat, "
                "10:00–17:00, break 13:00–14:00. Timezone: ",
            )
            + ctx.settings.timezone,
            rows + [home_button(ctx)],
            back="home",
            refresh="booking:menu",
        )

    def flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        stage = draft.get("_step") or next(
            (key for key in STAGES[:-1] if key not in draft), "review"
        )
        if stage == "service":
            return Screen(
                ctx.tr(
                    "Выберите услугу. Цены демонстрационные.",
                    "Choose a service. Prices are demonstration data.",
                ),
                [
                    [Button(f"{ctx.tr(ru, en)} · {price // 100} ₽", f"booking:service:{key}")]
                    for key, (ru, en, price) in SERVICES.items()
                ]
                + [home_button(ctx)],
                back="booking:back",
            )
        if stage == "specialist":
            return Screen(
                ctx.tr("Выберите специалиста:", "Choose a specialist:"),
                [
                    [Button(ctx.tr(*names), f"booking:specialist:{key}")]
                    for key, names in SPECIALISTS.items()
                ]
                + [home_button(ctx)],
                back="booking:back",
            )
        if stage == "day":
            return Screen(
                ctx.tr("Выберите дату:", "Choose a date:"),
                [[Button(day, f"booking:day:{day}")] for day in self.service.days()]
                + [home_button(ctx)],
                back="booking:back",
            )
        if stage == "starts_at":
            slots = self.service.slots(ctx.tenant, draft["specialist"], draft["day"])
            return Screen(
                ctx.tr("Выберите время:", "Choose a time:")
                if slots
                else ctx.tr(
                    "На эту дату мест нет. Выберите другую.", "No slots left. Choose another date."
                ),
                [
                    [
                        Button(
                            datetime.fromisoformat(slot)
                            .astimezone(self.service.zone)
                            .strftime("%H:%M"),
                            f"booking:slot:{slot}",
                        )
                    ]
                    for slot in slots
                ]
                + [
                    [Button(ctx.tr("Другая дата", "Another date"), "booking:dates")],
                    home_button(ctx),
                ],
                back="booking:back",
            )
        service = SERVICES[draft["service"]]
        specialist = SPECIALISTS[draft["specialist"]]
        return Screen(
            ctx.tr("Проверьте запись:\n\n", "Review appointment:\n\n")
            + f"{ctx.tr(*service[:2])} · {service[2] // 100} ₽\n"
            + f"{ctx.tr(*specialist)}\n{draft['day']} "
            + datetime.fromisoformat(draft["starts_at"])
            .astimezone(self.service.zone)
            .strftime("%H:%M")
            + "\n"
            + ctx.settings.timezone,
            [
                [Button(ctx.tr("Подтвердить запись", "Confirm booking"), "booking:confirm")],
                [Button(ctx.tr("Начать заново", "Start again"), "booking:new")],
                home_button(ctx),
            ],
            back="booking:back",
        )

    def listing(self, ctx, admin=False):
        if admin and not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        records = self.service.list(ctx.tenant, None if admin else ctx.user_id)[-15:]
        text = (
            ctx.tr("Кабинет администратора", "Admin view")
            if admin
            else ctx.tr("Мои записи", "My appointments")
        )
        rows = []
        for row in records:
            start = datetime.fromisoformat(row["starts_at"]).astimezone(self.service.zone)
            text += (
                f"\n\n#{row['id']} · {start:%Y-%m-%d %H:%M}\n"
                + ctx.tr(*SERVICES[row["service"]][:2])
                + " · "
                + ctx.tr(*SPECIALISTS[row["specialist"]])
            )
            text += "\n" + ctx.tr(*STATUSES[row["status"]])
            if row["status"] in ("pending", "confirmed"):
                rows.append(
                    [
                        Button(
                            ctx.tr(f"Отменить #{row['id']}", f"Cancel #{row['id']}"),
                            f"booking:cancel:{row['id']}",
                        )
                    ]
                )
            if admin and row["status"] == "pending":
                rows.append(
                    [
                        Button(
                            ctx.tr(f"Подтвердить #{row['id']}", f"Approve #{row['id']}"),
                            f"booking:approve:{row['id']}",
                        ),
                        Button(
                            ctx.tr(f"Отклонить #{row['id']}", f"Reject #{row['id']}"),
                            f"booking:reject:{row['id']}",
                        ),
                    ]
                )
        if not records:
            text += ctx.tr("\n\nЗаписей пока нет.", "\n\nNo appointments yet.")
        return Screen(
            text,
            rows + [home_button(ctx)],
            back="booking:menu",
            refresh="booking:admin" if admin else "booking:mine",
        )

    def action(self, ctx: Context, action: str):
        command, _, value = action.partition(":")
        if command == "menu":
            ctx.save(self.name, {})
            return self.start(ctx)
        if command in ("mine", "admin"):
            return self.listing(ctx, command == "admin")
        if command in ("cancel", "approve", "reject"):
            if not value.isdecimal():
                raise DomainError("Неверная запись.", "Invalid appointment.")
            is_admin = command != "cancel"
            if is_admin and not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            self.service.change_status(
                ctx.tenant,
                ctx.user_id,
                int(value),
                {"cancel": "cancelled", "approve": "confirmed", "reject": "rejected"}[command],
                admin=is_admin,
            )
            return self.listing(ctx, is_admin)
        draft = ctx.state(self.name)
        if command == "new":
            draft = {"active": True, "_step": "service"}
        elif command == "back":
            stage = draft.get("_step") or next(
                (key for key in STAGES[:-1] if key not in draft), "review"
            )
            if not draft or stage == "service":
                ctx.save(self.name, {})
                return self.start(ctx)
            draft["_step"] = STAGES[STAGES.index(stage) - 1]
        elif command == "service" and value in SERVICES and draft:
            if value != draft.get("service"):
                draft = {"active": True, "service": value}
            draft["_step"] = "specialist"
        elif command == "specialist" and value in SPECIALISTS and "service" in draft:
            if value != draft.get("specialist"):
                draft = {"active": True, "service": draft["service"], "specialist": value}
            draft["_step"] = "day"
        elif command == "day" and "specialist" in draft and value in self.service.days():
            draft.pop("starts_at", None)
            draft["day"] = value
            draft["_step"] = "starts_at"
        elif command == "dates":
            draft.pop("day", None)
            draft.pop("starts_at", None)
            draft["_step"] = "day"
        elif command == "slot" and "day" in draft:
            if value not in self.service.slots(ctx.tenant, draft["specialist"], draft["day"]):
                raise DomainError("Время недоступно. Выберите другое.", "Slot unavailable.")
            draft["starts_at"] = value
            draft["_step"] = "review"
        elif command == "confirm" and "starts_at" in draft:
            booking_id = self.service.book(
                ctx.tenant,
                ctx.user_id,
                ctx.chat_id,
                draft["service"],
                draft["specialist"],
                draft["starts_at"],
            )
            ctx.save(self.name, {})
            return Screen(
                ctx.tr(
                    f"Запись #{booking_id} создана и ожидает подтверждения. "
                    "Посмотрите её в кабинете администратора.",
                    f"Appointment #{booking_id} is pending confirmation. "
                    "You can review it in the admin view.",
                ),
                [
                    [Button(ctx.tr("Мои записи", "My appointments"), "booking:mine")],
                    *(
                        [[Button(ctx.tr("Кабинет администратора", "Admin view"), "booking:admin")]]
                        if ctx.can_admin
                        else []
                    ),
                    home_button(ctx),
                ],
                back="booking:menu",
            )
        ctx.save(self.name, draft)
        return self.flow(ctx)

    def text(self, ctx, text):
        return self.flow(ctx)


def create(db, settings):
    return Booking(BookingService(db, settings))
