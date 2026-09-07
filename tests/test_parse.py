"""Tests for the pure SCOPAY HTML parsing.

These need no Home Assistant and no account: every input is a saved fixture.
"""

from datetime import date

import pytest

from custom_components.scopay import parse


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("£6.55", 6.55),
        ("-£3.45", -3.45),
        ("£1,234.56", 1234.56),
        ("  £0.00  ", 0.0),
        ("-", None),
        ("", None),
        (None, None),
        ("no digits here", None),
    ],
)
def test_parse_money(text, expected):
    assert parse.parse_money(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("4 Sept 2026", date(2026, 9, 4)),
        ("1 June 2026", date(2026, 6, 1)),
        ("12 Jul 2025", date(2025, 7, 12)),
        ("31 Dec. 2024", date(2024, 12, 31)),
        ("30 Feb 2026", None),  # real-looking but not a real date
        ("4 Smarch 2026", None),
        ("not a date", None),
        (None, None),
    ],
)
def test_parse_date(text, expected):
    assert parse.parse_date(text) == expected


def test_is_logged_out_by_url(products_html):
    assert parse.is_logged_out(products_html, "https://www.scopay.com/login")
    assert not parse.is_logged_out(products_html, "https://www.scopay.com/products")


def test_is_logged_out_by_form(login_html):
    assert parse.is_logged_out(login_html, "https://www.scopay.com/products")


def test_login_failed(login_html, products_html):
    assert parse.login_failed(login_html)
    assert not parse.login_failed(products_html)


def test_parse_ids(products_html):
    assert parse.parse_ids(products_html) == ("1234", "56789")


def test_parse_ids_missing():
    assert parse.parse_ids("<html></html>") == (None, None)


def test_parse_products(products_html):
    products = parse.parse_products(products_html)
    assert [p.product_id for p in products] == ["111", "222", "333"]

    catering, trip, lessons = products
    assert catering.name == "Cashless Catering"
    assert catering.balance == 6.55
    assert catering.owed is None
    assert trip.balance == -12.00
    assert trip.owed == 12.00
    assert lessons.owed == 1234.56


def test_parse_pupil(products_html):
    # The fixture pads the name with stray whitespace, as SCOPAY does.
    assert parse.parse_pupil(products_html) == (
        "Alex Example",
        "Example High School",
    )


def test_parse_alerts(products_html):
    assert parse.parse_alerts(products_html) == 2
    assert parse.parse_alerts("<html></html>") is None


def test_parse_last_transaction(history_html):
    txn = parse.parse_last_transaction(history_html)
    assert txn.date == "4 Sept 2026"
    assert txn.description == "Cashless Catering"
    assert txn.amount == -2.40
    assert txn.on == date(2026, 9, 4)


def test_parse_transactions_skips_blank_rows(history_html):
    rows = parse.parse_transactions(history_html)
    assert len(rows) == 4
    assert [r.amount for r in rows] == [-2.40, -3.10, 20.00, -2.00]


def test_parse_transactions_without_table():
    assert parse.parse_transactions("<html><table></table></html>") == []


def test_build_data(products_html, history_html):
    data = parse.build_data(products_html, history_html)

    assert data.pupil == "Alex Example"
    assert data.school == "Example High School"
    assert (data.site_id, data.account_id) == ("1234", "56789")
    assert data.catering_balance == 6.55
    assert data.catering_display == "£6.55"
    assert data.alerts == 2
    # Only the two products carrying an "Owed:" line contribute.
    assert data.owed_total == 1246.56
    assert len(data.products) == 3
    assert data.last_transaction.amount == -2.40
    assert len(data.transactions) == 4


def test_build_data_without_history(products_html):
    data = parse.build_data(products_html)
    assert data.last_transaction is None
    assert data.transactions == []


def test_build_data_no_catering_product():
    html = """
      <div class="left_contentItem">
        <span class="targetLinkTitle">School Trip</span>
        <div id="priceDisplayNew1">£5.00</div>
      </div>
    """
    data = parse.build_data(html)
    assert data.catering_balance is None
    assert data.catering_display is None
    assert data.owed_total == 0.0
