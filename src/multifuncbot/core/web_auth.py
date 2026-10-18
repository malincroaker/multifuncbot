"""Telegram HMAC validation and a completely separate browser-demo identity."""

import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import parse_qsl


def validate_init_data(raw: str, bot_token: str, *, now=None, max_age=3600) -> int:
    if not bot_token or not raw or len(raw) > 8192:
        raise ValueError("Invalid Telegram authentication")
    try:
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError
        received_hash = fields.pop("hash")
        check = "\n".join(f"{key}={value}" for key, value in sorted(fields.items()))
        secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        expected = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, received_hash):
            raise ValueError
        timestamp = int(fields["auth_date"])
        current = time.time() if now is None else now
        if not -30 <= current - timestamp <= max_age:
            raise ValueError
        user = json.loads(fields["user"])
        user_id = user["id"]
        if type(user_id) is not int or not 0 < user_id < 2**63:
            raise ValueError
        return user_id
    except (ValueError, TypeError, KeyError, OverflowError) as error:
        raise ValueError("Invalid Telegram authentication") from error


class BrowserSessions:
    def __init__(self, db):
        self.db = db
        db.initialize("""
            CREATE TABLE IF NOT EXISTS browser_sessions (
                token_hash TEXT PRIMARY KEY, user_id INTEGER UNIQUE NOT NULL,
                expires_at INTEGER NOT NULL
            );
        """)

    def create(self):
        token = secrets.token_urlsafe(32)
        user_id = -secrets.randbelow(2**60) - 1
        with self.db.connect(write=True) as connection:
            connection.execute(
                "DELETE FROM browser_sessions WHERE expires_at<?", (int(time.time()),)
            )
            connection.execute(
                "INSERT INTO browser_sessions VALUES (?,?,?)",
                (hashlib.sha256(token.encode()).hexdigest(), user_id, int(time.time()) + 86400),
            )
        return token, user_id

    def resolve(self, token):
        if not token or len(token) > 100:
            return None
        with self.db.connect() as connection:
            row = connection.execute(
                "SELECT user_id FROM browser_sessions WHERE token_hash=? AND expires_at>?",
                (hashlib.sha256(token.encode()).hexdigest(), int(time.time())),
            ).fetchone()
            return row[0] if row else None
