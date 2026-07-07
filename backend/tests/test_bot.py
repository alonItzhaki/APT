from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from apt.bot import help_command, matches, pause, resume, start
from apt.domain.models import AlertFilters, Listing, Location
from apt.repo.alerts import AlertRepo
from apt.repo.link_tokens import LinkTokenRepo
from apt.repo.listings import ListingRepo
from apt.repo.users import UserRepo

NOW = datetime(2026, 7, 7, 12, 0, tzinfo=timezone.utc)
SITE = "https://apt.example.com"


def make_update(chat_id=42, args=None):
    message = SimpleNamespace(chat_id=chat_id, reply_text=AsyncMock())
    update = SimpleNamespace(effective_message=message, effective_chat=SimpleNamespace(id=chat_id))
    context = SimpleNamespace(
        args=args or [],
        bot_data={"conn": None, "site_url": SITE, "now_fn": lambda: NOW},
    )
    return update, context


def reply_text(update):
    return update.effective_message.reply_text.call_args.args[0]


def make_user(conn, chat_id=None):
    user = UserRepo(conn).upsert_google_user("g-1", "a@b.com", NOW)
    if chat_id is not None:
        UserRepo(conn).set_telegram_chat(user.id, chat_id)
    return UserRepo(conn).get(user.id)


async def test_start_without_token_shows_welcome(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await start(update, context)
    assert SITE in reply_text(update)


async def test_start_with_valid_token_links_account(conn):
    user = make_user(conn)
    LinkTokenRepo(conn).create("tok-1", user.id, NOW)
    update, context = make_update(chat_id=42, args=["tok-1"])
    context.bot_data["conn"] = conn
    await start(update, context)
    assert UserRepo(conn).get(user.id).telegram_chat_id == 42
    assert "בהצלחה" in reply_text(update)


async def test_start_with_bad_token_shows_error(conn):
    update, context = make_update(args=["nope"])
    context.bot_data["conn"] = conn
    await start(update, context)
    assert UserRepo(conn).get_by_telegram_chat(42) is None
    assert SITE in reply_text(update)


async def test_matches_unlinked_prompts_linking(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await matches(update, context)
    assert SITE in reply_text(update)


async def test_matches_lists_listings_per_alert(conn):
    user = make_user(conn, chat_id=42)
    AlertRepo(conn).create(user.id, "חיפה עד 6000",
                           AlertFilters(locations=[Location(city="חיפה")], max_price=6000),
                           ["telegram"], NOW)
    ListingRepo(conn).upsert(
        Listing(source="yad2", source_id="a1", url="https://e.com/a1", city="חיפה", price=5000), NOW)
    update, context = make_update(chat_id=42)
    context.bot_data["conn"] = conn
    await matches(update, context)
    text = reply_text(update)
    assert "חיפה עד 6000" in text
    assert "₪5,000" in text


async def test_pause_and_resume_toggle_all_alerts(conn):
    user = make_user(conn, chat_id=42)
    repo = AlertRepo(conn)
    alert = repo.create(user.id, "x", AlertFilters(), ["telegram"], NOW)
    update, context = make_update(chat_id=42)
    context.bot_data["conn"] = conn
    await pause(update, context)
    assert repo.get(alert.id).active is False
    await resume(update, context)
    assert repo.get(alert.id).active is True


async def test_help_shows_commands(conn):
    update, context = make_update()
    context.bot_data["conn"] = conn
    await help_command(update, context)
    text = reply_text(update)
    assert "/matches" in text
