"""Config flow for the Vanderbilt SPC (EDP) integration."""

from __future__ import annotations

import asyncio
import re
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers.selector import (
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    TextSelector,
    TextSelectorConfig,
    TextSelectorType,
)

from .const import (
    CONF_AREA_REFRESH_INTERVAL,
    CONF_AUX_REFRESH_INTERVAL,
    CONF_BIND,
    CONF_ENCRYPTION_KEY,
    CONF_IDLE_TIMEOUT,
    CONF_PORT,
    CONF_RECEIVER_ID,
    DEFAULT_AREA_REFRESH_INTERVAL,
    DEFAULT_AUX_REFRESH_INTERVAL,
    DEFAULT_BIND,
    DEFAULT_IDLE_TIMEOUT,
    DEFAULT_PORT,
    DOMAIN,
    MAX_PORT,
    MAX_RECEIVER_ID,
    MIN_PORT,
    MIN_RECEIVER_ID,
)

_HEX_KEY_RE = re.compile(r"^[0-9a-fA-F]{32}$")


def _user_schema(defaults: dict[str, Any] | None = None) -> vol.Schema:
    """Build the user/reconfigure schema.

    Deliberately does not set ``min``/``max`` on the NumberSelectors: Home
    Assistant enforces those as a hard schema-validation failure *before*
    the step handler ever runs, which surfaces as a generic crash instead of
    a friendly, translated per-field error. Range checking is instead done
    entirely in :meth:`SpcEdpConfigFlow._async_validate` below, which can
    show ``invalid_receiver_id``/``invalid_port`` errors on the form.
    """
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(
                CONF_RECEIVER_ID, default=defaults.get(CONF_RECEIVER_ID)
            ): NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX)),
            vol.Required(
                CONF_PORT, default=defaults.get(CONF_PORT, DEFAULT_PORT)
            ): NumberSelector(NumberSelectorConfig(mode=NumberSelectorMode.BOX)),
            vol.Required(
                CONF_BIND, default=defaults.get(CONF_BIND, DEFAULT_BIND)
            ): TextSelector(),
            vol.Optional(
                CONF_ENCRYPTION_KEY, default=defaults.get(CONF_ENCRYPTION_KEY, "")
            ): TextSelector(TextSelectorConfig(type=TextSelectorType.PASSWORD)),
        }
    )


async def _async_test_bind(bind: str, port: int) -> None:
    """Confirm the address:port is bindable, then release it immediately.

    This only proves the local listen socket can be opened; it cannot
    confirm the panel will actually dial in, since that depends on the
    panel's own EDP configuration and network path.
    """
    server = await asyncio.start_server(lambda r, w: None, bind, port)
    server.close()
    await server.wait_closed()


class SpcEdpConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Vanderbilt SPC (EDP)."""

    VERSION = 2

    async def _async_validate(
        self, user_input: dict[str, Any]
    ) -> dict[str, str]:
        """Validate user input, returning a dict of field -> error code."""
        errors: dict[str, str] = {}

        receiver_id = int(user_input[CONF_RECEIVER_ID])
        if not (MIN_RECEIVER_ID <= receiver_id <= MAX_RECEIVER_ID):
            errors[CONF_RECEIVER_ID] = "invalid_receiver_id"

        port = int(user_input[CONF_PORT])
        if not (MIN_PORT <= port <= MAX_PORT):
            errors[CONF_PORT] = "invalid_port"

        key = (user_input.get(CONF_ENCRYPTION_KEY) or "").strip()
        if key and not _HEX_KEY_RE.match(key):
            errors[CONF_ENCRYPTION_KEY] = "invalid_encryption_key"

        if not errors:
            try:
                await _async_test_bind(user_input[CONF_BIND], port)
            except OSError:
                errors["base"] = "cannot_bind"

        return errors

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step."""
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            if not errors:
                await self.async_set_unique_id(
                    f"{user_input[CONF_BIND]}:{int(user_input[CONF_PORT])}"
                )
                self._abort_if_unique_id_configured()
                key = (user_input.get(CONF_ENCRYPTION_KEY) or "").strip() or None
                return self.async_create_entry(
                    title=f"SPC Panel ({user_input[CONF_BIND]}:{int(user_input[CONF_PORT])})",
                    data={
                        CONF_RECEIVER_ID: int(user_input[CONF_RECEIVER_ID]),
                        CONF_BIND: user_input[CONF_BIND],
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_ENCRYPTION_KEY: key,
                    },
                )

        return self.async_show_form(
            step_id="user", data_schema=_user_schema(user_input), errors=errors
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the receiver id, bind address, port, or key."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        if user_input is not None:
            errors = await self._async_validate(user_input)
            new_unique_id = f"{user_input[CONF_BIND]}:{int(user_input[CONF_PORT])}"
            if not errors and new_unique_id != entry.unique_id:
                await self.async_set_unique_id(new_unique_id)
                self._abort_if_unique_id_configured()
            if not errors:
                key = (user_input.get(CONF_ENCRYPTION_KEY) or "").strip() or None
                return self.async_update_reload_and_abort(
                    entry,
                    title=f"SPC Panel ({user_input[CONF_BIND]}:{int(user_input[CONF_PORT])})",
                    data={
                        CONF_RECEIVER_ID: int(user_input[CONF_RECEIVER_ID]),
                        CONF_BIND: user_input[CONF_BIND],
                        CONF_PORT: int(user_input[CONF_PORT]),
                        CONF_ENCRYPTION_KEY: key,
                    },
                )

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=_user_schema(user_input or dict(entry.data)),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        """Get the options flow for this handler."""
        return SpcEdpOptionsFlow()


class SpcEdpOptionsFlow(OptionsFlow):
    """Tune runtime behaviour without re-running the connection setup."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        if user_input is not None:
            return self.async_create_entry(data=user_input)

        options = self.config_entry.options
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_IDLE_TIMEOUT,
                    default=options.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT),
                ): NumberSelector(
                    NumberSelectorConfig(min=30, max=600, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_AUX_REFRESH_INTERVAL,
                    default=options.get(
                        CONF_AUX_REFRESH_INTERVAL, DEFAULT_AUX_REFRESH_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=10, max=3600, mode=NumberSelectorMode.BOX)
                ),
                vol.Required(
                    CONF_AREA_REFRESH_INTERVAL,
                    default=options.get(
                        CONF_AREA_REFRESH_INTERVAL, DEFAULT_AREA_REFRESH_INTERVAL
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=30, max=7200, mode=NumberSelectorMode.BOX)
                ),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema)
