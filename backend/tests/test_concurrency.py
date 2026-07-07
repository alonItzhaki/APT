import threading
from datetime import datetime, timezone

from apt.domain.models import Listing
from apt.repo.db import connect, migrate
from apt.repo.listings import ListingRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)


def test_reader_not_blocked_while_writer_writes(tmp_path):
    db_path = tmp_path / "concurrent.db"
    setup = connect(db_path)
    migrate(setup)
    ListingRepo(setup).upsert(
        Listing(source="yad2", source_id="seed", url="https://e.com/s", city="חיפה"),
        NOW,
    )
    setup.close()

    errors: list[Exception] = []

    def writer():
        try:
            conn = connect(db_path)
            repo = ListingRepo(conn)
            for i in range(50):
                repo.upsert(
                    Listing(source="yad2", source_id=f"w{i}", url=f"https://e.com/{i}", city="חיפה"),
                    NOW,
                )
            conn.close()
        except Exception as exc:
            errors.append(exc)

    def reader():
        try:
            conn = connect(db_path)
            repo = ListingRepo(conn)
            for _ in range(50):
                assert repo.get("yad2:seed") is not None
            conn.close()
        except Exception as exc:
            errors.append(exc)

    threads = [threading.Thread(target=writer), threading.Thread(target=reader)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert errors == []
