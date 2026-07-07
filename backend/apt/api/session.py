import hashlib
import hmac
from datetime import datetime, timezone

SESSION_COOKIE = "apt_session"
SESSION_TTL_DAYS = 30


def _signature(payload: str, secret: str) -> str:
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def sign_session(user_id: int, expires_at: datetime, secret: str) -> str:
    payload = f"{user_id}.{int(expires_at.timestamp())}"
    return f"{payload}.{_signature(payload, secret)}"


def verify_session(token: str, secret: str, now: datetime) -> int | None:
    parts = token.split(".")
    if len(parts) != 3:
        return None
    user_id, timestamp, signature = parts
    payload = f"{user_id}.{timestamp}"
    if not hmac.compare_digest(signature, _signature(payload, secret)):
        return None
    try:
        expires_at = datetime.fromtimestamp(int(timestamp), tz=timezone.utc)
        parsed_user_id = int(user_id)
    except (ValueError, OverflowError):
        return None
    if now >= expires_at:
        return None
    return parsed_user_id
