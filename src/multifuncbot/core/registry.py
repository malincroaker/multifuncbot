"""Only enabled features are imported; no plugin discovery magic."""

from importlib import import_module

from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.models import Feature


def load_features(db: Database, settings: Settings) -> dict[str, Feature]:
    return {
        name: import_module(f"multifuncbot.modules.{name}.feature").create(db, settings)
        for name in settings.enabled_modules
    }
