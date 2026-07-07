from fastapi import HTTPException, Request

from apt.api.session import SESSION_COOKIE, verify_session
from apt.domain.models import User
from apt.repo.users import UserRepo


def current_user(request: Request) -> User | None:
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        return None
    state = request.app.state
    user_id = verify_session(token, state.config.secret_key, state.now_fn())
    if user_id is None:
        return None
    return UserRepo(state.conn).get(user_id)


def require_user(request: Request) -> User:
    user = current_user(request)
    if user is None:
        raise HTTPException(status_code=401, detail="not authenticated")
    return user


def require_admin(request: Request) -> User:
    user = require_user(request)
    if user.email not in request.app.state.config.admin_emails:
        raise HTTPException(status_code=403, detail="admin only")
    return user
