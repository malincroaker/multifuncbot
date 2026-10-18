"""Telegram transport; run with `python -m multifuncbot` or `multifuncbot`."""

import logging
from dataclasses import replace

from telegram import BotCommand, Update
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
from multifuncbot.core.notifications import pending, record_delivery
from multifuncbot.core.router import Router
from multifuncbot.telegram_ui import TelegramUI
from multifuncbot.telegram_ui import markup as markup

LOGGER = logging.getLogger(__name__)


def build_application(settings: Settings) -> Application:
    if not settings.bot_token:
        raise ValueError("Set BOT_TOKEN in .env to run the Telegram bot")
    db = Database(settings.database_path)
    router = Router(db, settings)
    ui = TelegramUI(db)

    async def commands(application):
        for language, labels in (
            ("", ("Main menu", "Back", "Language")),
            ("ru", ("Главное меню", "Назад", "Язык")),
        ):
            try:
                await application.bot.set_my_commands(
                    [
                        BotCommand(command, label)
                        for command, label in zip(("menu", "back", "language"), labels, strict=True)
                    ],
                    language_code=language,
                )
            except TelegramError:
                LOGGER.warning("Unable to update the Telegram command menu")

    application = Application.builder().token(settings.bot_token).post_init(commands).build()
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
                delivered = await context.bot.send_message(record["chat_id"], message)
                ui.note_message(record["owner_id"], record["chat_id"], delivered.message_id)
                feature.service.mark_reminded(record["id"])
            except TelegramError:
                LOGGER.warning("Appointment reminder delivery failed")

    if "booking" in router.features:
        application.job_queue.run_repeating(reminders, interval=60, first=10)

    async def notifications(context):
        for item in pending(db):
            try:
                delivered = await context.bot.send_message(item["recipient_id"], item["message"])
                ui.note_message(item["recipient_id"], item["recipient_id"], delivered.message_id)
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
            query = update.callback_query
            message_id = query.message.message_id if query.message else None
            action = ui.resolve(user_id, chat_id, message_id, query.data or "")
            try:
                await query.answer(
                    text=None
                    if action
                    else router.context(user_id, chat_id).tr(
                        "Эта кнопка устарела. Используйте текущий экран или /menu.",
                        "This button expired. Use the current screen or /menu.",
                    )
                )
            except TelegramError:
                LOGGER.info("Unable to acknowledge callback query")
            if not action:
                if message_id != ui.state(user_id, chat_id).get("message_id"):
                    await ui.retire(context.bot, chat_id, message_id)
                # Show a fresh keyboard without executing the stale business action.
                await ui.render(context.bot, user_id, chat_id, router.current(user_id, chat_id))
                return
            ui.invalidate(user_id, chat_id)
            screen = router.action(user_id, chat_id, action)
        elif update.message and update.message.text:
            words = update.message.text.split(maxsplit=1)
            command = words[0].split("@")[0] if words else ""
            if command == "/start":
                screen = router.start(user_id, chat_id)
            elif command == "/language":
                screen = router.action(user_id, chat_id, "language")
            elif command == "/back":
                screen = router.action(user_id, chat_id, "back")
            elif command in ("/help", "/menu", "/cancel"):
                screen = router.action(user_id, chat_id, "home")
            elif command.startswith("/"):
                screen = router.action(user_id, chat_id, "home")
            else:
                screen = router.text(user_id, chat_id, update.message.text)
        else:
            if update.message:
                ui.note_message(user_id, chat_id, update.message.message_id)
            screen = router.action(user_id, chat_id, "home")
        await ui.render(context.bot, user_id, chat_id, screen)
        if update.message and update.message.text:
            # Only remove text after the result is visible. Files sent by the user stay intact.
            await ui.remove_input(context.bot, chat_id, update.message.message_id)

    async def on_error(update, context):
        # Do not log raw updates, contact details or exception URLs containing tokens.
        LOGGER.error("Telegram handler failed: %s", type(context.error).__name__)
        if (
            isinstance(update, Update)
            and update.effective_chat
            and update.effective_user
            and update.effective_chat.type == "private"
        ):
            try:
                user_id, chat_id = update.effective_user.id, update.effective_chat.id
                screen = router.current(user_id, chat_id)
                await ui.render(
                    context.bot,
                    user_id,
                    chat_id,
                    replace(screen, text="Попробуйте /menu / Please try /menu\n\n" + screen.text),
                )
            except TelegramError:
                LOGGER.warning("Unable to send recovery hint")

    application.add_handler(
        CommandHandler(["start", "language", "help", "menu", "cancel", "back"], handle)
    )
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
