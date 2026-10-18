"""One-hour studio appointments, with atomic slot allocation."""

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import enqueue

SERVICES = {
    "haircut": ("Стрижка", "Haircut", 180000),
    "styling": ("Укладка", "Hair styling", 220000),
    "care": ("Уход за волосами", "Hair treatment", 260000),
}
SPECIALISTS = {"anna": ("Анна", "Anna"), "alex": ("Алекс", "Alex")}
HOURS = (10, 11, 12, 14, 15, 16)


class BookingService:
    def __init__(self, db, settings, clock=None):
        self.db, self.settings = db, settings
        self.clock = clock or (lambda: datetime.now(UTC))
        self.zone = ZoneInfo(settings.timezone)
        db.initialize("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INTEGER PRIMARY KEY, tenant INTEGER NOT NULL,
                owner_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                service TEXT NOT NULL, specialist TEXT NOT NULL,
                starts_at TEXT NOT NULL, status TEXT NOT NULL DEFAULT 'pending',
                reminder_sent INTEGER NOT NULL DEFAULT 0
            );
            CREATE UNIQUE INDEX IF NOT EXISTS booking_active_slot
                ON bookings(tenant,specialist,starts_at)
                WHERE status IN ('pending','confirmed');
        """)

    def days(self):
        today = self.clock().astimezone(self.zone).date()
        return [
            (today + timedelta(days=offset)).isoformat()
            for offset in range(1, 8)
            if (today + timedelta(days=offset)).weekday() != 6
        ]

    def slots(self, tenant, specialist, day):
        if specialist not in SPECIALISTS or day not in self.days():
            raise DomainError(
                "Выберите доступную дату и специалиста.", "Choose an available date and specialist."
            )
        with self.db.connect() as connection:
            busy = {
                row[0]
                for row in connection.execute(
                    "SELECT starts_at FROM bookings WHERE tenant=? AND specialist=? "
                    "AND status IN ('pending','confirmed')",
                    (tenant, specialist),
                )
            }
        slots = []
        for hour in HOURS:
            start = datetime.fromisoformat(f"{day}T{hour:02}:00:00").replace(tzinfo=self.zone)
            value = start.astimezone(UTC).isoformat()
            if value not in busy:
                slots.append(value)
        return slots

    def book(self, tenant, owner_id, chat_id, service, specialist, starts_at):
        if service not in SERVICES:
            raise DomainError("Выберите услугу из списка.", "Choose a service from the list.")
        try:
            start = datetime.fromisoformat(starts_at)
            if start.tzinfo is None:
                raise ValueError
            day = start.astimezone(self.zone).date().isoformat()
        except (TypeError, ValueError) as error:
            raise DomainError("Неверное время записи.", "Invalid appointment time.") from error
        starts_at = start.astimezone(UTC).isoformat()
        if starts_at not in self.slots(tenant, specialist, day):
            raise DomainError(
                "Это время уже занято. Выберите другое.",
                "This slot is unavailable. Choose another time.",
            )
        try:
            with self.db.connect(write=True) as connection:
                cursor = connection.execute(
                    "INSERT INTO bookings(tenant,owner_id,chat_id,service,specialist,starts_at) "
                    "VALUES (?,?,?,?,?,?)",
                    (tenant, owner_id, chat_id, service, specialist, starts_at),
                )
                booking_id = cursor.lastrowid
                if self.settings.app_mode == "business":
                    for recipient in self.settings.admin_ids:
                        enqueue(
                            connection,
                            recipient,
                            f"booking:new:{booking_id}",
                            f"Новая запись #{booking_id}. /menu → Запись → Кабинет администратора.",
                            f"New appointment #{booking_id}. /menu → Appointments → Admin view.",
                            self.settings.default_language,
                        )
                return booking_id
        except sqlite3.IntegrityError as error:
            raise DomainError(
                "Это время уже занято. Выберите другое.",
                "This slot is unavailable. Choose another time.",
            ) from error

    def list(self, tenant, owner_id=None):
        with self.db.connect() as connection:
            query = "SELECT * FROM bookings WHERE tenant=?"
            params = [tenant]
            if owner_id is not None:
                query += " AND owner_id=?"
                params.append(owner_id)
            return [dict(row) for row in connection.execute(query + " ORDER BY starts_at", params)]

    def change_status(self, tenant, owner_id, booking_id, status, *, admin=False):
        with self.db.connect(write=True) as connection:
            row = connection.execute(
                "SELECT * FROM bookings WHERE tenant=? AND id=?", (tenant, booking_id)
            ).fetchone()
            if not row or (not admin and row["owner_id"] != owner_id):
                raise DomainError("Запись не найдена.", "Appointment not found.")
            allowed = (status == "cancelled" and row["status"] in ("pending", "confirmed")) or (
                admin and status in ("confirmed", "rejected") and row["status"] == "pending"
            )
            if not allowed:
                raise DomainError("Статус записи уже изменился.", "Appointment status has changed.")
            connection.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
            if admin and self.settings.app_mode == "business":
                enqueue(
                    connection,
                    row["chat_id"],
                    f"booking:{status}:{booking_id}",
                    f"Запись #{booking_id}: "
                    + ("подтверждена." if status == "confirmed" else "отклонена."),
                    f"Appointment #{booking_id}: {status}.",
                    self.settings.default_language,
                )

    def due_reminders(self, now=None):
        now = now or self.clock()
        with self.db.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT * FROM bookings WHERE status='confirmed' AND reminder_sent=0 "
                    "AND starts_at>? AND starts_at<=?",
                    (now.isoformat(), (now + timedelta(hours=1)).isoformat()),
                )
            ]

    def mark_reminded(self, booking_id):
        with self.db.connect(write=True) as connection:
            connection.execute("UPDATE bookings SET reminder_sent=1 WHERE id=?", (booking_id,))
