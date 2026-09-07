"""Pure HTML parsing for SCOPAY pages.

No Home Assistant or network imports live here on purpose, so the parsing can
be unit-tested against saved HTML fixtures without a running instance or a live
account. Everything is derived from the server-rendered ``/products`` and
account-history HTML — SCOPAY exposes no JSON API.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

from bs4 import BeautifulSoup

# A product whose name matches this is treated as the cashless-catering balance.
_CATERING_RE = re.compile(r"cashless|catering|dinner|meal", re.IGNORECASE)
_OWED_RE = re.compile(r"Owed:\s*[-£]*\s*([\d.,]+)")
_IDS_RE = re.compile(r"/account/AccountHistory/(\d+)/(\d+)/")
_ALERTS_RE = re.compile(r"(\d+)")


@dataclass
class Product:
    """One line on the /products page (catering account or a trip/event)."""

    product_id: str
    name: str
    balance: float | None
    display: str
    owed: float | None = None


@dataclass
class Transaction:
    """One row of the payment-history table."""

    date: str
    description: str
    amount: float | None

    @property
    def on(self) -> date | None:
        """The completed date as a real date object, or None if unparseable."""
        return parse_date(self.date)


@dataclass
class ScopayData:
    """Everything one pupil's pages yield in a single refresh."""

    pupil: str | None = None
    school: str | None = None
    site_id: str | None = None
    account_id: str | None = None
    catering_balance: float | None = None
    catering_display: str | None = None
    alerts: int | None = None
    owed_total: float = 0.0
    products: list[Product] = field(default_factory=list)
    last_transaction: Transaction | None = None
    transactions: list[Transaction] = field(default_factory=list)


def parse_money(text: str | None) -> float | None:
    """Turn '£6.55', '-£3.45', '£1,234.56' into a float; None if not a number."""
    if not text:
        return None
    text = text.strip()
    negative = text.lstrip().startswith("-") or "-£" in text
    digits = re.sub(r"[^0-9.]", "", text.replace(",", ""))
    if digits in ("", "."):
        return None
    value = float(digits)
    return -value if negative else value


def is_logged_out(html: str, final_url: str = "") -> bool:
    """True when a page is really the login/logout page rather than app content."""
    if "/login" in final_url or "/logout" in final_url:
        return True
    return 'name="username"' in html and 'id="password"' in html


def login_failed(html: str) -> bool:
    """True when a POST /login response re-rendered the 'incorrect' error."""
    return "errorMessage1" in html or "email or password incorrect" in html


def parse_ids(html: str) -> tuple[str | None, str | None]:
    """Discover (site_id, account_id) from the 'Your info' history link."""
    match = _IDS_RE.search(html)
    return (match.group(1), match.group(2)) if match else (None, None)


def parse_products(html: str) -> list[Product]:
    """Every balance div on /products, paired with its name and any 'Owed'."""
    soup = BeautifulSoup(html, "html.parser")
    products: list[Product] = []
    for price in soup.select('[id^="priceDisplayNew"]'):
        product_id = price["id"].removeprefix("priceDisplayNew")
        display = price.get_text(strip=True)
        item = price.find_parent(class_="left_contentItem")
        title = item.select_one(".targetLinkTitle") if item else None
        name = title.get_text(strip=True) if title else product_id
        owed = None
        if item:
            owed_match = _OWED_RE.search(item.get_text(" ", strip=True))
            if owed_match:
                owed = parse_money(owed_match.group(1))
        products.append(
            Product(
                product_id=product_id,
                name=name,
                balance=parse_money(display),
                display=display,
                owed=owed,
            )
        )
    return products


def parse_last_transaction(html: str) -> Transaction | None:
    """First data row of the payment-history table (date / info / total)."""
    soup = BeautifulSoup(html, "html.parser")
    for table in soup.select("table"):
        header = table.find("tr")
        if not header or "Completed date" not in header.get_text():
            continue
        for row in table.select("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(("td", "th"))]
            if len(cells) >= 3 and cells[0]:
                return Transaction(
                    date=cells[0], description=cells[1], amount=parse_money(cells[2])
                )
    return None


# SCOPAY writes UK-style month abbreviations ("4 Sept 2026"), which are not all
# strptime's %b ("Sept" not "Sep", "June"/"July" not "Jun"/"Jul"), so map explicitly.
_MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "june": 6,
    "jul": 7,
    "july": 7,
    "aug": 8,
    "sep": 9,
    "sept": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_DATE_RE = re.compile(r"(\d{1,2})\s+([A-Za-z]+)\.?\s+(\d{4})")


def parse_date(text: str | None) -> date | None:
    """'4 Sept 2026' -> date(2026, 9, 4); None if unparseable."""
    if not text:
        return None
    match = _DATE_RE.search(text)
    if not match:
        return None
    month = _MONTHS.get(match.group(2).lower().rstrip("."))
    if not month:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def parse_transactions(html: str) -> list[Transaction]:
    """Every row of the payment-history table, newest first.

    The account-history page is already fetched for ``last_transaction``; this
    reads the whole table so spend can be aggregated over real date ranges
    instead of having to accumulate forward from the moment HA was set up.
    """
    soup = BeautifulSoup(html, "html.parser")
    rows: list[Transaction] = []
    for table in soup.select("table"):
        header = table.find("tr")
        if not header or "Completed date" not in header.get_text():
            continue
        for row in table.select("tr")[1:]:
            cells = [c.get_text(" ", strip=True) for c in row.find_all(("td", "th"))]
            if len(cells) >= 3 and cells[0]:
                rows.append(
                    Transaction(
                        date=cells[0],
                        description=cells[1],
                        amount=parse_money(cells[2]),
                    )
                )
        break
    return rows


def _clean(node) -> str | None:
    """Collapse all runs of whitespace in an element's text to single spaces."""
    if node is None:
        return None
    return " ".join(node.get_text(" ", strip=True).split()) or None


def parse_pupil(html: str) -> tuple[str | None, str | None]:
    """(pupil name, school name) from the student bar."""
    soup = BeautifulSoup(html, "html.parser")
    return (
        _clean(soup.select_one(".studentBar_name")),
        _clean(soup.select_one(".studentBar_school")),
    )


def parse_alerts(html: str) -> int | None:
    """Number shown on the Alerts menu item, e.g. 'Alerts 0' -> 0."""
    soup = BeautifulSoup(html, "html.parser")
    link = soup.select_one('a[href="/alerts"]')
    if not link:
        return None
    match = _ALERTS_RE.search(link.get_text(" ", strip=True))
    return int(match.group(1)) if match else None


def build_data(products_html: str, history_html: str | None = None) -> ScopayData:
    """Assemble a :class:`ScopayData` from the raw page HTML."""
    products = parse_products(products_html)
    pupil, school = parse_pupil(products_html)
    site_id, account_id = parse_ids(products_html)

    catering = next((p for p in products if _CATERING_RE.search(p.name)), None)
    owed_total = round(sum(p.owed for p in products if p.owed), 2)

    return ScopayData(
        pupil=pupil,
        school=school,
        site_id=site_id,
        account_id=account_id,
        catering_balance=catering.balance if catering else None,
        catering_display=catering.display if catering else None,
        alerts=parse_alerts(products_html),
        owed_total=owed_total,
        products=products,
        last_transaction=parse_last_transaction(history_html) if history_html else None,
        transactions=parse_transactions(history_html) if history_html else [],
    )
