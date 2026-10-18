"""Persistent notification outbox. Network delivery belongs to the Telegram transport."""

import time


def enqueue(connection, recipient_id, event_key, ru, en, default_language="ru"):
    if recipient_id <= 0:
        return  # Anonymous browser identities are never Telegram chat IDs.
    row = connection.execute(
        "SELECT language FROM preferences WHERE user_id=?", (recipient_id,)
    ).fetchone()
    language = row[0] if row else default_language
    connection.execute(
        "INSERT OR IGNORE INTO outbox(recipient_id,event_key,message) VALUES (?,?,?)",
        (recipient_id, event_key, ru if language == "ru" else en),
    )


def pending(db):
    with db.connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM outbox WHERE delivered=0 AND attempts<5 AND retry_at<=? "
                "ORDER BY id LIMIT 20",
                (time.time(),),
            )
        ]


def record_delivery(db, notification_id, *, success):
    with db.connect(write=True) as connection:
        connection.execute(
            "UPDATE outbox SET delivered=?, attempts=attempts+1, retry_at=? WHERE id=?",
            (int(success), time.time() + 60, notification_id),
        )
