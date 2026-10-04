import os
import sys
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from vinedeck.database.database import Database          # noqa: E402
from vinedeck.utils.paths import AppPaths                # noqa: E402


@pytest.fixture
def paths(tmp_path):
    p = AppPaths.under(tmp_path)
    p.ensure()
    return p


@pytest.fixture
def db(paths):
    d = Database(paths.db_path)
    yield d
    d.close()


@pytest.fixture
def mem_db():
    d = Database(":memory:")
    yield d
    d.close()


@pytest.fixture
def exe(tmp_path):
    f = tmp_path / "games" / "Game.exe"
    f.parent.mkdir()
    f.write_bytes(b"MZ")
    return f


@pytest.fixture(scope="session")
def qapp():
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance() or QApplication([])
    yield app
