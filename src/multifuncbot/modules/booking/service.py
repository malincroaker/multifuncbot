"""One-hour studio appointments, with atomic slot allocation."""

import sqlite3
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from multifuncbot.core.errors import DomainError
from multifuncbot.core.notifications import enqueue
from multifuncbot.core.presentation import display_date, zone_label

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
            CREATE TABLE IF NOT EXISTS booking_feedback (
                booking_id INTEGER PRIMARY KEY REFERENCES bookings(id),
                requested INTEGER NOT NULL DEFAULT 0,
                rating INTEGER CHECK(rating BETWEEN 1 AND 5),
                comment TEXT NOT NULL DEFAULT ''
            );
            INSERT OR IGNORE INTO booking_feedback(booking_id) SELECT id FROM bookings;
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
                connection.execute(
                    "INSERT INTO booking_feedback(booking_id) VALUES(?)", (booking_id,)
                )
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
            if datetime.fromisoformat(row["starts_at"]) <= self.clock():
                raise DomainError(
                    "Визит уже начался. Изменить запись нельзя.",
                    "The visit has started. This booking cannot be changed.",
                )
            allowed = (status == "cancelled" and row["status"] in ("pending", "confirmed")) or (
                admin and status in ("confirmed", "rejected") and row["status"] == "pending"
            )
            if not allowed:
                raise DomainError("Статус записи уже изменился.", "Appointment status has changed.")
            connection.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
            if admin:
                demo_ru = (
                    "Демо · сообщение клиенту\n\n" if self.settings.app_mode == "showcase" else ""
                )
                demo_en = (
                    "Demo · customer notification\n\n"
                    if self.settings.app_mode == "showcase"
                    else ""
                )
                start = datetime.fromisoformat(row["starts_at"]).astimezone(self.zone)
                ru_status, en_status = {
                    "confirmed": ("✅ Подтверждена", "✅ Confirmed"),
                    "rejected": ("❌ Отклонена", "❌ Declined"),
                    "cancelled": ("🚫 Отменена студией", "🚫 Cancelled by studio"),
                }[status]
                enqueue(
                    connection,
                    row["chat_id"],
                    f"booking:{status}:{booking_id}",
                    demo_ru
                    + f"{ru_status}\nЗапись #{booking_id} · {SERVICES[row['service']][0]}\n"
                    + f"{display_date(start.date(), 'ru')} · {start:%H:%M} "
                    + zone_label(self.zone, start)
                    + "\n"
                    + (
                        "Напомним за час до визита."
                        if status == "confirmed"
                        else "Выберите другое удобное время в меню студии."
                    ),
                    demo_en
                    + f"{en_status}\nAppointment #{booking_id} · {SERVICES[row['service']][1]}\n"
                    + f"{display_date(start.date(), 'en')} · {start:%H:%M} "
                    + zone_label(self.zone, start)
                    + "\n"
                    + (
                        "We will remind you an hour before the visit."
                        if status == "confirmed"
                        else "Choose another time from the studio menu."
                    ),
                    self.settings.default_language,
                )

    def due_reminders(self, now=None):
        now = (now or self.clock()).astimezone(UTC)
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

    def feedback(self, tenant, owner_id, booking_id):
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT b.*, f.rating, f.comment, f.requested FROM bookings b "
                "JOIN booking_feedback f ON f.booking_id=b.id "
                "WHERE b.tenant=? AND b.owner_id=? AND b.id=?",
                (tenant, owner_id, booking_id),
            ).fetchone()
            if (
                not row
                or row["status"] != "confirmed"
                or datetime.fromisoformat(row["starts_at"])
                + (timedelta(hours=self.settings.review_delay_hours))
                > self.clock()
            ):
                raise DomainError(
                    "Отзыв доступен после завершённого визита.",
                    "Feedback is available after the visit.",
                )
            return dict(row)

    def due_feedback(self, now=None):
        now = (now or self.clock()).astimezone(UTC)
        with self.db.connect() as connection:
            return [
                dict(row)
                for row in connection.execute(
                    "SELECT b.* FROM bookings b JOIN booking_feedback f ON f.booking_id=b.id "
                    "WHERE b.status='confirmed' AND f.requested=0 AND f.rating IS NULL "
                    "AND b.starts_at<=? ORDER BY b.starts_at LIMIT 20",
                    ((now - timedelta(hours=self.settings.review_delay_hours)).isoformat(),),
                )
            ]

    def mark_feedback_requested(self, booking_id):
        with self.db.connect(write=True) as connection:
            connection.execute(
                "UPDATE booking_feedback SET requested=1 WHERE booking_id=?", (booking_id,)
            )

    def save_feedback(self, tenant, owner_id, booking_id, rating, comment=""):
        if type(rating) is not int or not 1 <= rating <= 5:
            raise DomainError("Выберите оценку от 1 до 5.", "Choose a rating from 1 to 5.")
        comment = self.validate_feedback_comment(comment)
        self.feedback(tenant, owner_id, booking_id)
        with self.db.connect(write=True) as connection:
            row = connection.execute(
                "SELECT rating,comment FROM booking_feedback WHERE booking_id=?", (booking_id,)
            ).fetchone()
            if row["rating"] is not None:
                if row["rating"] == rating and row["comment"] == comment:
                    return
                raise DomainError("Вы уже оставили отзыв.", "Your feedback has already been saved.")
            connection.execute(
                "UPDATE booking_feedback SET rating=?,comment=? WHERE booking_id=?",
                (rating, comment, booking_id),
            )

    @staticmethod
    def validate_feedback_comment(value):
        value = value.strip()
        if len(value) > 500 or any(ord(c) < 32 for c in value):
            raise DomainError(
                "До 500 символов без переносов строк.", "Up to 500 characters without line breaks."
            )
        return value
