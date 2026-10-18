from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.router import Router


def test_language_progress_and_pdf_survive_router_restart(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    settings = Settings(enabled_modules=("guide",))
    router = Router(db, settings)
    assert "Choose your language" in router.start(1, 1).text
    router.action(1, 1, "lang:ru")
    router.action(1, 1, "enter:guide")
    router.action(1, 1, "guide:new")
    router.action(1, 1, "guide:next")
    assert "Шаг 2" in router.action(1, 1, "guide:pdf").text
    assert router.action(1, 1, "guide:pdf").document.is_file()
    assert "Step 2" in router.action(1, 1, "lang:en").text
    router = Router(db, settings)
    assert "Step 2" in router.action(1, 1, "guide:resume").text
    assert db.state(2, 2, "guide") == {}


def test_disabled_features_are_not_imported(tmp_path):
    router = Router(Database(tmp_path / "db"), Settings(enabled_modules=("guide",)))
    assert set(router.features) == {"guide"}
    screen = router.action(1, 1, "enter:shop")
    assert any("Stepwise" in button.text for row in screen.rows for button in row)


def test_stale_callback_does_not_mutate_guide_after_exit(tmp_path):
    router = Router(Database(tmp_path / "db"), Settings(enabled_modules=("guide",)))
    router.action(1, 1, "enter:guide")
    router.action(1, 1, "guide:new")
    router.action(1, 1, "home")
    router.action(1, 1, "guide:next")
    assert router.db.state(1, 1, "guide") == {"step": 0}
