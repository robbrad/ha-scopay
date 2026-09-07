"""Tests for the SCOPAY client: form login, session reuse, pupil switching."""

import re

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.scopay.api import (
    ScopayApi,
    ScopayAuthError,
    ScopayConnectionError,
)
from custom_components.scopay.const import BASE_URL

PRODUCTS_URL = f"{BASE_URL}/products"
LOGIN_URL = f"{BASE_URL}/login"
HISTORY_URL = f"{BASE_URL}/account/AccountHistory/1234/56789/-1"
PUPIL_URL = re.compile(rf"^{re.escape(BASE_URL)}/PupilChange/\d+$")


@pytest.fixture
async def session():
    async with aiohttp.ClientSession() as session:
        yield session


@pytest.fixture
def mock_http():
    with aioresponses() as mocked:
        yield mocked


def _requested(mock_http, method: str) -> list[str]:
    """Every path requested with `method`, in order."""
    return [
        str(key[1].path)
        for key, calls in mock_http.requests.items()
        for _ in calls
        if key[0] == method
    ]


async def test_get_data_when_already_signed_in(
    session, mock_http, products_html, history_html
):
    api = ScopayApi(session, "parent@example.com", "hunter2")
    mock_http.get(PRODUCTS_URL, body=products_html)
    mock_http.get(HISTORY_URL, body=history_html)

    data = await api.async_get_data()

    assert data.pupil == "Alex Example"
    assert data.catering_balance == 6.55
    assert data.last_transaction.amount == -2.40
    # A live session must not re-post the password.
    assert "POST" not in {key[0] for key in mock_http.requests}


async def test_expired_session_logs_in_again(
    session, mock_http, products_html, history_html, login_html
):
    api = ScopayApi(session, "parent@example.com", "hunter2")
    # First /products hands back the login page, so the client signs in.
    mock_http.get(PRODUCTS_URL, body=login_html)
    mock_http.get(LOGIN_URL, body="<html></html>")
    # A good login redirects away from /login; the client reads success from
    # the final URL, so a 200 that stayed on /login would mean failure.
    mock_http.post(LOGIN_URL, status=302, headers={"Location": PRODUCTS_URL})
    # Serves both the redirect target and the explicit re-fetch that follows.
    mock_http.get(PRODUCTS_URL, body=products_html, repeat=True)
    mock_http.get(HISTORY_URL, body=history_html)

    data = await api.async_get_data()

    assert data.pupil == "Alex Example"
    assert "POST" in {key[0] for key in mock_http.requests}


async def test_bad_credentials_raise_auth_error(session, mock_http, login_html):
    api = ScopayApi(session, "parent@example.com", "wrong")
    mock_http.get(PRODUCTS_URL, body=login_html)
    mock_http.get(LOGIN_URL, body="<html></html>")
    mock_http.post(LOGIN_URL, body=login_html)

    with pytest.raises(ScopayAuthError):
        await api.async_get_data()


async def test_still_logged_out_after_login_raises(session, mock_http, login_html):
    api = ScopayApi(session, "parent@example.com", "hunter2")
    mock_http.get(PRODUCTS_URL, body=login_html)
    mock_http.get(LOGIN_URL, body="<html></html>")
    mock_http.post(LOGIN_URL, body="<html>ok</html>")
    mock_http.get(PRODUCTS_URL, body=login_html)

    with pytest.raises(ScopayAuthError):
        await api.async_get_data()


async def test_network_failure_raises_connection_error(session, mock_http):
    api = ScopayApi(session, "parent@example.com", "hunter2")
    mock_http.get(PRODUCTS_URL, exception=aiohttp.ClientError("boom"))

    with pytest.raises(ScopayConnectionError):
        await api.async_get_data()


async def test_wrong_pupil_triggers_a_switch(
    session, mock_http, products_html, history_html
):
    """A live session pointing at another child must be switched over."""
    # The fixture page belongs to account 56789; this entry wants 99999.
    api = ScopayApi(session, "parent@example.com", "hunter2", account_id="99999")
    mock_http.get(PRODUCTS_URL, body=products_html)
    mock_http.get(PUPIL_URL, body="<html>switched</html>")
    mock_http.get(PRODUCTS_URL, body=products_html)
    mock_http.get(HISTORY_URL, body=history_html)

    await api.async_get_data()

    assert "/PupilChange/99999" in _requested(mock_http, "GET")


async def test_matching_pupil_is_not_switched(
    session, mock_http, products_html, history_html
):
    api = ScopayApi(session, "parent@example.com", "hunter2", account_id="56789")
    mock_http.get(PRODUCTS_URL, body=products_html)
    mock_http.get(HISTORY_URL, body=history_html)

    await api.async_get_data()

    assert not any(
        path.startswith("/PupilChange") for path in _requested(mock_http, "GET")
    )


async def test_history_is_skipped_when_ids_are_missing(session, mock_http):
    api = ScopayApi(session, "parent@example.com", "hunter2")
    mock_http.get(
        PRODUCTS_URL,
        body='<div class="left_contentItem">'
        '<span class="targetLinkTitle">Cashless Catering</span>'
        '<div id="priceDisplayNew1">£1.00</div></div>',
    )

    data = await api.async_get_data()

    assert data.last_transaction is None
    assert data.catering_balance == 1.00
