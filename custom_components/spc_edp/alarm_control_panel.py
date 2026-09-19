"""Alarm control panel platform for Vanderbilt SPC (EDP) areas."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import (
    AlarmControlPanelEntity,
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp import ArmMode
from spcedp.panel import Area

from .commands import async_run_command
from .const import SIGNAL_NEW_AREAS, SIGNAL_UPDATE_AREA
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub

_MODE_TO_STATE: dict[ArmMode, AlarmControlPanelState] = {
    ArmMode.UNSET: AlarmControlPanelState.DISARMED,
    ArmMode.PART_A: AlarmControlPanelState.ARMED_HOME,
    ArmMode.PART_B: AlarmControlPanelState.ARMED_NIGHT,
    ArmMode.FULL: AlarmControlPanelState.ARMED_AWAY,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up alarm control panel entities for known and future areas."""
    hub: SpcEdpHub = entry.runtime_data
    added: set[int] = set()

    @callback
    def _add_areas(area_ids: set[int]) -> None:
        new = area_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(SpcEdpAlarmControlPanel(hub, area_id) for area_id in new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_AREAS.format(entry.entry_id), _add_areas
        )
    )

    if hub.panel is not None:
        _add_areas(set(hub.panel.areas))


class SpcEdpAlarmControlPanel(SpcEdpEntity, AlarmControlPanelEntity):
    """Representation of one SPC alarm area."""

    _attr_code_arm_required = False
    _attr_supported_features = (
        AlarmControlPanelEntityFeature.ARM_HOME
        | AlarmControlPanelEntityFeature.ARM_AWAY
        | AlarmControlPanelEntityFeature.ARM_NIGHT
    )

    def __init__(self, hub: SpcEdpHub, area_id: int) -> None:
        """Initialize the alarm control panel for one area."""
        super().__init__(hub)
        self._area_id = area_id
        self._attr_unique_id = f"{hub.unique_id}-area-{area_id}"

    @property
    def _area(self) -> Area | None:
        panel = self._hub.panel
        return panel.areas.get(self._area_id) if panel else None

    @property
    def name(self) -> str:
        """Use the area's real name from the panel (e.g. "Home")."""
        area = self._area
        return area.name if area and area.name else f"Area {self._area_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Areas share the single panel device; there is no separate sub-device."""
        return hub_device_info(self._hub)

    @property
    def changed_by(self) -> str | None:
        """Return the user the last unset was triggered by."""
        area = self._area
        return area.last_unset_user_name if area else None

    @property
    def alarm_state(self) -> AlarmControlPanelState | None:
        """Return the state of the area."""
        area = self._area
        if area is None:
            return None
        if area.triggered:
            return AlarmControlPanelState.TRIGGERED
        mode = area.arm_mode
        if mode is None:
            return None
        return _MODE_TO_STATE.get(mode)

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose raw diagnostic fields the panel does not otherwise surface."""
        area = self._area
        if area is None:
            return None
        return {
            "last_set_time": area.last_set_time,
            "last_unset_time": area.last_unset_time,
            "last_alarm": area.last_alarm,
            "not_ready_set": area.not_ready_set,
        }

    async def async_added_to_hass(self) -> None:
        """Subscribe to area-specific + availability updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_AREA.format(self._hub.entry.entry_id, self._area_id),
                self._handle_area_update,
            )
        )

    @callback
    def _handle_area_update(self) -> None:
        self.async_write_ha_state()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        """Send disarm command."""
        await async_run_command(
            self._hub.panel.area(self._area_id).unset(), "disarming this area"
        )

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        """Send part-set A (arm home) command."""
        await async_run_command(
            self._hub.panel.area(self._area_id).set_a(),
            "arming this area in home mode",
            engineer_mode_possible=True,
        )

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        """Send part-set B (arm night) command."""
        await async_run_command(
            self._hub.panel.area(self._area_id).set_b(),
            "arming this area in night mode",
            engineer_mode_possible=True,
        )

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        """Send full-set (arm away) command."""
        await async_run_command(
            self._hub.panel.area(self._area_id).set(),
            "arming this area away",
            engineer_mode_possible=True,
        )
