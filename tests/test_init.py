"""Setup, reload and unload of a SCOPAY config entry."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scopay.api import ScopayAuthError, ScopayConnectionError
from custom_components.scopay.const import CONF_SCAN_MINUTES, DOMAIN
from custom_components.scopay.parse import Product, ScopayData, Transaction

DATA = ScopayData(
    pupil="Alex Example",
    school="Example High School",
    site_id="1234",
    account_id="56789",
    catering_balance=6.55,
    catering_display="£6.55",
    alerts=2,
    owed_total=12.0,
    products=[Product("111", "Cashless Catering", 6.55, "£6.55")],
    last_transaction=Transaction("4 Sept 2026", "Cashless Catering", -2.40),
    transactions=[Transaction("4 Sept 2026", "Cashless Catering", -2.40)],
)


@pytest.fixture
def entry(hass: HomeAssistant) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id="parent@example.com:56789",
        data={
            CONF_USERNAME: "parent@example.com",
            CONF_PASSWORD: "hunter2",
            CONF_SCAN_MINUTES: 60,
        },
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
def mock_api():
    with patch(
        "custom_components.scopay.coordinator.ScopayApi.async_get_data",
        new=AsyncMock(return_value=DATA),
    ) as mocked:
        yield mocked


async def test_setup_and_unload(hass: HomeAssistant, entry, mock_api):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED

    state = hass.states.get("sensor.scopay_alex_example_cashless_catering_balance")
    assert state is not None
    assert state.state == "6.55"

    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_all_sensors_are_created(hass: HomeAssistant, entry, mock_api):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    created = [
        state.entity_id
        for state in hass.states.async_all("sensor")
        if state.entity_id.startswith("sensor.scopay_")
    ]
    assert len(created) == 8


async def test_setup_retries_when_scopay_is_unreachable(
    hass: HomeAssistant, entry, mock_api
):
    mock_api.side_effect = ScopayConnectionError("down")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_RETRY


async def test_bad_credentials_trigger_reauth(hass: HomeAssistant, entry, mock_api):
    mock_api.side_effect = ScopayAuthError("nope")
    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.SETUP_ERROR

    assert any(
        flow["context"]["source"] == "reauth"
        for flow in hass.config_entries.flow.async_progress()
    )


async def test_changing_options_reloads_the_entry(hass: HomeAssistant, entry, mock_api):
    await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    hass.config_entries.async_update_entry(entry, options={CONF_SCAN_MINUTES: 120})
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.LOADED
    assert entry.runtime_data.update_interval.total_seconds() == 120 * 60
