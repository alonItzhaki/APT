import aiohttp

from apt.domain.events import MatchEvent
from apt.domain.models import User
from apt.notify.format import email_html, email_subject

BREVO_URL = "https://api.brevo.com/v3/smtp/email"
REQUEST_TIMEOUT_SECONDS = 30


class EmailChannel:
    name = "email"

    def __init__(self, api_key: str, from_email: str):
        self._api_key = api_key
        self._from_email = from_email

    def applicable(self, user: User) -> bool:
        return bool(user.email)

    async def deliver(self, user: User, event: MatchEvent) -> None:
        payload = {
            "sender": {"email": self._from_email, "name": "APT"},
            "to": [{"email": user.email}],
            "subject": email_subject(event),
            "htmlContent": email_html(event),
        }
        timeout = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(BREVO_URL, json=payload, headers={"api-key": self._api_key}) as response:
                if response.status >= 300:
                    body = (await response.text())[:200]
                    raise RuntimeError(f"brevo returned {response.status}: {body}")
