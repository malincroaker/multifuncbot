"""Persistent lead collection with ownership checks."""

import re

from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import enqueue

STATUSES = {
    "new": ("🆕 Новая", "🆕 New"),
    "in_progress": ("🔧 В работе", "🔧 In progress"),
    "paused": ("⏸ На паузе", "⏸ Paused"),
    "done": ("✅ Завершена", "✅ Complete"),
    "rejected": ("❌ Отклонена", "❌ Declined"),
}
TRANSITIONS = {
    "new": ("in_progress", "paused", "rejected"),
    "in_progress": ("paused", "done", "new", "rejected"),
    "paused": ("in_progress", "new", "rejected"),
    "done": ("in_progress",),
    "rejected": ("new",),
}


def validate_comment(value, *, required=False):
    value = value.strip()
    if (required and not value) or len(value) > 500 or any(ord(c) < 32 for c in value):
        raise DomainError(
            "Комментарий: от 1 до 500 символов без переносов строк.",
            "Comment: 1–500 characters without line breaks.",
        )
    return value


def validate_field(field, value):
    value = value.strip()
    limits = {"request": (5, 1000), "name": (2, 80), "contact": (3, 120)}
    lower, upper = limits[field]
    if not lower <= len(value) <= upper or any(ord(char) < 32 for char in value):
        raise DomainError(
            f"Введите от {lower} до {upper} символов без переносов строк.",
            f"Enter {lower}–{upper} characters without line breaks.",
        )
    if field == "contact" and not (
        re.fullmatch(r"@[A-Za-z0-9_]{5,32}", value)
        or re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value)
        or (re.fullmatch(r"\+?[0-9 ()-]+", value) and 10 <= len(re.sub(r"\D", "", value)) <= 15)
    ):
        raise DomainError(
            "Укажите телефон, email или @username (от 5 символов).",
            "Enter a phone number, email or @username (at least 5 characters).",
        )
    return value


class LeadService:
    def __init__(self, db, settings=None):
        self.db = db
        self.settings = settings
        db.initialize("""
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY, tenant INTEGER NOT NULL, owner_id INTEGER NOT NULL,
                request TEXT NOT NULL, name TEXT NOT NULL, contact TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'new',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS lead_events (
                id INTEGER PRIMARY KEY, lead_id INTEGER NOT NULL REFERENCES leads(id),
                status TEXT NOT NULL, comment TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
        """)

    def create(self, tenant, owner_id, draft):
        values = [
            validate_field(field, draft.get(field, "")) for field in ("request", "name", "contact")
        ]
        with self.db.connect(write=True) as connection:
            lead_id = connection.execute(
                "INSERT INTO leads(tenant,owner_id,request,name,contact) VALUES (?,?,?,?,?)",
                [tenant, owner_id, *values],
            ).lastrowid
            if self.settings and self.settings.app_mode == "business":
                for recipient in self.settings.admin_ids:
                    enqueue(
                        connection,
                        recipient,
                        f"leads:new:{lead_id}",
                        f"Новая заявка #{lead_id}. /menu → Заявки → Кабинет администратора.",
                        f"New request #{lead_id}. /menu → Lead collection → Admin view.",
                        self.settings.default_language,
                    )
            return lead_id

    def list(self, tenant, owner_id=None):
        with self.db.connect() as connection:
            query = "SELECT * FROM leads WHERE tenant=?"
            params = [tenant]
            if owner_id is not None:
                query += " AND owner_id=?"
                params.append(owner_id)
            return [
                dict(row)
                for row in connection.execute(query + " ORDER BY id DESC LIMIT 10", params)
            ]

    def advance(self, tenant, lead_id):
        record = self.get(tenant, lead_id)
        self.change_status(
            tenant,
            lead_id,
            "in_progress" if record["status"] == "new" else "done",
            expected=record["status"],
        )

    def get(self, tenant, lead_id, owner_id=None):
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT * FROM leads WHERE tenant=? AND id=?", (tenant, lead_id)
            ).fetchone()
            if not row or (owner_id is not None and row["owner_id"] != owner_id):
                raise DomainError("Заявка не найдена.", "Request not found.")
            latest = connection.execute(
                "SELECT comment FROM lead_events WHERE lead_id=? ORDER BY id DESC LIMIT 1",
                (lead_id,),
            ).fetchone()
            return {**dict(row), "comment": latest["comment"] if latest else ""}

    def history(self, tenant, lead_id):
        self.get(tenant, lead_id)
        with self.db.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM lead_events WHERE lead_id=? ORDER BY id", (lead_id,)
                )
            ]

    def change_status(self, tenant, lead_id, status, comment="", *, expected=None):
        comment = validate_comment(comment, required=status == "rejected")
        with self.db.connect(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM leads WHERE id=? AND tenant=?", (lead_id, tenant)
            ).fetchone()
            if (
                not row
                or status not in TRANSITIONS.get(row["status"], ())
                or (expected is not None and row["status"] != expected)
            ):
                raise DomainError(
                    "Статус уже изменился. Откройте заявку снова.",
                    "The status has changed. Reopen the request.",
                )
            connection.execute(
                "UPDATE leads SET status=? WHERE id=?",
                (status, lead_id),
            )
            event_id = connection.execute(
                "INSERT INTO lead_events(lead_id,status,comment) VALUES(?,?,?)",
                (lead_id, status, comment),
            ).lastrowid
            demo = self.settings is not None and self.settings.app_mode == "showcase"
            enqueue(
                connection,
                row["owner_id"],
                f"leads:event:{event_id}",
                ("Демо · сообщение клиенту\n\n" if demo else "")
                + f"Заявка #{lead_id}\n{STATUSES[status][0]}"
                + (f"\nКомментарий: {comment}" if comment else ""),
                ("Demo · customer notification\n\n" if demo else "")
                + f"Request #{lead_id}\n{STATUSES[status][1]}"
                + (f"\nComment: {comment}" if comment else ""),
                self.settings.default_language if self.settings else "ru",
            )
