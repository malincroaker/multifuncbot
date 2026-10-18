from datetime import datetime, timedelta

from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Context, Screen, home_button, scenario_exit_button
from multifuncbot.core.presentation import display_date, money, zone_label
from multifuncbot.modules.booking.service import SERVICES, SPECIALISTS, BookingService

STATUSES = {
    "pending": ("🕓 Ожидает подтверждения", "🕓 Pending confirmation"),
    "confirmed": ("✅ Подтверждена", "✅ Confirmed"),
    "rejected": ("❌ Отклонена", "❌ Rejected"),
    "cancelled": ("🚫 Отменена", "🚫 Cancelled"),
}
STAGES = ("service", "specialist", "day", "starts_at", "review")


class Booking:
    name = "booking"
    menu_names = ("Студия", "Studio")
    notice_actions = {"review"}

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
            rows.append([Button(ctx.admin_label(), "booking:admin")])
        rows.append([Button(ctx.tr("Связаться со студией", "Contact studio"), "booking:contact")])
        if ctx.settings.app_mode == "showcase":
            rows.append(
                [
                    Button(
                        ctx.tr("Напоминания и отзывы · пример", "Reminders & reviews · preview"),
                        "booking:followup-demo",
                    )
                ]
            )
        return Screen(
            ctx.tr(
                "Студия «Линия»\nСтрижка · укладка · уход за волосами\n\n"
                "🕒 Пн–сб · 10:00–17:00\nПерерыв · 13:00–14:00\n"
                "⏱ Длительность услуги · 60 минут\nВремя · ",
                "Line Studio\nHaircuts · styling · hair care\n\n"
                "🕒 Mon–Sat · 10:00–17:00\nBreak · 13:00–14:00\n"
                "⏱ Appointment · 60 minutes\nTimezone · ",
            )
            + zone_label(self.service.zone, self.service.clock())
            + ctx.tr(
                "\n\nДемо: услуги и цены вымышлены.", "\n\nDemo: fictional services and prices."
            ),
            rows + [scenario_exit_button(ctx)],
            back="" if ctx.settings.default_module else "home",
            refresh="booking:menu",
        )

    def flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        if "feedback" in draft:
            return self.feedback_screen(ctx)
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
                    [Button(f"{ctx.tr(ru, en)} · {money(price)}", f"booking:service:{key}")]
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
                [
                    [Button(display_date(day, ctx.language), f"booking:day:{day}")]
                    for day in self.service.days()
                ]
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
            + f"{ctx.tr(*service[:2])} · {money(service[2])}\n"
            + ctx.tr("Мастер · ", "Specialist · ")
            + f"{ctx.tr(*specialist)}\n"
            + display_date(draft["day"], ctx.language)
            + " · "
            + datetime.fromisoformat(draft["starts_at"])
            .astimezone(self.service.zone)
            .strftime("%H:%M")
            + " "
            + zone_label(self.service.zone, datetime.fromisoformat(draft["starts_at"]))
            + ctx.tr(
                "\n\nПосле подтверждения студией напомним за час до визита.",
                "\n\nOnce approved, we will remind you an hour before your visit.",
            ),
            [
                [Button(ctx.tr("Подтвердить запись", "Confirm booking"), "booking:confirm")],
                home_button(ctx),
            ],
            back="booking:back",
        )

    def listing(self, ctx, admin=False):
        if admin and not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        records = self.service.list(ctx.tenant, None if admin else ctx.user_id)[-15:]
        text = ctx.admin_label() if admin else ctx.tr("Мои записи", "My appointments")
        if admin and ctx.settings.app_mode == "showcase":
            text += ctx.tr(
                "\nЗдесь только ваши демо-записи. После решения вы получите сообщение как клиент.",
                "\nOnly your demo visits appear here. Decisions will reach you as the customer.",
            )
        rows = []
        for row in records:
            start = datetime.fromisoformat(row["starts_at"]).astimezone(self.service.zone)
            text += (
                f"\n\n#{row['id']} · {display_date(start.date(), ctx.language)} · {start:%H:%M} "
                + zone_label(self.service.zone, start)
                + "\n"
                + ctx.tr(*SERVICES[row["service"]][:2])
                + " · "
                + ctx.tr(*SPECIALISTS[row["specialist"]])
            )
            text += "\n" + ctx.tr(*STATUSES[row["status"]])
            if row["status"] in ("pending", "confirmed") and start > self.service.clock():
                rows.append(
                    [
                        Button(
                            ctx.tr(f"Отменить #{row['id']}", f"Cancel #{row['id']}"),
                            f"booking:{'admincancel' if admin else 'cancel'}:{row['id']}",
                        )
                    ]
                )
            if admin and row["status"] == "pending" and start > self.service.clock():
                rows.append(
                    [
                        Button(
                            ctx.tr(f"✅ Подтвердить #{row['id']}", f"✅ Approve #{row['id']}"),
                            f"booking:approve:{row['id']}",
                        ),
                        Button(
                            ctx.tr(f"❌ Отклонить #{row['id']}", f"❌ Reject #{row['id']}"),
                            f"booking:reject:{row['id']}",
                        ),
                    ]
                )
            if (
                row["status"] == "confirmed"
                and start + timedelta(hours=ctx.settings.review_delay_hours) <= self.service.clock()
            ):
                feedback = self.service.feedback(ctx.tenant, row["owner_id"], row["id"])
                if feedback["rating"] is None and not admin:
                    rows.append(
                        [
                            Button(
                                ctx.tr(
                                    f"⭐ Оценить визит #{row['id']}", f"⭐ Rate visit #{row['id']}"
                                ),
                                f"booking:review:{row['id']}",
                            )
                        ]
                    )
                elif feedback["rating"] is not None:
                    text += ctx.tr(
                        f"\nОценка визита · {feedback['rating']}/5 ⭐",
                        f"\nVisit rating · {feedback['rating']}/5 ⭐",
                    )
                    if admin and feedback["comment"]:
                        text += " · " + feedback["comment"][:80]
        if not records:
            text += ctx.tr("\n\nЗаписей пока нет.", "\n\nNo appointments yet.")
        elif not admin:
            rows.append(
                [
                    Button(
                        ctx.tr("Связаться со студией / мастером", "Contact studio / specialist"),
                        "booking:contact",
                    )
                ]
            )
        return Screen(
            text,
            rows + [home_button(ctx)],
            back="booking:menu",
            refresh="booking:admin" if admin else "booking:mine",
        )

    def feedback_screen(self, ctx):
        draft = ctx.state(self.name)
        value = draft.get("feedback")
        if value is None:
            return self.listing(ctx)
        demo = value == "demo"
        if not demo:
            record = self.service.feedback(ctx.tenant, ctx.user_id, value)
            if record["rating"] is not None:
                return Screen(
                    ctx.tr(
                        "Спасибо! Ваш отзыв уже сохранён.",
                        "Thank you! Your feedback has already been saved.",
                    ),
                    [home_button(ctx)],
                    back="booking:mine",
                )
        title = (
            ctx.tr(
                "Пример отзыва · данные не отправляются студии",
                "Sample review · not sent to a studio",
            )
            if demo
            else (ctx.tr(f"Отзыв о визите #{value}", f"Review visit #{value}"))
        )
        if "rating" not in draft:
            return Screen(
                title
                + ctx.tr(
                    "\n\nКак прошёл приём? Выберите оценку от 1 до 5.",
                    "\n\nHow was your visit? Choose a rating from 1 to 5.",
                ),
                [
                    [Button(f"{score} ⭐", f"booking:rating:{score}") for score in range(1, 6)],
                    home_button(ctx),
                ],
                back="booking:followup-demo" if demo else "booking:mine",
            )
        text = title + ctx.tr(
            f"\n\nОценка · {draft['rating']}/5 ⭐", f"\n\nRating · {draft['rating']}/5 ⭐"
        )
        if draft.get("comment"):
            text += "\n\n" + draft["comment"]
        else:
            text += ctx.tr(
                "\n\nПри желании напишите комментарий (до 500 символов) "
                "или отправьте только оценку.",
                "\n\nOptionally write a comment (up to 500 characters), or submit just the rating.",
            )
        return Screen(
            text,
            [
                [Button(ctx.tr("Отправить отзыв", "Submit review"), "booking:feedback-submit")],
                home_button(ctx),
            ],
            back="booking:feedback-back",
        )

    def reminder_text(self, record, language):
        start = datetime.fromisoformat(record["starts_at"]).astimezone(self.service.zone)
        details = (
            f"#{record['id']} · {display_date(start.date(), language)} · {start:%H:%M} "
            + zone_label(self.service.zone, start)
        )
        service = SERVICES[record["service"]][0 if language == "ru" else 1]
        specialist = SPECIALISTS[record["specialist"]][0 if language == "ru" else 1]
        return ("🔔 Скоро ваш визит\n" if language == "ru" else "🔔 Your visit is coming up\n") + (
            f"{details}\n{service} · {specialist}\n\n"
            + (
                "До начала — не больше часа. /menu → Мои записи. "
                "Если планы изменились, свяжитесь со студией."
                if language == "ru"
                else "Your appointment starts within an hour. /menu → My appointments. "
                "Contact the studio if plans change."
            )
        )

    def action(self, ctx: Context, action: str):
        command, _, value = action.partition(":")
        if command == "contact":
            rows = []
            if ctx.settings.studio_contact_url:
                rows.append(
                    [
                        Button(
                            ctx.tr("Написать в студию", "Message studio"),
                            url=ctx.settings.studio_contact_url,
                        )
                    ]
                )
            return Screen(
                ctx.tr(
                    "Связь со студией\n\nУточните детали визита "
                    "или попросите связаться с вашим мастером.",
                    "Contact the studio\n\nAsk about your visit "
                    "or request a conversation with your specialist.",
                )
                + (
                    ""
                    if rows
                    else ctx.tr(
                        "\n\nЭто демо-студия: реальный контакт пока не подключён.",
                        "\n\nThis is a demo studio: a real contact is not connected yet.",
                    )
                ),
                rows + [home_button(ctx)],
                back="booking:menu",
                refresh="booking:contact",
            )
        if command == "followup-demo":
            ctx.save(self.name, {})
            return Screen(
                ctx.tr(
                    "После записи\n\n✅ Студия подтверждает визит — клиент получает сообщение.\n"
                    "🔔 За час до визита — напоминание с услугой, мастером и временем.\n"
                    f"⭐ Через {ctx.settings.review_delay_hours} ч после начала "
                    "— просьба оценить приём.\n\n"
                    "Ниже можно попробовать форму отзыва сразу, без создания записи и ожидания.",
                    "After booking\n\n✅ Studio approval — customer notification.\n"
                    "🔔 An hour before the visit — service, specialist and time reminder.\n"
                    f"⭐ {ctx.settings.review_delay_hours} hours after the start "
                    "— request to rate the visit.\n\n"
                    "Try the sample review below without creating an appointment or waiting.",
                ),
                [
                    [
                        Button(
                            ctx.tr("Попробовать отзыв", "Try a sample review"),
                            "booking:demo-review",
                        )
                    ],
                    home_button(ctx),
                ],
                back="booking:menu",
                refresh="booking:followup-demo",
            )
        if command in ("review", "demo-review"):
            if command == "review":
                if not value.isdecimal():
                    raise DomainError("Запись не найдена.", "Appointment not found.")
                self.service.feedback(ctx.tenant, ctx.user_id, int(value))
            elif ctx.settings.app_mode != "showcase":
                raise DomainError("Доступно только в демо.", "Available only in showcase mode.")
            feedback_id = int(value) if command == "review" else "demo"
            if ctx.state(self.name).get("feedback") != feedback_id:
                ctx.save(self.name, {"feedback": feedback_id})
            return self.feedback_screen(ctx)
        if command in ("rating", "feedback-back", "feedback-submit"):
            draft = ctx.state(self.name)
            if "feedback" not in draft:
                return self.listing(ctx)
            if command == "rating" and value in ("1", "2", "3", "4", "5"):
                draft["rating"] = int(value)
            elif command == "feedback-back":
                draft.pop("rating", None)
            elif command == "feedback-submit" and "rating" in draft:
                demo = draft["feedback"] == "demo"
                if not demo:
                    self.service.save_feedback(
                        ctx.tenant,
                        ctx.user_id,
                        draft["feedback"],
                        draft["rating"],
                        draft.get("comment", ""),
                    )
                ctx.save(self.name, {})
                return Screen(
                    ctx.tr("Спасибо за отзыв!", "Thank you for your feedback!")
                    + (
                        ctx.tr(
                            "\nЭто был пример: реальные записи не изменились.",
                            "\nThis was a preview: no actual appointments were changed.",
                        )
                        if demo
                        else ""
                    ),
                    [home_button(ctx)],
                    back="booking:followup-demo" if demo else "booking:mine",
                )
            ctx.save(self.name, draft)
            return self.feedback_screen(ctx)
        if command == "menu":
            ctx.save(self.name, {})
            return self.start(ctx)
        if command in ("mine", "admin"):
            ctx.save(self.name, {})
            return self.listing(ctx, command == "admin")
        if command in ("cancel", "admincancel", "approve", "reject"):
            if not value.isdecimal():
                raise DomainError("Неверная запись.", "Invalid appointment.")
            is_admin = command != "cancel"
            if is_admin and not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            self.service.change_status(
                ctx.tenant,
                ctx.user_id,
                int(value),
                {
                    "cancel": "cancelled",
                    "admincancel": "cancelled",
                    "approve": "confirmed",
                    "reject": "rejected",
                }[command],
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
                    f"🕓 Запись #{booking_id} создана и ожидает подтверждения. "
                    "Студия подтвердит время. Статус появится в «Мои записи».",
                    f"🕓 Appointment #{booking_id} is pending confirmation. "
                    "The studio will confirm the time. Check My appointments for updates.",
                ),
                [
                    [Button(ctx.tr("Мои записи", "My appointments"), "booking:mine")],
                    *([[Button(ctx.admin_label(), "booking:admin")]] if ctx.can_admin else []),
                    home_button(ctx),
                ],
                back="booking:menu",
            )
        ctx.save(self.name, draft)
        return self.flow(ctx)

    def text(self, ctx, text):
        draft = ctx.state(self.name)
        if "feedback" in draft and "rating" in draft:
            draft["comment"] = self.service.validate_feedback_comment(text)
            ctx.save(self.name, draft)
            return self.feedback_screen(ctx)
        return self.flow(ctx)


def create(db, settings):
    return Booking(BookingService(db, settings))
