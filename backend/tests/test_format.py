from apt.domain.events import MatchEvent
from apt.domain.models import Alert, AlertFilters, Listing
from apt.notify.format import email_html, email_subject, telegram_message


def make_event(kind="new", old_price=None, **listing_overrides):
    base = dict(
        source="yad2", source_id="a1", url="https://yad2.co.il/item/a1",
        city="חיפה", neighborhood="הדר", street="הרצל", price=5000,
        rooms=3.5, size_sqm=80, floor=2, has_mamad=True, has_elevator=None,
        description="דירה יפה <b>מאוד</b>",
    )
    base.update(listing_overrides)
    alert = Alert(id=1, user_id=1, name="חיפוש", filters=AlertFilters(), channels=["telegram"])
    return MatchEvent(kind=kind, listing=Listing(**base), alert=alert, old_price=old_price)


def test_telegram_new_message():
    text = telegram_message(make_event())
    assert "דירה חדשה" in text
    assert "₪5,000" in text
    assert "הרצל, הדר, חיפה" in text
    assert "3.5" in text and "80" in text
    assert 'ממ"ד: כן' in text
    assert "מעלית: לא ידוע" in text
    assert '<a href="https://yad2.co.il/item/a1">' in text
    assert "&lt;b&gt;מאוד&lt;/b&gt;" in text  # description escaped


def test_telegram_price_drop_message():
    text = telegram_message(make_event(kind="price_drop", old_price=6000, price=5000))
    assert "ירידת מחיר" in text
    assert "₪6,000" in text and "₪5,000" in text


def test_telegram_handles_missing_fields():
    text = telegram_message(make_event(price=None, rooms=None, size_sqm=None,
                                       floor=None, street=None, neighborhood=None,
                                       has_mamad=None, description=""))
    assert "חיפה" in text
    assert "לא ידוע" in text


def test_description_trimmed():
    text = telegram_message(make_event(description="א" * 500))
    assert "א" * 400 + "..." in text
    assert "א" * 401 not in text


def test_email_subject_and_html():
    event = make_event()
    assert "חיפה" in email_subject(event)
    html = email_html(event)
    assert 'dir="rtl"' in html
    assert "₪5,000" in html
    assert "https://yad2.co.il/item/a1" in html
