"""Transport-neutral feature contracts."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database


@dataclass(frozen=True)
class Button:
    text: str
    action: str = ""
    url: str = ""
    web_app: bool = False


@dataclass
class Screen:
    """A view plus navigation targets; refresh must never repeat a business mutation."""

    text: str
    rows: list[list[Button]] = field(default_factory=list)
    document: Path | None = None
    back: str = ""
    refresh: str = ""


@dataclass
class Context:
    db: Database
    settings: Settings
    user_id: int
    chat_id: int
    language: str

    def tr(self, ru: str, en: str) -> str:
        return ru if self.language == "ru" else en

    def state(self, namespace: str) -> dict:
        return self.db.state(self.user_id, self.chat_id, namespace)

    def save(self, namespace: str, data: dict):
        self.db.set_state(self.user_id, self.chat_id, namespace, data)

    @property
    def tenant(self) -> int:
        return self.user_id if self.settings.app_mode == "showcase" else 0

    @property
    def can_admin(self) -> bool:
        return self.settings.app_mode == "showcase" or self.user_id in self.settings.admin_ids

    def admin_label(self) -> str:
        return (
            self.tr("🧑‍💼 Демо-кабинет бизнеса", "🧑‍💼 Demo business desk")
            if (self.settings.app_mode == "showcase")
            else self.tr("🧑‍💼 Кабинет бизнеса", "🧑‍💼 Business desk")
        )


class Feature(Protocol):
    name: str

    def title(self, context: Context) -> str: ...
    def start(self, context: Context) -> Screen: ...
    def action(self, context: Context, action: str) -> Screen: ...
    def text(self, context: Context, text: str) -> Screen: ...


def home_button(context: Context) -> list[Button]:
    navigation = context.state("navigation")
    active = navigation.get("active")
    if not active:
        return scenario_exit_button(context)
    names = navigation.get("menu_names")
    label = context.tr("Меню сценария", "Scenario menu")
    if names:
        label = context.tr("Меню · ", "Menu · ") + context.tr(*names)
    return [Button(label, f"{active}:menu")]


def scenario_exit_button(context: Context) -> list[Button]:
    if context.settings.default_module:
        return []
    return [Button(context.tr("Все сценарии", "All scenarios"), "home")]
