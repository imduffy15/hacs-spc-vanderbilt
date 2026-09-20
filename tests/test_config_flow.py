"""Integration tests for the config flow, driven through Home Assistant."""

from __future__ import annotations

from unittest.mock import patch

import pytest
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.spc_edp.const import (
    CONF_BIND,
    CONF_ENCRYPTION_KEY,
    CONF_PORT,
    CONF_RECEIVER_ID,
    DOMAIN,
)

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")

_VALID_INPUT = {
    CONF_RECEIVER_ID: 1001,
    CONF_PORT: 50123,
    CONF_BIND: "127.0.0.1",
    CONF_ENCRYPTION_KEY: "",
}


async def test_user_flow_creates_entry(hass: HomeAssistant) -> None:
    """A valid submission should bind the port and create a config entry."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    with (
        patch(
            "custom_components.spc_edp.config_flow._async_test_bind",
            return_value=None,
        ),
        patch(
            "custom_components.spc_edp.hub.SpcEdpHub.async_start",
            return_value=None,
        ),
    ):
        result = await hass.config_entries.flow.async_configure(result["flow_id"], _VALID_INPUT)
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"][CONF_RECEIVER_ID] == 1001
    assert result["data"][CONF_ENCRYPTION_KEY] is None


async def test_user_flow_rejects_invalid_port(hass: HomeAssistant) -> None:
    """An out-of-range port should be rejected with a field-level error."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_VALID_INPUT, CONF_PORT: 70000}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_PORT] == "invalid_port"


async def test_user_flow_rejects_invalid_encryption_key(hass: HomeAssistant) -> None:
    """A key that isn't 32 hex digits should be rejected."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_VALID_INPUT, CONF_ENCRYPTION_KEY: "not-hex"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"][CONF_ENCRYPTION_KEY] == "invalid_encryption_key"


async def test_user_flow_rejects_unbindable_address(hass: HomeAssistant) -> None:
    """A bind failure should surface as a base-level cannot_bind error."""
    with patch("asyncio.start_server", side_effect=OSError("in use")):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], _VALID_INPUT)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"]["base"] == "cannot_bind"


async def test_reconfigure_active_listener_preserves_panel_identity(hass) -> None:
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.spc_edp.const import CONF_PANEL_ID

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=3,
        unique_id="12345",
        title="SPC4300",
        data={**_VALID_INPUT, CONF_PANEL_ID: "12345"},
    )
    entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN,
        context={
            "source": config_entries.SOURCE_RECONFIGURE,
            "entry_id": entry.entry_id,
        },
    )
    with (
        patch("custom_components.spc_edp.config_flow._async_test_bind") as bind,
        patch.object(hass.config_entries, "async_reload", return_value=True),
    ):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {**_VALID_INPUT, CONF_RECEIVER_ID: 1002}
        )
        await hass.async_block_till_done()
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    bind.assert_not_called()
    assert entry.unique_id == "12345"
    assert entry.data[CONF_PANEL_ID] == "12345"
    assert entry.data[CONF_RECEIVER_ID] == 1002


@pytest.mark.parametrize("field", [CONF_PORT, CONF_RECEIVER_ID])
async def test_fractional_identifiers_are_rejected(hass, field) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**_VALID_INPUT, field: 1001.5}
    )
    assert field in result["errors"]


@pytest.mark.parametrize("receiver_id", [1, 65536, 999997])
async def test_receiver_id_accepts_panels_full_range(hass, receiver_id) -> None:
    from custom_components.spc_edp.config_flow import SpcEdpConfigFlow

    flow = SpcEdpConfigFlow()
    errors = await flow._async_validate(
        {**_VALID_INPUT, CONF_RECEIVER_ID: receiver_id}, test_bind=False
    )
    assert not errors


@pytest.mark.parametrize("receiver_id", [0, -1, 999998, 999999])
async def test_receiver_id_rejects_reserved_and_out_of_range_values(hass, receiver_id) -> None:
    from custom_components.spc_edp.config_flow import SpcEdpConfigFlow

    flow = SpcEdpConfigFlow()
    errors = await flow._async_validate(
        {**_VALID_INPUT, CONF_RECEIVER_ID: receiver_id}, test_bind=False
    )
    assert errors == {CONF_RECEIVER_ID: "invalid_receiver_id"}
