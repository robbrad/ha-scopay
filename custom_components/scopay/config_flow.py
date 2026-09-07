"""Config and options flow for SCOPAY."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_PASSWORD, CONF_USERNAME
from homeassistant.core import callback
from homeassistant.helpers.aiohttp_client import async_create_clientsession
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .api import ScopayApi, ScopayAuthError, ScopayConnectionError
from .const import (
    CONF_ACCOUNT_ID,
    CONF_SCAN_MINUTES,
    DEFAULT_SCAN_MINUTES,
    DOMAIN,
    MAX_SCAN_MINUTES,
    MIN_SCAN_MINUTES,
)
from .coordinator import ScopayConfigEntry

STEP_USER_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_USERNAME): TextSelector(
            TextSelectorConfig(type=TextSelectorType.EMAIL)
        ),
        vol.Required(CONF_PASSWORD): TextSelector(
            TextSelectorConfig(type=TextSelectorType.PASSWORD)
        ),
        vol.Optional(CONF_ACCOUNT_ID): TextSelector(),
        vol.Optional(CONF_SCAN_MINUTES, default=DEFAULT_SCAN_MINUTES): NumberSelector(
            NumberSelectorConfig(
                min=MIN_SCAN_MINUTES,
                max=MAX_SCAN_MINUTES,
                step=1,
                mode=NumberSelectorMode.BOX,
                unit_of_measurement="min",
            )
        ),
    }
)


async def _validate(hass, data: Mapping[str, Any]):
    """Try a login + fetch; return the scraped ScopayData or raise."""
    # A dedicated session keeps this login's cookies out of the shared one.
    # Home Assistant owns its lifecycle, so it is not closed here.
    api = ScopayApi(
        async_create_clientsession(hass),
        data[CONF_USERNAME],
        data[CONF_PASSWORD],
        data.get(CONF_ACCOUNT_ID) or None,
    )
    return await api.async_get_data()


class ScopayConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle the SCOPAY config flow."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Collect credentials and verify them against SCOPAY."""
        errors: dict[str, str] = {}
        if user_input is not None:
            if CONF_SCAN_MINUTES in user_input:
                user_input[CONF_SCAN_MINUTES] = int(user_input[CONF_SCAN_MINUTES])
            try:
                data = await _validate(self.hass, user_input)
            except ScopayAuthError:
                errors["base"] = "invalid_auth"
            except ScopayConnectionError:
                errors["base"] = "cannot_connect"
            else:
                await self.async_set_unique_id(
                    f"{user_input[CONF_USERNAME].lower()}:{data.account_id}"
                )
                self._abort_if_unique_id_configured()
                return self.async_create_entry(
                    title=data.pupil or user_input[CONF_USERNAME], data=user_input
                )

        return self.async_show_form(
            step_id="user", data_schema=STEP_USER_SCHEMA, errors=errors
        )

    async def async_step_reauth(
        self, entry_data: Mapping[str, Any]
    ) -> ConfigFlowResult:
        """Start reauth when SCOPAY rejects the stored credentials."""
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for a new password and update the entry."""
        errors: dict[str, str] = {}
        reauth_entry = self._get_reauth_entry()
        if user_input is not None:
            merged = {**reauth_entry.data, CONF_PASSWORD: user_input[CONF_PASSWORD]}
            try:
                await _validate(self.hass, merged)
            except ScopayAuthError:
                errors["base"] = "invalid_auth"
            except ScopayConnectionError:
                errors["base"] = "cannot_connect"
            else:
                return self.async_update_reload_and_abort(reauth_entry, data=merged)

        return self.async_show_form(
            step_id="reauth_confirm",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PASSWORD): TextSelector(
                        TextSelectorConfig(type=TextSelectorType.PASSWORD)
                    )
                }
            ),
            description_placeholders={CONF_USERNAME: reauth_entry.data[CONF_USERNAME]},
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ScopayConfigEntry) -> ScopayOptionsFlow:
        """Return the options flow (poll interval)."""
        return ScopayOptionsFlow()


class ScopayOptionsFlow(OptionsFlow):
    """Let the user change how often SCOPAY is polled."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show and store the poll interval."""
        if user_input is not None:
            user_input[CONF_SCAN_MINUTES] = int(user_input[CONF_SCAN_MINUTES])
            return self.async_create_entry(data=user_input)

        current = self.config_entry.options.get(
            CONF_SCAN_MINUTES,
            self.config_entry.data.get(CONF_SCAN_MINUTES, DEFAULT_SCAN_MINUTES),
        )
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SCAN_MINUTES, default=current): NumberSelector(
                        NumberSelectorConfig(
                            min=MIN_SCAN_MINUTES,
                            max=MAX_SCAN_MINUTES,
                            step=1,
                            mode=NumberSelectorMode.BOX,
                            unit_of_measurement="min",
                        )
                    )
                }
            ),
        )
