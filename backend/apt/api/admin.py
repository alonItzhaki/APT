from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from apt.api.deps import require_admin
from apt.repo.source_state import SourceStateRepo
from apt.repo.stats import StatsRepo

router = APIRouter()

KNOWN_SOURCES = {"yad2", "facebook"}


class EnabledIn(BaseModel):
    enabled: bool


@router.get("/api/admin/health")
def health(request: Request) -> dict:
    require_admin(request)
    conn = request.app.state.conn
    return {
        "sources": [state.model_dump(mode="json") for state in SourceStateRepo(conn).all()],
        "counts": StatsRepo(conn).counts(),
    }


@router.post("/api/admin/sources/{source}")
def toggle_source(request: Request, source: str, payload: EnabledIn) -> dict:
    require_admin(request)
    if source not in KNOWN_SOURCES:
        raise HTTPException(status_code=404, detail="unknown source")
    repo = SourceStateRepo(request.app.state.conn)
    repo.set_enabled(source, payload.enabled)
    return repo.get(source).model_dump(mode="json")
