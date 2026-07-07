import secrets

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from apt.api.deps import require_user
from apt.api.session import SESSION_COOKIE
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.users import UserRepo

router = APIRouter()

LINK_EXPIRY_MINUTES = 15


@router.post("/api/telegram/link")
def mint_link(request: Request) -> dict:
    user = require_user(request)
    state = request.app.state
    if not state.config.bot_username:
        raise HTTPException(status_code=503, detail="telegram bot not configured")
    token = secrets.token_urlsafe(24)
    LinkTokenRepo(state.conn).create(token, user.id, state.now_fn())
    return {
        "link": f"https://t.me/{state.config.bot_username}?start={token}",
        "expires_minutes": LINK_EXPIRY_MINUTES,
    }


@router.delete("/api/me")
def delete_me(request: Request) -> JSONResponse:
    user = require_user(request)
    UserRepo(request.app.state.conn).delete(user.id)
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    return response
