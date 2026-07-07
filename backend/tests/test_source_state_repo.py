from datetime import datetime, timezone

from apt.repo.source_state import SourceStateRepo

T1 = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 7, 7, 12, 15, tzinfo=timezone.utc)


def test_unknown_source_defaults_to_enabled(conn):
    state = SourceStateRepo(conn).get("yad2")
    assert state.enabled is True
    assert state.last_run is None


def test_record_successful_run(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    state = repo.get("yad2")
    assert state.last_run == T1.isoformat()
    assert state.last_success == T1.isoformat()
    assert state.last_error is None


def test_record_failed_run_keeps_last_success(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    repo.record_run("yad2", T2, error="HTTP 403")
    state = repo.get("yad2")
    assert state.last_run == T2.isoformat()
    assert state.last_success == T1.isoformat()
    assert state.last_error == "HTTP 403"


def test_success_clears_previous_error(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("facebook", T1, error="session expired")
    repo.record_run("facebook", T2)
    assert repo.get("facebook").last_error is None


def test_set_enabled_and_all(conn):
    repo = SourceStateRepo(conn)
    repo.record_run("yad2", T1)
    repo.set_enabled("facebook", False)
    assert repo.get("facebook").enabled is False
    assert {state.source for state in repo.all()} == {"yad2", "facebook"}


def test_ensure_default_seeds_without_overwriting(conn):
    repo = SourceStateRepo(conn)
    repo.ensure_default("facebook", enabled=False)
    assert repo.get("facebook").enabled is False
    repo.set_enabled("facebook", True)
    repo.ensure_default("facebook", enabled=False)
    assert repo.get("facebook").enabled is True
