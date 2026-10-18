from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Screen, home_button, scenario_exit_button
from multifuncbot.modules.leads.service import (
    STATUSES,
    TRANSITIONS,
    LeadService,
    validate_comment,
    validate_field,
)

FIELDS = {
    "request": (
        "Опишите, какая услуга вам нужна (5–1000 символов).",
        "Describe the service you need (5–1000 characters).",
    ),
    "name": ("Как к вам обращаться?", "What is your name?"),
    "contact": (
        "Укажите телефон, email или @username. В демо можно использовать вымышленные данные.",
        "Enter your phone, email or @username. Fictional contact details are fine in this demo.",
    ),
}


class Leads:
    name = "leads"
    menu_names = ("Заявки", "Requests")

    def __init__(self, service):
        self.service = service

    def title(self, ctx):
        return ctx.tr("Услуги · Приём заявок", "Services · Lead collection")

    def start(self, ctx):
        rows = [
            [Button(ctx.tr("Оставить заявку", "Submit a request"), "leads:new")],
            [Button(ctx.tr("Мои заявки", "My requests"), "leads:mine")],
        ]
        if ctx.can_admin:
            rows.append([Button(ctx.admin_label(), "leads:admin")])
        return Screen(
            ctx.tr(
                "Приём заявок · Демо\n\nБот уточнит задачу и контакт, "
                "покажет ответы для проверки и сохранит заявку.",
                "Lead collection · Demo\n\nDescribe your task, leave a contact, "
                "review your answers and submit your request.",
            ),
            rows + [scenario_exit_button(ctx)],
            back="" if ctx.settings.default_module else "home",
            refresh="leads:menu",
        )

    def flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        if "status_change" in draft:
            return self.status_screen(ctx)
        field = self.field(draft)
        if field != "review":
            text = ctx.tr(*FIELDS[field])
            rows = []
            if field in draft:
                text += ctx.tr("\n\nТекущий ответ: ", "\n\nCurrent answer: ") + draft[field]
                rows.append(
                    [Button(ctx.tr("Оставить этот ответ", "Keep this answer"), "leads:keep")]
                )
            return Screen(
                text,
                rows
                + [
                    [Button(ctx.tr("Отменить заполнение", "Cancel draft"), "leads:cancel")],
                    home_button(ctx),
                ],
                back="leads:back",
            )
        return Screen(
            ctx.tr("Проверьте заявку:\n\n", "Review your request:\n\n")
            + f"{draft['request']}\n{draft['name']}\n{draft['contact']}",
            [
                [Button(ctx.tr("Отправить заявку", "Submit request"), "leads:confirm")],
                [Button(ctx.tr("Исправить ответы", "Edit answers"), "leads:edit")],
                home_button(ctx),
            ],
            back="leads:back",
        )

    @staticmethod
    def field(draft):
        return draft.get("_field") or next((key for key in FIELDS if key not in draft), "review")

    def advance_field(self, ctx, draft):
        fields = (*FIELDS, "review")
        draft["_field"] = fields[min(fields.index(self.field(draft)) + 1, len(fields) - 1)]
        ctx.save(self.name, draft)

    def listing(self, ctx, admin=False):
        if admin and not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        rows = []
        lines = [ctx.admin_label() if admin else ctx.tr("Мои заявки", "My requests")]
        if admin and ctx.settings.app_mode == "showcase":
            lines.append(
                ctx.tr(
                    "Управляйте своими демо-заявками. Изменения придут вам как клиенту.",
                    "Manage your demo requests. Updates will reach you as the customer.",
                )
            )
        for row in self.service.list(ctx.tenant, None if admin else ctx.user_id):
            lines.append(
                f"#{row['id']} · {ctx.tr(*STATUSES[row['status']])}\n"
                f"{row['request'][:120]}\n{row['name']} · {row['contact']}"
            )
            rows.append(
                [
                    Button(
                        ctx.tr(f"Открыть заявку #{row['id']}", f"Open request #{row['id']}"),
                        f"leads:{'adminitem' if admin else 'item'}:{row['id']}",
                    )
                ]
            )
        if not rows:
            lines.append(ctx.tr("Заявок пока нет.", "No requests yet."))
        return Screen(
            "\n\n".join(lines) or ctx.tr("Заявок пока нет.", "No requests yet."),
            rows + [home_button(ctx)],
            back="leads:menu",
            refresh="leads:admin" if admin else "leads:mine",
        )

    def detail(self, ctx, lead_id, admin=False):
        if admin and not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        record = self.service.get(ctx.tenant, lead_id, None if admin else ctx.user_id)
        text = ctx.tr(f"Заявка #{lead_id}\n", f"Request #{lead_id}\n")
        text += ctx.tr(*STATUSES[record["status"]])
        text += f"\n\n{record['request']}\n\n{record['name']} · {record['contact']}"
        if record["comment"]:
            text += ctx.tr("\n\nКомментарий: ", "\n\nComment: ") + record["comment"]
        labels = {
            "new": ("↩ Вернуть в новые", "↩ Return to new"),
            "in_progress": ("🔧 Взять в работу", "🔧 Start / resume work"),
            "paused": ("⏸ Поставить на паузу", "⏸ Pause"),
            "done": ("✅ Завершить", "✅ Complete"),
            "rejected": ("❌ Отказаться с комментарием", "❌ Decline with a reason"),
        }
        rows = (
            [
                [Button(ctx.tr(*labels[target]), f"leads:status:{lead_id}:{target}")]
                for target in TRANSITIONS[record["status"]]
            ]
            if admin
            else []
        )
        if admin:
            history = self.service.history(ctx.tenant, lead_id)[-3:]
            if history:
                text += ctx.tr("\n\nПоследние изменения:", "\n\nRecent changes:")
                for event in history:
                    text += "\n" + ctx.tr(*STATUSES[event["status"]])
                    if event["comment"]:
                        text += " · " + event["comment"][:100]
        return Screen(
            text,
            rows + [home_button(ctx)],
            back="leads:admin" if admin else "leads:mine",
            refresh=f"leads:{'adminitem' if admin else 'item'}:{lead_id}",
        )

    def status_screen(self, ctx):
        if not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        change = ctx.state(self.name).get("status_change")
        if not change:
            return self.listing(ctx, True)
        record = self.service.get(ctx.tenant, change["id"])
        target = ctx.tr(*STATUSES[change["target"]])
        if "comment" not in change:
            text = ctx.tr(
                "Укажите причину для клиента (до 500 символов).",
                "Write a reason for the customer (up to 500 characters).",
            )
            rows = (
                [[Button(ctx.tr("Без комментария", "No comment"), "leads:status-skip")]]
                if (change["target"] == "paused")
                else []
            )
        else:
            text = ctx.tr(
                "Проверьте изменение. Клиент получит уведомление.",
                "Review the change. The customer will be notified.",
            )
            text += "\n\n" + change["comment"]
            rows = [
                [Button(ctx.tr("Подтвердить изменение", "Confirm change"), "leads:status-confirm")]
            ]
        text = f"#{record['id']} · {target}\n\n" + text
        return Screen(text, rows + [home_button(ctx)], back=f"leads:adminitem:{record['id']}")

    def action(self, ctx, action):
        command, _, value = action.partition(":")
        if command in ("item", "adminitem"):
            if not value.isdecimal():
                raise DomainError("Заявка не найдена.", "Request not found.")
            ctx.save(self.name, {})
            return self.detail(ctx, int(value), command == "adminitem")
        if command == "status":
            lead_id, _, target = value.partition(":")
            if not ctx.can_admin or not lead_id.isdecimal():
                raise DomainError("Нет доступа.", "Access denied.")
            record = self.service.get(ctx.tenant, int(lead_id))
            if target not in TRANSITIONS[record["status"]]:
                raise DomainError("Статус уже изменился.", "Status has changed.")
            if target in ("paused", "rejected"):
                ctx.save(
                    self.name,
                    {
                        "status_change": {
                            "id": int(lead_id),
                            "target": target,
                            "from": record["status"],
                        }
                    },
                )
                return self.status_screen(ctx)
            self.service.change_status(ctx.tenant, int(lead_id), target, expected=record["status"])
            return self.detail(ctx, int(lead_id), True)
        if command in ("status-confirm", "status-skip"):
            if not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            draft = ctx.state(self.name)
            change = draft.get("status_change")
            if not change:
                return self.listing(ctx, True)
            if command == "status-skip" and change["target"] == "paused":
                change["comment"] = ""
                ctx.save(self.name, draft)
                return self.status_screen(ctx)
            if "comment" not in change:
                return self.status_screen(ctx)
            self.service.change_status(
                ctx.tenant,
                change["id"],
                change["target"],
                change["comment"],
                expected=change["from"],
            )
            ctx.save(self.name, {})
            return self.detail(ctx, change["id"], True)
        if command in ("mine", "admin"):
            ctx.save(self.name, {})
            return self.listing(ctx, command == "admin")
        if command == "advance":
            if not ctx.can_admin or not value.isdecimal():
                raise DomainError("Нет доступа.", "Access denied.")
            self.service.advance(ctx.tenant, int(value))
            return self.listing(ctx, True)
        if command in ("menu", "cancel"):
            ctx.save(self.name, {})
            return self.start(ctx)
        if command == "new":
            ctx.save(self.name, {"active": True, "_field": "request"})
        elif command in ("back", "keep", "edit"):
            draft = ctx.state(self.name)
            if not draft:
                return self.start(ctx)
            field = self.field(draft)
            if command == "back":
                fields = (*FIELDS, "review")
                if field == fields[0]:
                    ctx.save(self.name, {})
                    return self.start(ctx)
                draft["_field"] = fields[fields.index(field) - 1]
                ctx.save(self.name, draft)
            elif command == "edit":
                draft["_field"] = "request"
                ctx.save(self.name, draft)
            elif field in draft:
                self.advance_field(ctx, draft)
        elif command == "confirm":
            draft = ctx.state(self.name)
            if not all(field in draft for field in FIELDS):
                return self.flow(ctx)
            lead_id = self.service.create(ctx.tenant, ctx.user_id, draft)
            ctx.save(self.name, {})
            return Screen(
                ctx.tr(f"Заявка #{lead_id} сохранена.", f"Request #{lead_id} saved."),
                [
                    [Button(ctx.tr("Мои заявки", "My requests"), "leads:mine")],
                    *([[Button(ctx.admin_label(), "leads:admin")]] if ctx.can_admin else []),
                    home_button(ctx),
                ],
                back="leads:menu",
            )
        return self.flow(ctx)

    def text(self, ctx, text):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        if "status_change" in draft:
            if not ctx.can_admin:
                raise DomainError("Нет доступа.", "Access denied.")
            change = draft["status_change"]
            change["comment"] = validate_comment(text, required=change["target"] == "rejected")
            ctx.save(self.name, draft)
            return self.status_screen(ctx)
        field = self.field(draft)
        if field in FIELDS:
            draft["_field"] = field
            draft[field] = validate_field(field, text)
            self.advance_field(ctx, draft)
        return self.flow(ctx)


def create(db, settings):
    return Leads(LeadService(db, settings))
