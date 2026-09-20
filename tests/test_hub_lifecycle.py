"""Availability, reconnects and alarm commands."""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.exceptions import HomeAssistantError
from spcedp import Area, Panel, SpcTimeout, Zone

from custom_components.spc_edp.alarm_control_panel import SpcEdpAlarmControlPanel
from custom_components.spc_edp.binary_sensor import SpcEdpZoneBinarySensor
from custom_components.spc_edp.const import SIGNAL_UPDATE_AREA, SIGNAL_UPDATE_ZONE
from custom_components.spc_edp.hub import SpcEdpHub


def make_hub(hass):
    entry = MagicMock()
    entry.data = {"bind": "127.0.0.1", "port": 50000, "receiver_id": 1001}
    entry.options = {}
    entry.entry_id = "test-entry"
    entry.unique_id = "test-panel"
    return SpcEdpHub(hass, entry)


async def test_initial_read_failure_releases_session_for_retry(hass):
    hub = make_hub(hass)
    # The registry's hardware identity is not the EDP frame's source address.
    hub.entry.data["panel_id"] = "physical-panel-id"
    session = MagicMock()
    with patch(
        "custom_components.spc_edp.hub.Panel.from_session",
        side_effect=SpcTimeout("timeout"),
    ):
        await hub._on_session(session)
    assert not hub.available
    assert hub._session is None
    session.request_teardown.assert_called_once()

    panel = Panel(MagicMock())
    connected = asyncio.Event()

    async def events():
        connected.set()
        await asyncio.Future()
        yield

    panel.events = events
    with patch("custom_components.spc_edp.hub.Panel.from_session", return_value=panel):
        task = asyncio.create_task(hub._on_session(MagicMock()))
        await connected.wait()
        assert hub.available
        await hub._on_session(session)  # duplicate cannot replace the active panel
        assert hub.panel is panel
        assert hub.available
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
    assert not hub.available
    assert hub._session is None
    assert hub._area_unsub is None


async def test_removed_entities_become_unavailable_and_are_notified(hass):
    hub = make_hub(hass)
    session = MagicMock()
    session.xml_command = AsyncMock(return_value={})
    hub.panel = Panel(session)
    hub.panel.areas[1] = Area(id=1, mode="0")
    hub.panel.zones[2] = Zone.from_row({"ID": "2", "INPUT": "0"})
    hub.available = True
    alarm = SpcEdpAlarmControlPanel(hub, 1)
    sensor = SpcEdpZoneBinarySensor(hub, 2)
    assert alarm.available and sensor.available
    with patch("custom_components.spc_edp.hub.async_dispatcher_send") as dispatch:
        await hub.async_refresh()
    assert not alarm.available and not sensor.available
    dispatch.assert_any_call(hass, SIGNAL_UPDATE_AREA.format("test-entry", 1))
    dispatch.assert_any_call(hass, SIGNAL_UPDATE_ZONE.format("test-entry", 2))


@pytest.mark.parametrize(
    "method,opcode",
    [
        ("async_alarm_disarm", "AREA_UNSET"),
        ("async_alarm_arm_home", "AREA_SET_A"),
        ("async_alarm_arm_night", "AREA_SET_B"),
        ("async_alarm_arm_away", "AREA_SET"),
    ],
)
async def test_alarm_controls_refresh_confirmed_state(hass, method, opcode):
    from spcedp.commands import BinaryOp

    hub = make_hub(hass)
    session = MagicMock()
    session.binary_command = AsyncMock()
    session.xml_command = AsyncMock(
        return_value={"AREA_STATUS": [{"ID": "1", "MODE": "2"}]}
    )
    hub.panel = Panel(session)
    hub.panel.areas[1] = Area(id=1, mode="0")
    hub.available = True
    alarm = SpcEdpAlarmControlPanel(hub, 1)
    await getattr(alarm, method)()
    session.binary_command.assert_awaited_once_with(getattr(BinaryOp, opcode), 1)
    assert hub.panel.areas[1].mode == "2"


async def test_unavailable_alarm_does_not_send_commands(hass):
    hub = make_hub(hass)
    alarm = SpcEdpAlarmControlPanel(hub, 1)
    with pytest.raises(HomeAssistantError, match="unavailable"):
        await alarm.async_alarm_arm_home()
