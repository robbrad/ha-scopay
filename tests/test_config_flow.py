"""Tests for the SCOPAY config and options flows."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant import config_entries
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.scopay.api import ScopayAuthError, ScopayConnectionError
from custom_components.scopay.const import CONF_SCAN_MINUTES, DOMAIN
from custom_components.scopay.parse import ScopayData

USER_INPUT = {
    CONF_USERNAME: "parent@example.com",
    CONF_PASSWORD: "hunter2",
    CONF_SCAN_MINUTES: 60,
}

DATA = ScopayData(pupil="Alex Example", account_id="56789", catering_balance=6.55)


@pytest.fixture
def mock_validate():
    """Patch the login-and-fetch used by the flow."""
    with patch(
        "custom_components.scopay.config_flow._validate",
        new=AsyncMock(return_value=DATA),
    ) as mocked:
        yield mocked


async def test_user_flow_creates_entry(hass: HomeAssistant, mock_validate):
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # The pupil's name, not the parent's email, titles the entry.
    assert result["title"] == "Alex Example"
    assert result["data"][CONF_USERNAME] == "parent@example.com"


@pytest.mark.parametrize(
    ("error", "expected"),
    [
        (ScopayAuthError("nope"), "invalid_auth"),
        (ScopayConnectionError("down"), "cannot_connect"),
    ],
)
async def test_user_flow_errors_are_recoverable(
    hass: HomeAssistant, mock_validate, error, expected
):
    mock_validate.side_effect = error
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": expected}

    # Correcting the problem lets the same flow finish.
    mock_validate.side_effect = None
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_duplicate_pupil_is_aborted(hass: HomeAssistant, mock_validate):
    MockConfigEntry(
        domain=DOMAIN,
        unique_id="parent@example.com:56789",
        data=USER_INPUT,
    ).add_to_hass(hass)

    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], USER_INPUT
    )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reauth_updates_the_password(hass: HomeAssistant, mock_validate):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="parent@example.com:56789", data=USER_INPUT
    )
    entry.add_to_hass(hass)

    result = await entry.start_reauth_flow(hass)
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_PASSWORD: "new-password"}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_PASSWORD] == "new-password"


async def test_options_flow_sets_the_interval(hass: HomeAssistant, mock_validate):
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id="parent@example.com:56789", data=USER_INPUT
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["step_id"] == "init"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_MINUTES: 180}
    )
    await hass.async_block_till_done()

    assert result["type"] is FlowResultType.CREATE_ENTRY
    # Stored as an int, not the float the number selector hands back.
    assert result["data"][CONF_SCAN_MINUTES] == 180
    assert isinstance(result["data"][CONF_SCAN_MINUTES], int)
