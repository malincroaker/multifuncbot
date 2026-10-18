from multifuncbot.core.database import Database


def test_state_is_separate_for_users_chats_and_features(tmp_path):
    db = Database(tmp_path / "test.sqlite3")
    db.set_state(1, 10, "guide", {"step": 2})
    assert db.state(1, 10, "guide") == {"step": 2}
    assert db.state(2, 10, "guide") == {}
    assert db.state(1, 11, "guide") == {}
    assert db.state(1, 10, "booking") == {}
    assert Database(db.path).state(1, 10, "guide") == {"step": 2}
