import sqlite3

import pytest

from vinedeck.database import migrations
from vinedeck.database.database import Database
from vinedeck.database.models import Application


def make(name="Game", **kw):
    return Application(name=name, executable_path=f"/x/{name}.exe", **kw)


def test_creates_database_file_with_defaults(paths):
    db = Database(paths.db_path)
    assert paths.db_path.exists()
    assert [c.name for c in db.list_categories()] == ["Games", "Applications", "Utilities", "Tools", "Other"]
    assert migrations.current_version(db.connection) == migrations.LATEST_VERSION


def test_migrations_upgrade_preserves_data(tmp_path):
    path = tmp_path / "old.db"
    conn = sqlite3.connect(path)
    conn.isolation_level = None
    migrations.migrate(conn, target=1)
    assert migrations.current_version(conn) == 1
    conn.execute("INSERT INTO applications(name, executable_path, created_at, updated_at) "
                 "VALUES ('Old', '/old.exe', 'x', 'x')")
    conn.close()
    db = Database(path)                                # runs v2
    app = db.list_applications()[0]
    assert (app.name, app.developer, app.website) == ("Old", "", "")
    assert migrations.current_version(db.connection) == 2


def test_migrations_idempotent_and_refuse_newer(tmp_path):
    conn = sqlite3.connect(tmp_path / "a.db")
    conn.isolation_level = None
    migrations.migrate(conn)
    migrations.migrate(conn)
    conn.execute("PRAGMA user_version = 99")
    with pytest.raises(RuntimeError):
        migrations.migrate(conn)


def test_create_and_read_application(mem_db):
    games = mem_db.get_category_by_name("games")
    app = mem_db.add_application(make(env_vars={"WINEDEBUG": "-all"}, category_id=games.id,
                                      developer="Dev", favorite=True))
    assert app.id and app.created_at and app.category_name == "Games"
    got = mem_db.get_application(app.id)
    assert got.env_vars == {"WINEDEBUG": "-all"} and got.favorite and got.developer == "Dev"


def test_edit_application(mem_db):
    app = mem_db.add_application(make())
    app.name, app.wine_prefix = "Renamed", "/p"
    out = mem_db.update_application(app)
    assert (out.name, out.wine_prefix) == ("Renamed", "/p")
    assert mem_db.count_applications() == 1


def test_delete_application_cascades_history(mem_db):
    app = mem_db.add_application(make())
    mem_db.record_launch_start(app.id)
    assert mem_db.delete_application(app.id)
    assert mem_db.get_application(app.id) is None
    assert mem_db.connection.execute("SELECT COUNT(*) FROM launch_history").fetchone()[0] == 0


def test_favorites(mem_db):
    app = mem_db.add_application(make())
    mem_db.set_favorite(app.id, True)
    assert mem_db.get_application(app.id).favorite
    mem_db.set_favorite(app.id, False)
    assert not mem_db.get_application(app.id).favorite


def test_categories_crud(mem_db):
    cat = mem_db.add_category("RPG")
    with pytest.raises(ValueError):
        mem_db.add_category("rpg")                     # case-insensitive unique
    with pytest.raises(ValueError):
        mem_db.add_category("   ")
    mem_db.rename_category(cat.id, "JRPG")
    app = mem_db.add_application(make(category_id=cat.id))
    assert mem_db.get_application(app.id).category_name == "JRPG"
    mem_db.delete_category(cat.id)
    kept = mem_db.get_application(app.id)             # app survives, becomes uncategorised
    assert kept is not None and kept.category_id is None


def test_launch_tracking(mem_db):
    app = mem_db.add_application(make())
    hid = mem_db.record_launch_start(app.id)
    mem_db.record_launch_end(hid, 0)
    got = mem_db.get_application(app.id)
    assert got.launch_count == 1 and got.last_played
    assert mem_db.launch_history(app.id)[0]["exit_code"] == 0


def test_reorder(mem_db):
    ids = [mem_db.add_application(make(n)).id for n in "ABCD"]
    mem_db.reorder_application(ids[0], ids[2])        # A after C
    assert [a.name for a in mem_db.list_applications()] == ["B", "C", "A", "D"]
    mem_db.reorder_application(ids[3], ids[1])        # D before B
    assert [a.name for a in mem_db.list_applications()] == ["D", "B", "C", "A"]


def test_corrupt_env_json_is_tolerated(mem_db):
    app = mem_db.add_application(make())
    mem_db.connection.execute("UPDATE applications SET env_vars = 'not json'")
    assert mem_db.get_application(app.id).env_vars == {}
