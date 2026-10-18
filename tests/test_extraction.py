import os
import shutil
import subprocess
import sys
from pathlib import Path


def test_guide_runs_when_other_modules_are_physically_absent(tmp_path):
    source = Path(__file__).parents[1] / "src" / "multifuncbot"
    shutil.copytree(
        source,
        tmp_path / "multifuncbot",
        ignore=shutil.ignore_patterns("booking", "leads", "shop", "__pycache__"),
    )
    script = """
import sys
from multifuncbot.core.config import Settings
from multifuncbot.core.database import Database
from multifuncbot.core.router import Router
router = Router(Database('isolated.sqlite3'), Settings(enabled_modules=('guide',)))
assert set(router.features) == {'guide'}
assert 'Stepwise' in router.action(1, 1, 'enter:guide').text
assert 'fastapi' not in sys.modules
print('isolated guide ok')
"""
    result = subprocess.run(
        [sys.executable, "-c", script],
        cwd=tmp_path,
        env={**os.environ, "PYTHONPATH": str(tmp_path)},
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stderr
    assert "isolated guide ok" in result.stdout
