from apt import migrate_main
from apt.repo.db import connect


def test_migrate_main_applies_schema(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("APT_DB_PATH", str(tmp_path / "fresh.db"))
    migrate_main.main()
    conn = connect(tmp_path / "fresh.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] >= 2
