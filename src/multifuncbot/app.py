"""Telegram transport; run with `python -m multifuncbot` or `multifuncbot`."""

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, WebAppInfo
from telegram.error import TelegramError
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    CommandHandler,
    MessageHandler,
    filters,
)

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.models import Screen
from multifuncbot.core.notifications import pending, record_delivery
from multifuncbot.core.router import Router

LOGGER = logging.getLogger(__name__)


def markup(screen: Screen) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    button.text,
                    callback_data=button.action or None,
                    url=button.url if button.url and not button.web_app else None,
                    web_app=WebAppInfo(button.url) if button.web_app else None,
                )
                for button in row
            ]
            for row in screen.rows
        ]
    )


def build_application(settings: Settings) -> Application:
    if not settings.bot_token:
        raise ValueError("Set BOT_TOKEN in .env to run the Telegram bot")
    db = Database(settings.database_path)
    router = Router(db, settings)
    application = Application.builder().token(settings.bot_token).build()
    application.bot_data["router"] = router

    async def reminders(context):
        feature = router.features.get("booking")
        if not feature:
            return
        for record in feature.service.due_reminders():
            language = db.language(record["owner_id"]) or settings.default_language
            message = (
                "Напоминание: запись начнётся в течение часа. /menu — мои записи."
                if language == "ru"
                else "Reminder: your appointment starts within an hour. /menu for appointments."
            )
            try:
                await context.bot.send_message(record["chat_id"], message)
                feature.service.mark_reminded(record["id"])
            except TelegramError:
                LOGGER.warning("Appointment reminder delivery failed")

    if "booking" in router.features:
        application.job_queue.run_repeating(reminders, interval=60, first=10)

    async def notifications(context):
        for item in pending(db):
            try:
                await context.bot.send_message(item["recipient_id"], item["message"])
                record_delivery(db, item["id"], success=True)
            except TelegramError:
                record_delivery(db, item["id"], success=False)
                LOGGER.warning("Notification delivery failed; retry recorded")

    application.job_queue.run_repeating(notifications, interval=15, first=5)

    async def handle(update: Update, context):
        if not update.effective_user or not update.effective_chat:
            return
        if update.effective_chat.type != "private":
            return
        user_id, chat_id = update.effective_user.id, update.effective_chat.id
        if update.callback_query:
            await update.callback_query.answer()
            screen = router.action(user_id, chat_id, update.callback_query.data or "")
        elif update.message and update.message.text:
            command = update.message.text.split()[0].split("@")[0]
            if command == "/start":
                screen = router.start(user_id, chat_id)
            elif command == "/language":
                screen = router.language_menu()
            elif command in ("/help", "/menu", "/cancel"):
                screen = router.action(user_id, chat_id, "home")
            elif command.startswith("/"):
                screen = router.action(user_id, chat_id, "home")
            else:
                screen = router.text(user_id, chat_id, update.message.text)
        else:
            screen = router.action(user_id, chat_id, "home")
        if screen.document:
            try:
                with screen.document.open("rb") as document:
                    await context.bot.send_document(chat_id, document)
            except OSError:
                await context.bot.send_message(chat_id, "PDF unavailable / PDF временно недоступен")
        await context.bot.send_message(chat_id, screen.text, reply_markup=markup(screen))

    async def on_error(update, context):
        # Do not log raw updates, contact details or exception URLs containing tokens.
        LOGGER.error("Telegram handler failed: %s", type(context.error).__name__)
        if isinstance(update, Update) and update.effective_chat:
            try:
                await context.bot.send_message(
                    update.effective_chat.id, "Попробуйте /start / Please try /start"
                )
            except TelegramError:
                LOGGER.warning("Unable to send recovery hint")

    application.add_handler(CommandHandler(["start", "language", "help", "menu", "cancel"], handle))
    application.add_handler(CallbackQueryHandler(handle))
    application.add_handler(MessageHandler(filters.ALL, handle))
    application.add_error_handler(on_error)
    return application


def main():
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    try:
        application = build_application(Settings.from_env())
    except ValueError as error:
        raise SystemExit(str(error)) from error
    application.run_polling(allowed_updates=["message", "callback_query"])
