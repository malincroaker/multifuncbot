"""Environment configuration with safe demo defaults."""

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo

MODULE_NAMES = ("guide", "booking", "leads", "shop")


@dataclass(frozen=True)
class Settings:
    bot_token: str = ""
    database_path: str = "data/multifuncbot.sqlite3"
    enabled_modules: tuple[str, ...] = MODULE_NAMES
    default_language: str = "ru"
    timezone: str = "Europe/Moscow"
    app_mode: str = "showcase"
    admin_ids: tuple[int, ...] = ()
    default_module: str = ""
    admin_contact_url: str = ""
    mini_app_url: str = ""
    host: str = "127.0.0.1"
    port: int = 8000
    allow_browser_demo: bool = True
    payment_provider: str = "demo"

    def __post_init__(self):
        if not self.enabled_modules or len(set(self.enabled_modules)) != len(self.enabled_modules):
            raise ValueError("ENABLED_MODULES must contain unique module names")
        if set(self.enabled_modules) - set(MODULE_NAMES):
            raise ValueError("Unknown module in ENABLED_MODULES")
        if self.default_module and self.default_module not in self.enabled_modules:
            raise ValueError("DEFAULT_MODULE must be enabled")
        if self.default_language not in ("ru", "en"):
            raise ValueError("DEFAULT_LANGUAGE must be ru or en")
        if self.app_mode not in ("showcase", "business"):
            raise ValueError("APP_MODE must be showcase or business")
        if self.payment_provider != "demo":
            raise ValueError("Only the demo payment provider is implemented")
        if self.mini_app_url:
            url = urlparse(self.mini_app_url)
            if url.scheme != "https" or not url.netloc or url.username or url.password:
                raise ValueError("MINI_APP_URL must be an HTTPS URL without credentials")
        if self.admin_contact_url:
            url = urlparse(self.admin_contact_url)
            if url.scheme != "https" or url.hostname != "t.me" or not url.path.strip("/"):
                raise ValueError("ADMIN_CONTACT_URL must be an https://t.me/username link")
        ZoneInfo(self.timezone)

    @classmethod
    def from_env(cls):
        from dotenv import load_dotenv

        load_dotenv()
        env = os.environ
        return cls(
            bot_token=env.get("BOT_TOKEN", ""),
            database_path=env.get("DATABASE_PATH", "data/multifuncbot.sqlite3"),
            enabled_modules=tuple(
                x.strip()
                for x in env.get("ENABLED_MODULES", ",".join(MODULE_NAMES)).split(",")
                if x.strip()
            ),
            default_language=env.get("DEFAULT_LANGUAGE", "ru"),
            timezone=env.get("TIMEZONE", "Europe/Moscow"),
            app_mode=env.get("APP_MODE", "showcase"),
            admin_ids=tuple(
                int(x.strip()) for x in env.get("ADMIN_IDS", "").split(",") if x.strip()
            ),
            default_module=env.get("DEFAULT_MODULE", ""),
            admin_contact_url=env.get("ADMIN_CONTACT_URL", ""),
            mini_app_url=env.get("MINI_APP_URL", ""),
            host=env.get("HOST", "127.0.0.1"),
            port=int(env.get("PORT", "8000")),
            allow_browser_demo=env.get("ALLOW_BROWSER_DEMO", "true").lower() == "true",
            payment_provider=env.get("PAYMENT_PROVIDER", "demo"),
        )

    @property
    def database(self) -> Path:
        return Path(self.database_path)
