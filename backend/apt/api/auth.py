import secrets
from datetime import timedelta
from urllib.parse import urlencode

import aiohttp
from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse, RedirectResponse

from apt.api.config import WebConfig
from apt.api.deps import require_user
from apt.api.session import SESSION_COOKIE, SESSION_TTL_DAYS, sign_session
from apt.repo.users import UserRepo

router = APIRouter()

GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_USERINFO_URL = "https://openidconnect.googleapis.com/v1/userinfo"
STATE_COOKIE = "apt_oauth_state"


def _redirect_uri(base_url: str) -> str:
    return f"{base_url}/api/auth/callback"


def _secure(base_url: str) -> bool:
    return base_url.startswith("https://")


@router.get("/api/auth/login")
def login(request: Request) -> RedirectResponse:
    config = request.app.state.config
    state = secrets.token_urlsafe(16)
    params = urlencode({
        "client_id": config.google_client_id,
        "redirect_uri": _redirect_uri(config.base_url),
        "response_type": "code",
        "scope": "openid email",
        "state": state,
    })
    response = RedirectResponse(f"{GOOGLE_AUTH_URL}?{params}")
    response.set_cookie(
        STATE_COOKIE, state, max_age=600, httponly=True,
        samesite="lax", secure=_secure(config.base_url),
    )
    return response


async def _exchange_code(config: WebConfig, code: str) -> dict:
    timeout = aiohttp.ClientTimeout(total=30)
    async with aiohttp.ClientSession(timeout=timeout) as session:
        async with session.post(GOOGLE_TOKEN_URL, data={
            "code": code,
            "client_id": config.google_client_id,
            "client_secret": config.google_client_secret,
            "redirect_uri": _redirect_uri(config.base_url),
            "grant_type": "authorization_code",
        }) as response:
            if response.status >= 300:
                raise HTTPException(status_code=502, detail="google token exchange failed")
            token_payload = await response.json()
        async with session.get(
            GOOGLE_USERINFO_URL,
            headers={"Authorization": f"Bearer {token_payload['access_token']}"},
        ) as response:
            if response.status >= 300:
                raise HTTPException(status_code=502, detail="google userinfo failed")
            return await response.json()


@router.get("/api/auth/callback")
async def callback(request: Request, code: str, state: str) -> RedirectResponse:
    app_state = request.app.state
    expected = request.cookies.get(STATE_COOKIE)
    if not expected or state != expected:
        raise HTTPException(status_code=400, detail="bad oauth state")
    userinfo = await _exchange_code(app_state.config, code)
    now = app_state.now_fn()
    user = UserRepo(app_state.conn).upsert_google_user(userinfo["sub"], userinfo["email"], now)
    token = sign_session(user.id, now + timedelta(days=SESSION_TTL_DAYS), app_state.config.secret_key)
    response = RedirectResponse("/")
    response.set_cookie(
        SESSION_COOKIE, token, max_age=SESSION_TTL_DAYS * 24 * 3600, httponly=True,
        samesite="lax", secure=_secure(app_state.config.base_url),
    )
    response.delete_cookie(STATE_COOKIE)
    return response


@router.post("/api/auth/logout")
def logout() -> JSONResponse:
    response = JSONResponse({"ok": True})
    response.delete_cookie(SESSION_COOKIE)
    response.delete_cookie(STATE_COOKIE)
    return response


@router.get("/api/me")
def me(request: Request) -> dict:
    user = require_user(request)
    config = request.app.state.config
    return {
        "id": user.id,
        "email": user.email,
        "telegram_linked": user.telegram_chat_id is not None,
        "is_admin": user.email in config.admin_emails,
    }
