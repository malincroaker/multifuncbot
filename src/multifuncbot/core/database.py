"""Small SQLite connection factory; feature modules own their schema."""

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path


class Database:
    def __init__(self, path: str | Path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        self.initialize("""
            CREATE TABLE IF NOT EXISTS preferences (
                user_id INTEGER PRIMARY KEY, language TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS conversations (
                user_id INTEGER NOT NULL, chat_id INTEGER NOT NULL,
                namespace TEXT NOT NULL, data TEXT NOT NULL,
                PRIMARY KEY (user_id, chat_id, namespace)
            );
            CREATE TABLE IF NOT EXISTS outbox (
                id INTEGER PRIMARY KEY, recipient_id INTEGER NOT NULL,
                event_key TEXT NOT NULL, message TEXT NOT NULL,
                delivered INTEGER NOT NULL DEFAULT 0, attempts INTEGER NOT NULL DEFAULT 0,
                retry_at REAL NOT NULL DEFAULT 0, UNIQUE(recipient_id,event_key)
            );
        """)

    @contextmanager
    def connect(self, *, write=False):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            if write:
                connection.execute("BEGIN IMMEDIATE")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self, schema: str):
        with self.connect() as connection:
            connection.executescript(schema)

    def language(self, user_id: int) -> str | None:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT language FROM preferences WHERE user_id=?", (user_id,)
            ).fetchone()
            return row[0] if row else None

    def set_language(self, user_id: int, language: str):
        if language not in ("ru", "en"):
            raise ValueError("Unsupported language")
        with self.connect(write=True) as connection:
            connection.execute(
                "INSERT INTO preferences VALUES (?,?) "
                "ON CONFLICT(user_id) DO UPDATE SET language=excluded.language",
                (user_id, language),
            )

    def state(self, user_id: int, chat_id: int, namespace: str) -> dict:
        with self.connect() as connection:
            row = connection.execute(
                "SELECT data FROM conversations WHERE user_id=? AND chat_id=? AND namespace=?",
                (user_id, chat_id, namespace),
            ).fetchone()
            return json.loads(row[0]) if row else {}

    def set_state(self, user_id: int, chat_id: int, namespace: str, data: dict):
        with self.connect(write=True) as connection:
            connection.execute(
                "INSERT INTO conversations VALUES (?,?,?,?) "
                "ON CONFLICT(user_id,chat_id,namespace) DO UPDATE SET data=excluded.data",
                (user_id, chat_id, namespace, json.dumps(data, ensure_ascii=False)),
            )
