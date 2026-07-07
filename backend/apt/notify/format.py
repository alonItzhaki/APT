import html

from apt.domain.events import MatchEvent
from apt.domain.models import Listing

MAX_DESCRIPTION_CHARS = 400
UNKNOWN = "לא ידוע"


def _escape(value: object) -> str:
    return html.escape(str(value), quote=False)


def _price(value: int | None) -> str:
    return f"₪{value:,}" if value is not None else UNKNOWN


def _location(listing: Listing) -> str:
    parts = [part for part in (listing.street, listing.neighborhood, listing.city) if part]
    return ", ".join(dict.fromkeys(parts))


def _yes_no(value: bool | None) -> str:
    if value is True:
        return "כן"
    if value is False:
        return "לא"
    return UNKNOWN


def _maybe(value: object) -> str:
    return _escape(value) if value is not None else UNKNOWN


def _description(listing: Listing) -> str:
    text = listing.description
    if len(text) > MAX_DESCRIPTION_CHARS:
        text = text[:MAX_DESCRIPTION_CHARS].rstrip() + "..."
    return _escape(text)


def _header(event: MatchEvent) -> str:
    if event.kind == "price_drop":
        return f"🔻 ירידת מחיר! {_price(event.old_price)} ← {_price(event.listing.price)}"
    return "🏠 דירה חדשה!"


def _lines(event: MatchEvent) -> list[str]:
    listing = event.listing
    lines = [
        f"<b>{_header(event)}</b>",
        f"מחיר: {_price(listing.price)}",
        f"מיקום: {_escape(_location(listing))}",
        f"חדרים: {_maybe(listing.rooms)} | גודל: {_maybe(listing.size_sqm)} מ\"ר | קומה: {_maybe(listing.floor)}",
        f'ממ"ד: {_yes_no(listing.has_mamad)} | מעלית: {_yes_no(listing.has_elevator)}',
    ]
    if listing.description:
        lines.append(_description(listing))
    lines.append(f'<a href="{html.escape(listing.url, quote=True)}">לצפייה במודעה</a>')
    return lines


def telegram_message(event: MatchEvent) -> str:
    return "\n".join(_lines(event))


def email_subject(event: MatchEvent) -> str:
    listing = event.listing
    prefix = "ירידת מחיר" if event.kind == "price_drop" else "דירה חדשה"
    rooms = f"{listing.rooms} חד' " if listing.rooms is not None else ""
    return f"{prefix}: {rooms}ב{listing.city} - {_price(listing.price)}"


def email_html(event: MatchEvent) -> str:
    body = "<br>\n".join(_lines(event))
    return f'<!DOCTYPE html>\n<html dir="rtl" lang="he"><body>\n{body}\n</body></html>'
