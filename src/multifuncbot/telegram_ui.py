"""One persistent Telegram screen, with expiring callbacks and separate PDF downloads."""

import logging
from dataclasses import replace
from uuid import uuid4

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from telegram.error import BadRequest, TelegramError

from multifuncbot.core.database import Database
from multifuncbot.core.models import Screen

LOGGER = logging.getLogger(__name__)


def markup(screen: Screen, revision: str | None = None) -> InlineKeyboardMarkup:
    rows = []
    index = 0
    for row in screen.rows:
        buttons = []
        for button in row:
            callback = button.action or None
            if callback and revision is not None:
                callback = f"ui:{revision}:{index}"
            buttons.append(
                InlineKeyboardButton(
                    button.text,
                    callback_data=callback,
                    url=button.url if button.url and not button.web_app else None,
                    web_app=WebAppInfo(button.url) if button.web_app else None,
                )
            )
            index += 1
        rows.append(buttons)
    return InlineKeyboardMarkup(rows)


def not_modified(error: BadRequest) -> bool:
    return "message is not modified" in str(error).lower()


def unavailable(error: BadRequest) -> bool:
    message = str(error).lower()
    return any(
        value in message
        for value in ("message to edit not found", "message can't be edited", "message_id_invalid")
    )


class TelegramUI:
    def __init__(self, db: Database):
        self.db = db

    def state(self, user_id, chat_id):
        return self.db.state(user_id, chat_id, "telegram_ui")

    def resolve(self, user_id, chat_id, message_id, data):
        state = self.state(user_id, chat_id)
        parts = data.split(":")
        if (
            len(parts) != 3
            or parts[0] != "ui"
            or not parts[1]
            or parts[1] != state.get("revision")
            or message_id != state.get("message_id")
            or not parts[2].isascii()
            or not parts[2].isdecimal()
        ):
            return None
        index = int(parts[2])
        actions = state.get("actions", [])
        if index >= len(actions):
            return None
        return actions[index] or None

    def invalidate(self, user_id, chat_id):
        # Consume BEFORE a business action, including when the following edit times out.
        state = self.state(user_id, chat_id)
        state["revision"] = ""
        self.db.set_state(user_id, chat_id, "telegram_ui", state)

    def note_message(self, user_id, chat_id, message_id):
        """Keep notifications/files, but place the next navigation screen below them."""
        previous = self.db.state(user_id, chat_id, "telegram_external").get("message_id", 0)
        self.db.set_state(
            user_id, chat_id, "telegram_external", {"message_id": max(previous, message_id)}
        )

    @staticmethod
    async def retire(bot, chat_id, message_id):
        if not message_id:
            return
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError:
            # An old, undeletable screen must not keep a working-looking keyboard.
            try:
                await bot.edit_message_reply_markup(
                    chat_id=chat_id, message_id=message_id, reply_markup=None
                )
            except TelegramError:
                LOGGER.info("Unable to retire an old Telegram screen")

    @staticmethod
    async def remove_input(bot, chat_id, message_id):
        try:
            await bot.delete_message(chat_id=chat_id, message_id=message_id)
        except TelegramError:
            LOGGER.info("Unable to remove a processed input message")

    async def document(self, bot, chat_id, screen, state):
        """Return whether a newly sent attachment requires moving the screen below it."""
        if not screen.document:
            return False
        caption = "PDF · Stepwise"
        if state.get("document_name") == screen.document.name and state.get("document_id"):
            try:
                await bot.edit_message_caption(
                    chat_id=chat_id, message_id=state["document_id"], caption=caption
                )
                return False
            except BadRequest as error:
                if not_modified(error):
                    return False
                if not unavailable(error):
                    raise
        with screen.document.open("rb") as file:
            message = await bot.send_document(chat_id, file, caption=caption)
        old_document = state.get("document_id")
        state.update(document_id=message.message_id, document_name=screen.document.name)
        # Persist before screen delivery, so a failed edit will not resend the file.
        if old_document:
            await self.retire(bot, chat_id, old_document)
        return True

    async def render(self, bot, user_id, chat_id, screen: Screen):
        state = self.state(user_id, chat_id)
        moved = False
        try:
            moved = await self.document(bot, chat_id, screen, state)
        except (OSError, TelegramError):
            screen = replace(screen, text=screen.text + "\n\nPDF временно недоступен / unavailable")
        self.db.set_state(user_id, chat_id, "telegram_ui", state)
        revision = uuid4().hex[:12]
        keyboard = markup(screen, revision)
        old_id = state.get("message_id")
        latest = self.db.state(user_id, chat_id, "telegram_external").get("message_id", 0)
        latest = max(latest, state.get("document_id", 0))
        moved = moved or latest > (old_id or 0)
        message_id = old_id
        if old_id and not moved:
            try:
                await bot.edit_message_text(
                    chat_id=chat_id,
                    message_id=old_id,
                    text=screen.text,
                    reply_markup=keyboard,
                )
            except BadRequest as error:
                if not not_modified(error):
                    if not unavailable(error):
                        raise
                    message_id = None
        else:
            message_id = None
        # Never send a fallback after a timeout/rate limit: delivery may have succeeded.
        if message_id is None:
            message = await bot.send_message(chat_id, screen.text, reply_markup=keyboard)
            message_id = message.message_id
        state.update(
            message_id=message_id,
            revision=revision,
            actions=[button.action for row in screen.rows for button in row],
        )
        self.db.set_state(user_id, chat_id, "telegram_ui", state)
        if old_id and old_id != message_id:
            await self.retire(bot, chat_id, old_id)
