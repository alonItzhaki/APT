from datetime import timedelta

from apt.api.session import SESSION_COOKIE, sign_session
from apt.domain.models import AlertFilters
from apt.repo.alerts import AlertRepo
from apt.repo.users import UserRepo
from tests.conftest import FIXED_NOW

VALID = {
    "name": "חיפה עד 6000",
    "filters": {"locations": [{"city": "חיפה"}], "max_price": 6000},
    "channels": ["telegram"],
}


def login(client, conn, web_config, sub="g-1", email="u@example.com"):
    user = UserRepo(conn).upsert_google_user(sub, email, FIXED_NOW)
    token = sign_session(user.id, FIXED_NOW + timedelta(days=30), web_config.secret_key)
    client.cookies.set(SESSION_COOKIE, token)
    return user


def test_alerts_require_auth(client):
    assert client.get("/api/alerts").status_code == 401
    assert client.post("/api/alerts", json=VALID).status_code == 401


def test_create_and_list_alert(client, conn, web_config):
    login(client, conn, web_config)
    created = client.post("/api/alerts", json=VALID)
    assert created.status_code == 201
    alert = created.json()
    assert alert["name"] == VALID["name"]
    assert alert["active"] is True
    listed = client.get("/api/alerts").json()["alerts"]
    assert [item["id"] for item in listed] == [alert["id"]]


def test_validation_rejects_bad_payloads(client, conn, web_config):
    login(client, conn, web_config)
    no_location = {**VALID, "filters": {"locations": []}}
    assert client.post("/api/alerts", json=no_location).status_code == 422
    bad_channel = {**VALID, "channels": ["whatsapp"]}
    assert client.post("/api/alerts", json=bad_channel).status_code == 422
    empty_channels = {**VALID, "channels": []}
    assert client.post("/api/alerts", json=empty_channels).status_code == 422
    blank_name = {**VALID, "name": "   "}
    assert client.post("/api/alerts", json=blank_name).status_code == 422


def test_update_toggle_delete(client, conn, web_config):
    login(client, conn, web_config)
    alert_id = client.post("/api/alerts", json=VALID).json()["id"]
    updated = client.put(f"/api/alerts/{alert_id}", json={**VALID, "name": "חדש"}).json()
    assert updated["name"] == "חדש"
    toggled = client.post(f"/api/alerts/{alert_id}/active", json={"active": False}).json()
    assert toggled["active"] is False
    assert client.delete(f"/api/alerts/{alert_id}").json() == {"ok": True}
    assert client.get("/api/alerts").json()["alerts"] == []


def test_cannot_touch_others_alert(client, conn, web_config):
    other = UserRepo(conn).upsert_google_user("g-2", "other@example.com", FIXED_NOW)
    foreign = AlertRepo(conn).create(other.id, "x", AlertFilters(), ["telegram"], FIXED_NOW)
    login(client, conn, web_config)
    assert client.put(f"/api/alerts/{foreign.id}", json=VALID).status_code == 404
    assert client.delete(f"/api/alerts/{foreign.id}").status_code == 404


def test_mutating_endpoints_require_auth(client):
    assert client.put("/api/alerts/1", json=VALID).status_code == 401
    assert client.post("/api/alerts/1/active", json={"active": False}).status_code == 401
    assert client.delete("/api/alerts/1").status_code == 401


def test_cannot_toggle_others_alert(client, conn, web_config):
    other = UserRepo(conn).upsert_google_user("g-3", "third@example.com", FIXED_NOW)
    foreign = AlertRepo(conn).create(other.id, "x", AlertFilters(), ["telegram"], FIXED_NOW)
    login(client, conn, web_config)
    assert client.post(f"/api/alerts/{foreign.id}/active", json={"active": False}).status_code == 404
