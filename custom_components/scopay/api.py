"""Async SCOPAY client: form login, session cookie, HTML scrape.

SCOPAY (Tucasi) exposes no JSON/token API and no HTTP Basic Auth — the only way
in is the same form login a browser uses (``POST /login`` with a ``SESSION``
cookie), after which every page is server-rendered HTML. This client owns that
flow and hands raw HTML to the pure functions in :mod:`parse`.
"""

from __future__ import annotations

import logging

import aiohttp

from . import parse
from .const import BASE_URL

_LOGGER = logging.getLogger(__name__)


class ScopayAuthError(Exception):
    """Credentials were rejected by SCOPAY."""


class ScopayConnectionError(Exception):
    """SCOPAY could not be reached."""


class ScopayApi:
    """Talks to SCOPAY for a single pupil, reusing one cookie session."""

    def __init__(
        self,
        session: aiohttp.ClientSession,
        username: str,
        password: str,
        account_id: str | None = None,
    ) -> None:
        """Store the aiohttp session (its cookie jar carries the SCOPAY login)."""
        self._session = session
        self._username = username
        self._password = password
        self._account_id = account_id

    async def async_login(self) -> None:
        """Establish an authenticated SESSION cookie or raise ScopayAuthError."""
        try:
            async with self._session.get(f"{BASE_URL}/login"):
                pass
            async with self._session.post(
                f"{BASE_URL}/login",
                data={"username": self._username, "password": self._password},
            ) as resp:
                text = await resp.text()
                final_url = str(resp.url)
        except aiohttp.ClientError as err:
            raise ScopayConnectionError(str(err)) from err

        if parse.login_failed(text) or parse.is_logged_out(text, final_url):
            raise ScopayAuthError("email or password incorrect")

    async def _fetch(self, path: str) -> tuple[str, str]:
        """GET a path within SCOPAY, returning (html, final_url)."""
        try:
            async with self._session.get(f"{BASE_URL}{path}") as resp:
                return await resp.text(), str(resp.url)
        except aiohttp.ClientError as err:
            raise ScopayConnectionError(str(err)) from err

    async def async_get_data(self) -> parse.ScopayData:
        """Return one refresh of balances, alerts and the latest transaction."""
        html, _url = await self._products_when_authenticated()

        site_id, account_id = parse.parse_ids(html)
        history_html: str | None = None
        if site_id and account_id:
            history_html, _ = await self._fetch(
                f"/account/AccountHistory/{site_id}/{account_id}/-1"
            )
        return parse.build_data(html, history_html)

    async def _products_when_authenticated(self) -> tuple[str, str]:
        """Fetch /products, logging in (and selecting the pupil) if needed."""
        html, url = await self._fetch("/products")
        if parse.is_logged_out(html, url):
            await self.async_login()
            await self._select_pupil()
            html, url = await self._fetch("/products")
            if parse.is_logged_out(html, url):
                raise ScopayAuthError("still logged out after re-login")
        elif self._account_id:
            # Session still valid, but make sure it is pointing at our pupil.
            _, current = parse.parse_ids(html)
            if current != self._account_id:
                await self._select_pupil()
                html, url = await self._fetch("/products")
        return html, url

    async def _select_pupil(self) -> None:
        """Switch the session to the configured pupil (multi-child accounts).

        Mirrors SCOPAY's own ``changePupil()``: ``GET /PupilChange/{accountId}``.
        No-op for single-pupil accounts, where ``account_id`` is left unset.
        """
        if self._account_id:
            await self._fetch(f"/PupilChange/{self._account_id}")
