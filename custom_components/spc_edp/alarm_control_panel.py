"""Alarm control panel platform for Vanderbilt SPC (EDP) areas."""

from __future__ import annotations

from homeassistant.components.alarm_control_panel import AlarmControlPanelEntity
from homeassistant.components.alarm_control_panel.const import (
    AlarmControlPanelEntityFeature,
    AlarmControlPanelState,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp import ArmMode
from spcedp.panel import Area

from .commands import async_run_command
from .const import SIGNAL_NEW_AREAS, SIGNAL_UPDATE_AREA
from .entity import SpcEdpEntity
from .hub import SpcEdpHub

_MODE_TO_STATE: dict[ArmMode, AlarmControlPanelState] = {
    ArmMode.UNSET: AlarmControlPanelState.DISARMED,
    ArmMode.PART_A: AlarmControlPanelState.ARMED_HOME,
    ArmMode.PART_B: AlarmControlPanelState.ARMED_NIGHT,
    ArmMode.FULL: AlarmControlPanelState.ARMED_AWAY,
}


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry[SpcEdpHub], async_add_entities: AddEntitiesCallback
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
        async_dispatcher_connect(hass, SIGNAL_NEW_AREAS.format(entry.entry_id), _add_areas)
    )

    if hub.panel is not None:
        _add_areas(set(hub.panel.areas))


# Home Assistant supports async overrides and optional methods on this base class.
class SpcEdpAlarmControlPanel(SpcEdpEntity, AlarmControlPanelEntity):  # pylint: disable=abstract-method
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
    def available(self) -> bool:
        return super().available and self._area is not None

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

    async def async_added_to_hass(self) -> None:
        """Subscribe to area-specific + availability updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_AREA.format(self._hub.entry.entry_id, self._area_id),
                self.async_write_ha_state,
            )
        )

    async def _async_set_mode(self, mode: ArmMode) -> None:
        if not self.available or self._hub.panel is None:
            raise HomeAssistantError("The SPC panel is unavailable")
        area = self._hub.panel.area(self._area_id)
        command = {
            ArmMode.UNSET: area.unset,
            ArmMode.PART_A: area.set_a,
            ArmMode.PART_B: area.set_b,
            ArmMode.FULL: area.set,
        }[mode]
        await async_run_command(
            command(),
            "disarming this area" if mode is ArmMode.UNSET else "arming this area",
            engineer_mode_possible=mode is not ArmMode.UNSET,
        )
        await self._hub.async_refresh()

    async def async_alarm_disarm(self, code: str | None = None) -> None:
        await self._async_set_mode(ArmMode.UNSET)

    async def async_alarm_arm_home(self, code: str | None = None) -> None:
        await self._async_set_mode(ArmMode.PART_A)

    async def async_alarm_arm_night(self, code: str | None = None) -> None:
        await self._async_set_mode(ArmMode.PART_B)

    async def async_alarm_arm_away(self, code: str | None = None) -> None:
        await self._async_set_mode(ArmMode.FULL)
