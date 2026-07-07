from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, field_validator

from apt.api.deps import require_user
from apt.domain.models import Alert, AlertFilters
from apt.repo.alerts import AlertRepo

router = APIRouter()

ALLOWED_CHANNELS = {"telegram", "email"}


class AlertIn(BaseModel):
    name: str
    filters: AlertFilters
    channels: list[str]

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name must not be blank")
        return value

    @field_validator("channels")
    @classmethod
    def channels_valid(cls, value: list[str]) -> list[str]:
        deduped = list(dict.fromkeys(value))
        if not deduped or not set(deduped) <= ALLOWED_CHANNELS:
            raise ValueError("channels must be a non-empty subset of telegram/email")
        return deduped

    @field_validator("filters")
    @classmethod
    def needs_location(cls, value: AlertFilters) -> AlertFilters:
        if not value.locations:
            raise ValueError("at least one location is required")
        return value


class ActiveIn(BaseModel):
    active: bool


def _owned_alert(request: Request, alert_id: int) -> Alert:
    user = require_user(request)
    alert = AlertRepo(request.app.state.conn).get(alert_id)
    if alert is None or alert.user_id != user.id:
        raise HTTPException(status_code=404, detail="alert not found")
    return alert


@router.get("/api/alerts")
def list_alerts(request: Request) -> dict:
    user = require_user(request)
    alerts = AlertRepo(request.app.state.conn).list_for_user(user.id)
    return {"alerts": [alert.model_dump(mode="json") for alert in alerts]}


@router.post("/api/alerts", status_code=201)
def create_alert(request: Request, payload: AlertIn) -> dict:
    user = require_user(request)
    state = request.app.state
    alert = AlertRepo(state.conn).create(
        user.id, payload.name, payload.filters, payload.channels, state.now_fn()
    )
    return alert.model_dump(mode="json")


@router.put("/api/alerts/{alert_id}")
def update_alert(request: Request, alert_id: int, payload: AlertIn) -> dict:
    _owned_alert(request, alert_id)
    updated = AlertRepo(request.app.state.conn).update(
        alert_id, payload.name, payload.filters, payload.channels
    )
    return updated.model_dump(mode="json")


@router.post("/api/alerts/{alert_id}/active")
def set_alert_active(request: Request, alert_id: int, payload: ActiveIn) -> dict:
    _owned_alert(request, alert_id)
    repo = AlertRepo(request.app.state.conn)
    repo.set_active(alert_id, payload.active)
    return repo.get(alert_id).model_dump(mode="json")


@router.delete("/api/alerts/{alert_id}")
def delete_alert(request: Request, alert_id: int) -> dict:
    _owned_alert(request, alert_id)
    AlertRepo(request.app.state.conn).delete(alert_id)
    return {"ok": True}
