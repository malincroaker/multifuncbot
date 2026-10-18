"""Persistent navigation and feature routing, independent of Telegram's API."""

from dataclasses import asdict

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.errors import DomainError
from multifuncbot.core.models import Button, Context, Screen, home_button
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

    def language_menu(self, ctx: Context | None = None) -> Screen:
        if ctx and ctx.state("screen").get("back") != "nav:return":
            ctx.save("return_screen", ctx.state("screen"))
        return Screen(
            "Выберите язык / Choose your language",
            [[Button("Русский", "lang:ru"), Button("English", "lang:en")]],
            back="nav:return" if ctx and ctx.state("return_screen") else "",
            refresh="nav:return",
        )

    @staticmethod
    def restore(data: dict) -> Screen:
        return Screen(
            data["text"],
            [[Button(**button) for button in row] for row in data["rows"]],
            back=data.get("back", ""),
            refresh=data.get("refresh", ""),
        )

    def current(self, user_id: int, chat_id: int) -> Screen:
        data = self.db.state(user_id, chat_id, "screen")
        return self.restore(data) if data else self.start(user_id, chat_id)

    def remember(self, user_id: int, chat_id: int, screen: Screen) -> Screen:
        ctx = self.context(user_id, chat_id)
        active = ctx.state("navigation").get("active")
        screen.rows = [row for row in screen.rows if row]
        if not screen.refresh and active in self.features:
            screen.refresh = f"{active}:resume"
        if screen.back and not any(
            button.action == screen.back for row in screen.rows for button in row
        ):
            # Keep the global home link last, consistently across all modules.
            position = next(
                (
                    i
                    for i, row in enumerate(screen.rows)
                    if any(b.action in ("home", f"{active}:menu") for b in row)
                ),
                len(screen.rows),
            )
            screen.rows.insert(position, [Button(ctx.tr("Назад", "Back"), screen.back)])
        self.db.set_state(
            user_id,
            chat_id,
            "screen",
            {
                "text": screen.text,
                "rows": [[asdict(b) for b in row] for row in screen.rows],
                "back": screen.back,
                "refresh": screen.refresh,
            },
        )
        return screen

    def menu(self, ctx: Context) -> Screen:
        self.leave(ctx)
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
        self.leave(ctx)
        ctx.save(
            "navigation",
            {
                "active": name,
                "menu_names": getattr(self.features[name], "menu_names", (name, name)),
            },
        )
        return self.features[name].start(ctx)

    def leave(self, ctx: Context):
        active = ctx.state("navigation").get("active")
        if active in self.features and not getattr(
            self.features[active], "retain_state_on_exit", False
        ):
            ctx.save(active, {})

    def start(self, user_id: int, chat_id: int) -> Screen:
        return self.remember(user_id, chat_id, self._start(user_id, chat_id))

    def _start(self, user_id: int, chat_id: int) -> Screen:
        ctx = self.context(user_id, chat_id)
        self.leave(ctx)
        ctx.save("navigation", {})
        if not self.db.language(user_id):
            return self.language_menu()
        return (
            self.enter(ctx, self.settings.default_module)
            if self.settings.default_module
            else self.menu(ctx)
        )

    def action(self, user_id: int, chat_id: int, data: str) -> Screen:
        return self.remember(user_id, chat_id, self._action(user_id, chat_id, data))

    def notice(self, user_id: int, chat_id: int, data: str) -> Screen:
        parts = data.split(":", 3)
        if len(parts) != 4:
            return self.action(user_id, chat_id, "scenario")
        _, name, action, value = parts
        feature = self.features.get(name)
        if not feature or action not in getattr(feature, "notice_actions", ()):
            return self.action(user_id, chat_id, "scenario")
        ctx = self.context(user_id, chat_id)
        if ctx.state("navigation").get("active") != name:
            self.enter(ctx, name)
        # Only explicitly declared navigation actions are accepted from retained notices.
        # The feature still validates ownership and eligibility before displaying data.
        return self.action(user_id, chat_id, f"{name}:{action}:{value}")

    def _action(self, user_id: int, chat_id: int, data: str) -> Screen:
        ctx = self.context(user_id, chat_id)
        if data == "back":
            return self._action(user_id, chat_id, ctx.state("screen").get("back") or "home")
        if data == "nav:return":
            saved = ctx.state("return_screen")
            return self.restore(saved) if saved else self._action(user_id, chat_id, "home")
        if data == "language":
            return self.language_menu(ctx)
        if data in ("lang:ru", "lang:en"):
            self.db.set_language(user_id, data.split(":")[1])
            ctx = self.context(user_id, chat_id)
            active = ctx.state("navigation").get("active")
            if active in self.features:
                previous = ctx.state("screen")
                if previous.get("refresh") == "nav:return":
                    previous = ctx.state("return_screen")
                name, _, refresh = previous.get("refresh", "").partition(":")
                if name == active:
                    return self.features[active].action(ctx, refresh)
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
        if data == "scenario":
            active = ctx.state("navigation").get("active")
            return (
                self.features[active].action(ctx, "menu")
                if active in self.features
                else (
                    self.enter(ctx, self.settings.default_module)
                    if self.settings.default_module
                    else self.menu(ctx)
                )
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
        return self.remember(user_id, chat_id, self._text(user_id, chat_id, text))

    def _text(self, user_id: int, chat_id: int, text: str) -> Screen:
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
        previous = ctx.state("screen")
        # Repeated invalid text must not create a loop between error screens.
        if previous.get("back") != "nav:return":
            ctx.save("return_screen", previous)
        return Screen(
            error.message(ctx.language),
            [
                [Button(ctx.tr("Продолжить", "Continue"), f"{name}:resume")],
                home_button(ctx),
            ],
            back="nav:return",
        )
