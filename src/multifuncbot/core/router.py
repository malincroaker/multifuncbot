"""Persistent navigation and feature routing, independent of Telegram's API."""

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Context, Screen
from multifuncbot.core.registry import load_features


class Router:
    def __init__(self, db: Database, settings: Settings):
        self.db, self.settings = db, settings
        self.features = load_features(db, settings)

    def context(self, user_id: int, chat_id: int) -> Context:
        return Context(
            self.db,
            self.settings,
            user_id,
            chat_id,
            self.db.language(user_id) or self.settings.default_language,
        )

    def language_menu(self) -> Screen:
        return Screen(
            "Выберите язык / Choose your language",
            [[Button("Русский", "lang:ru"), Button("English", "lang:en")]],
        )

    def menu(self, ctx: Context) -> Screen:
        ctx.save("navigation", {})
        return Screen(
            ctx.tr(
                "Multifuncbot\n\nВыберите сценарий и попробуйте его в роли клиента. "
                "Данные демонстрационные. В демо-кабинете видны только ваши действия.",
                "Multifuncbot\n\nChoose a scenario and try the customer journey. "
                "All data is for demonstration. The demo admin view shows only your actions.",
            ),
            [
                [Button(feature.title(ctx), f"enter:{name}")]
                for name, feature in self.features.items()
            ]
            + [[Button(ctx.tr("Язык / Language", "Language / Язык"), "language")]],
        )

    def enter(self, ctx: Context, name: str) -> Screen:
        if name not in self.features:
            return self.menu(ctx)
        ctx.save("navigation", {"active": name})
        return self.features[name].start(ctx)

    def start(self, user_id: int, chat_id: int) -> Screen:
        ctx = self.context(user_id, chat_id)
        ctx.save("navigation", {})
        if not self.db.language(user_id):
            return self.language_menu()
        return (
            self.enter(ctx, self.settings.default_module)
            if self.settings.default_module
            else self.menu(ctx)
        )

    def action(self, user_id: int, chat_id: int, data: str) -> Screen:
        ctx = self.context(user_id, chat_id)
        if data == "language":
            return self.language_menu()
        if data in ("lang:ru", "lang:en"):
            self.db.set_language(user_id, data.split(":")[1])
            ctx = self.context(user_id, chat_id)
            active = ctx.state("navigation").get("active")
            if active in self.features:
                return self.features[active].action(ctx, "resume")
            return (
                self.enter(ctx, self.settings.default_module)
                if self.settings.default_module
                else self.menu(ctx)
            )
        if data == "home":
            return (
                self.enter(ctx, self.settings.default_module)
                if self.settings.default_module
                else self.menu(ctx)
            )
        if data.startswith("enter:"):
            return self.enter(ctx, data.split(":", 1)[1])
        name, _, action = data.partition(":")
        if name not in self.features or ctx.state("navigation").get("active") != name:
            return self.menu(ctx)
        try:
            return self.features[name].action(ctx, action)
        except DomainError as error:
            return self.error(ctx, name, error)

    def text(self, user_id: int, chat_id: int, text: str) -> Screen:
        ctx = self.context(user_id, chat_id)
        name = ctx.state("navigation").get("active")
        if name not in self.features:
            return self.menu(ctx)
        try:
            return self.features[name].text(ctx, text)
        except DomainError as error:
            return self.error(ctx, name, error)

    @staticmethod
    def error(ctx: Context, name: str, error: DomainError) -> Screen:
        return Screen(
            error.message(ctx.language),
            [
                [Button(ctx.tr("Продолжить", "Continue"), f"{name}:resume")],
                [Button(ctx.tr("Все сценарии", "All scenarios"), "home")],
            ],
        )
