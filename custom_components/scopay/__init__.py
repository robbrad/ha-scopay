"""The SCOPAY (Tucasi school payments) integration."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .const import CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES
from .coordinator import ScopayConfigEntry, ScopayCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(hass: HomeAssistant, entry: ScopayConfigEntry) -> bool:
    """Set up SCOPAY from a config entry."""
    minutes = entry.options.get(
        CONF_SCAN_MINUTES, entry.data.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES)
    )
    coordinator = ScopayCoordinator(hass, entry, timedelta(minutes=minutes))
    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ScopayConfigEntry) -> bool:
    """Unload a config entry.

    The cookie session is deliberately not closed: Home Assistant patches
    close() on sessions it creates and warns if an integration calls it,
    because HA already tears them down at shutdown.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: ScopayConfigEntry) -> None:
    """Reload the entry when its options (e.g. scan interval) change."""
    await hass.config_entries.async_reload(entry.entry_id)
