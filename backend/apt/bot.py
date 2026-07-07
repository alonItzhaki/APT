import html
import logging
import sqlite3
from datetime import datetime, timezone
from typing import Callable

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from apt.repo.alerts import AlertRepo
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.listings import ListingRepo
from apt.repo.users import UserRepo

logger = logging.getLogger(__name__)

WELCOME = (
    "🏠 <b>APT - חיפוש דירות להשכרה</b>\n"
    "הבוט שולח התראות על דירות חדשות שמתאימות לחיפושים שלך.\n\n"
    "פקודות:\n"
    "/matches - הדירות האחרונות שמתאימות לחיפושים שלך\n"
    "/pause - השהיית כל ההתראות\n"
    "/resume - חידוש ההתראות\n"
    "/help - ההודעה הזאת\n\n"
    'יצירת חיפושים ועריכתם באתר: <a href="{site}">{site}</a>'
)
LINK_FIRST = (
    'כדי להשתמש בבוט צריך קודם לקשר את החשבון מהאתר: <a href="{site}">{site}</a>'
)


def _tools(context: ContextTypes.DEFAULT_TYPE):
    data = context.bot_data
    now_fn = data.get("now_fn") or (lambda: datetime.now(timezone.utc))
    return data["conn"], data["site_url"], now_fn


async def _reply(update: Update, text: str) -> None:
    await update.effective_message.reply_text(text, parse_mode="HTML")


def _linked_user(conn: sqlite3.Connection, update: Update):
    return UserRepo(conn).get_by_telegram_chat(update.effective_message.chat_id)


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, site_url, now_fn = _tools(context)
    if context.args:
        user_id = LinkTokenRepo(conn).consume(context.args[0], now_fn())
        if user_id is not None:
            UserRepo(conn).set_telegram_chat(user_id, update.effective_message.chat_id)
            await _reply(update, "✅ החשבון קושר בהצלחה! מעכשיו תקבלו כאן התראות על דירות חדשות.")
            return
        await _reply(update, "הקישור פג תוקף או שגוי. " + LINK_FIRST.format(site=site_url))
        return
    await _reply(update, WELCOME.format(site=site_url))


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    _, site_url, _ = _tools(context)
    await _reply(update, WELCOME.format(site=site_url))


def _listing_line(listing) -> str:
    price = f"₪{listing.price:,}" if listing.price is not None else "מחיר לא ידוע"
    parts = [part for part in (listing.street, listing.neighborhood, listing.city) if part]
    location = html.escape(", ".join(dict.fromkeys(parts)), quote=False)
    url = html.escape(listing.url, quote=True)
    return f'• {price} - {location} - <a href="{url}">למודעה</a>'


async def matches(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conn, site_url, _ = _tools(context)
    user = _linked_user(conn, update)
    if user is None:
        await _reply(update, LINK_FIRST.format(site=site_url))
        return
    alerts = [alert for alert in AlertRepo(conn).list_for_user(user.id) if alert.active]
    if not alerts:
        await _reply(update, f'אין לך עדיין חיפושים. אפשר ליצור באתר: <a href="{site_url}">{site_url}</a>')
        return
    listings_repo = ListingRepo(conn)
    for alert in alerts:
        found = listings_repo.search(alert.filters, limit=3)
        name = html.escape(alert.name, quote=False)
        if found:
            lines = "\n".join(_listing_line(listing) for listing in found)
            await _reply(update, f"<b>{name}</b>\n{lines}")
        else:
            await _reply(update, f"<b>{name}</b>\nאין עדיין דירות מתאימות.")


async def _set_all_alerts(update: Update, context: ContextTypes.DEFAULT_TYPE, active: bool) -> None:
    conn, site_url, _ = _tools(context)
    user = _linked_user(conn, update)
    if user is None:
        await _reply(update, LINK_FIRST.format(site=site_url))
        return
    repo = AlertRepo(conn)
    alerts = repo.list_for_user(user.id)
    for alert in alerts:
        repo.set_active(alert.id, active)
    verb = "חודשו" if active else "הושהו"
    await _reply(update, f"{len(alerts)} חיפושים {verb}.")


async def pause(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_all_alerts(update, context, False)


async def resume(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _set_all_alerts(update, context, True)


def build_application(
    token: str,
    conn: sqlite3.Connection,
    site_url: str,
    now_fn: Callable[[], datetime] | None = None,
) -> Application:
    application = Application.builder().token(token).build()
    application.bot_data.update({"conn": conn, "site_url": site_url, "now_fn": now_fn})
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("matches", matches))
    application.add_handler(CommandHandler("pause", pause))
    application.add_handler(CommandHandler("resume", resume))
    return application
