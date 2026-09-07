"""DataUpdateCoordinator that polls SCOPAY on a schedule."""

from __future__ import annotations

import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import ScopayApi, ScopayAuthError, ScopayConnectionError
from .const import CONF_ACCOUNT_ID, DOMAIN
from .parse import ScopayData

_LOGGER = logging.getLogger(__name__)

type ScopayConfigEntry = ConfigEntry[ScopayCoordinator]


class ScopayCoordinator(DataUpdateCoordinator[ScopayData]):
    """Fetches one pupil's SCOPAY data and shares it with the sensors."""

    def __init__(
        self, hass: HomeAssistant, entry: ScopayConfigEntry, update_interval: timedelta
    ) -> None:
        """Create a coordinator with its own cookie session for this pupil."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=update_interval,
            config_entry=entry,
        )
        # A dedicated session keeps this pupil's login cookie isolated from
        # other entries and from the rest of Home Assistant.
        self.session = async_create_clientsession(hass)
        self.api = ScopayApi(
            self.session,
            entry.data[CONF_USERNAME],
            entry.data[CONF_PASSWORD],
            entry.data.get(CONF_ACCOUNT_ID) or None,
        )

    async def _async_update_data(self) -> ScopayData:
        """Fetch fresh data, mapping auth/connection errors to HA's."""
        try:
            return await self.api.async_get_data()
        except ScopayAuthError as err:
            raise ConfigEntryAuthFailed(str(err)) from err
        except ScopayConnectionError as err:
            raise UpdateFailed(str(err)) from err
