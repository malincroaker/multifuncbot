"""Persistent lead collection with ownership checks."""

import re

from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import enqueue


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
        with self.db.connect(write=True) as connection:
            row = connection.execute(
                "SELECT status FROM leads WHERE id=? AND tenant=?", (lead_id, tenant)
            ).fetchone()
            if not row or row[0] == "done":
                raise DomainError(
                    "Заявка недоступна или уже завершена.",
                    "Request is unavailable or already complete.",
                )
            connection.execute(
                "UPDATE leads SET status=? WHERE id=?",
                ("in_progress" if row[0] == "new" else "done", lead_id),
            )
