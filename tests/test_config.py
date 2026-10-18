import pytest

from multifuncbot.core.config import Settings


def test_disabled_default_module_is_rejected():
    with pytest.raises(ValueError, match="DEFAULT_MODULE"):
        Settings(enabled_modules=("guide",), default_module="shop")


def test_unknown_module_cannot_be_imported():
    with pytest.raises(ValueError, match="Unknown module"):
        Settings(enabled_modules=("arbitrary.path",))


def test_configuration_does_not_require_a_bot_token_for_preview():
    assert Settings().bot_token == ""


def test_real_payments_are_not_silently_enabled():
    with pytest.raises(ValueError, match="demo"):
        Settings(payment_provider="live")
