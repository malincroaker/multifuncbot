from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Screen, home_button
from multifuncbot.modules.leads.service import LeadService, validate_field

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
STATUSES = {
    "new": ("Новая", "New"),
    "in_progress": ("В работе", "In progress"),
    "done": ("Завершена", "Complete"),
}


class Leads:
    name = "leads"

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
            rows.append([Button(ctx.tr("Кабинет администратора", "Admin view"), "leads:admin")])
        return Screen(
            ctx.tr(
                "Приём заявок · Демо\n\nБот уточнит задачу и контакт, "
                "покажет ответы для проверки и сохранит заявку.",
                "Lead collection · Demo\n\nDescribe your task, leave a contact, "
                "review your answers and submit your request.",
            ),
            rows + [home_button(ctx)],
        )

    def flow(self, ctx):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        for field, prompt in FIELDS.items():
            if field not in draft:
                return Screen(
                    ctx.tr(*prompt),
                    [
                        [Button(ctx.tr("Отменить заполнение", "Cancel draft"), "leads:cancel")],
                        home_button(ctx),
                    ],
                )
        return Screen(
            ctx.tr("Проверьте заявку:\n\n", "Review your request:\n\n")
            + f"{draft['request']}\n{draft['name']}\n{draft['contact']}",
            [
                [Button(ctx.tr("Отправить заявку", "Submit request"), "leads:confirm")],
                [Button(ctx.tr("Исправить ответы", "Edit answers"), "leads:new")],
                home_button(ctx),
            ],
        )

    def listing(self, ctx, admin=False):
        if admin and not ctx.can_admin:
            raise DomainError("Нет доступа.", "Access denied.")
        rows, lines = [], []
        for row in self.service.list(ctx.tenant, None if admin else ctx.user_id):
            lines.append(
                f"#{row['id']} · {ctx.tr(*STATUSES[row['status']])}\n"
                f"{row['request'][:120]}\n{row['name']} · {row['contact']}"
            )
            if admin and row["status"] != "done":
                label = (
                    ctx.tr("Взять в работу", "Start work")
                    if row["status"] == "new"
                    else ctx.tr("Завершить", "Complete")
                )
                rows.append([Button(f"{label} #{row['id']}", f"leads:advance:{row['id']}")])
        return Screen(
            "\n\n".join(lines) or ctx.tr("Заявок пока нет.", "No requests yet."),
            rows + [[Button(ctx.tr("Назад", "Back"), "leads:menu")], home_button(ctx)],
        )

    def action(self, ctx, action):
        command, _, value = action.partition(":")
        if command in ("mine", "admin"):
            return self.listing(ctx, command == "admin")
        if command == "advance":
            if not ctx.can_admin or not value.isdecimal():
                raise DomainError("Нет доступа.", "Access denied.")
            self.service.advance(ctx.tenant, int(value))
            return self.listing(ctx, True)
        if command == "menu":
            return self.start(ctx)
        if command == "cancel":
            ctx.save(self.name, {})
            return self.start(ctx)
        if command == "new":
            ctx.save(self.name, {"active": True})
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
                    *(
                        [[Button(ctx.tr("Кабинет администратора", "Admin view"), "leads:admin")]]
                        if ctx.can_admin
                        else []
                    ),
                    home_button(ctx),
                ],
            )
        return self.flow(ctx)

    def text(self, ctx, text):
        draft = ctx.state(self.name)
        if not draft:
            return self.start(ctx)
        for field in FIELDS:
            if field not in draft:
                draft[field] = validate_field(field, text)
                ctx.save(self.name, draft)
                break
        return self.flow(ctx)


def create(db, settings):
    return Leads(LeadService(db, settings))
