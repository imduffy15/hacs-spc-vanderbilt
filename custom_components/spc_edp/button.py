"""Button platform for Vanderbilt SPC (EDP) panel-wide and door actions."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import (
    ButtonDeviceClass,
    ButtonEntity,
    ButtonEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp.panel import Panel

from .commands import async_run_command
from .const import SIGNAL_NEW_DOORS, SIGNAL_NEW_ZONES
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub


@dataclass(frozen=True, kw_only=True)
class SpcEdpButtonDescription(ButtonEntityDescription):
    """Describes a panel-wide button and how to invoke it."""

    press_fn: Callable[[Panel], Awaitable[None]]


PANEL_BUTTONS: tuple[SpcEdpButtonDescription, ...] = (
    SpcEdpButtonDescription(
        key="bell_silence",
        translation_key="bell_silence",
        press_fn=lambda panel: panel.bell_silence(),
    ),
    SpcEdpButtonDescription(
        key="alert_restore",
        translation_key="alert_restore",
        press_fn=lambda panel: panel.alert_restore(),
    ),
    SpcEdpButtonDescription(
        key="audio_play",
        translation_key="audio_play",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda panel: panel.audio_play(),
    ),
    SpcEdpButtonDescription(
        key="test",
        translation_key="test",
        entity_category=EntityCategory.DIAGNOSTIC,
        press_fn=lambda panel: panel.test(),
    ),
    SpcEdpButtonDescription(
        key="reset",
        translation_key="reset",
        device_class=ButtonDeviceClass.RESTART,
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda panel: panel.reset(),
    ),
)


@dataclass(frozen=True, kw_only=True)
class SpcEdpDoorButtonDescription(ButtonEntityDescription):
    """Describes a per-door secondary action button."""

    press_fn: Callable[[Panel, int], Awaitable[None]]


DOOR_BUTTONS: tuple[SpcEdpDoorButtonDescription, ...] = (
    SpcEdpDoorButtonDescription(
        key="inhibit",
        translation_key="door_inhibit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, door_id: panel.door(door_id).inhibit(),
    ),
    SpcEdpDoorButtonDescription(
        key="deinhibit",
        translation_key="door_deinhibit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, door_id: panel.door(door_id).deinhibit(),
    ),
    SpcEdpDoorButtonDescription(
        key="isolate",
        translation_key="door_isolate",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, door_id: panel.door(door_id).isolate(),
    ),
    SpcEdpDoorButtonDescription(
        key="deisolate",
        translation_key="door_deisolate",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, door_id: panel.door(door_id).deisolate(),
    ),
    SpcEdpDoorButtonDescription(
        key="set_normal_mode",
        translation_key="door_set_normal_mode",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, door_id: panel.door(door_id).set_normal_mode(),
    ),
)


@dataclass(frozen=True, kw_only=True)
class SpcEdpZoneButtonDescription(ButtonEntityDescription):
    """Describes a per-zone protection-state action."""

    press_fn: Callable[[Panel, int], Awaitable[None]]


ZONE_BUTTONS: tuple[SpcEdpZoneButtonDescription, ...] = (
    SpcEdpZoneButtonDescription(
        key="inhibit",
        translation_key="zone_inhibit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, zone_id: panel.zone(zone_id).inhibit(),
    ),
    SpcEdpZoneButtonDescription(
        key="deinhibit",
        translation_key="zone_deinhibit",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, zone_id: panel.zone(zone_id).deinhibit(),
    ),
    SpcEdpZoneButtonDescription(
        key="isolate",
        translation_key="zone_isolate",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, zone_id: panel.zone(zone_id).isolate(),
    ),
    SpcEdpZoneButtonDescription(
        key="deisolate",
        translation_key="zone_deisolate",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda panel, zone_id: panel.zone(zone_id).deisolate(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up panel-wide buttons, plus per-door action buttons."""
    hub: SpcEdpHub = entry.runtime_data
    async_add_entities(
        SpcEdpPanelButton(hub, description) for description in PANEL_BUTTONS
    )

    added: set[int] = set()

    @callback
    def _add_doors(door_ids: set[int]) -> None:
        new = door_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(
            SpcEdpDoorButton(hub, door_id, description)
            for door_id in new
            for description in DOOR_BUTTONS
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DOORS.format(entry.entry_id), _add_doors
        )
    )
    if hub.panel is not None:
        _add_doors(set(hub.panel.doors))

    added_zones: set[int] = set()

    @callback
    def _add_zones(zone_ids: set[int]) -> None:
        new = zone_ids - added_zones
        if not new:
            return
        added_zones.update(new)
        async_add_entities(
            SpcEdpZoneButton(hub, zone_id, description)
            for zone_id in new
            for description in ZONE_BUTTONS
        )

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_ZONES.format(entry.entry_id), _add_zones
        )
    )
    if hub.panel is not None:
        _add_zones(set(hub.panel.zones))


class SpcEdpPanelButton(SpcEdpEntity, ButtonEntity):
    """A panel-wide action (bell silence, alert restore, test, reset, ...)."""

    entity_description: SpcEdpButtonDescription

    def __init__(self, hub: SpcEdpHub, description: SpcEdpButtonDescription) -> None:
        """Initialize the panel-wide action button."""
        super().__init__(hub)
        self.entity_description = description
        self._attr_unique_id = f"{hub.unique_id}-{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Panel-wide actions belong to the panel device."""
        return hub_device_info(self._hub)

    async def async_press(self) -> None:
        """Invoke the described panel-wide action."""
        await async_run_command(
            self.entity_description.press_fn(self._hub.panel),
            self.name or self.entity_description.key,
        )


class SpcEdpDoorButton(SpcEdpEntity, ButtonEntity):
    """A secondary action (inhibit/isolate/...) for one door."""

    entity_description: SpcEdpDoorButtonDescription

    def __init__(
        self, hub: SpcEdpHub, door_id: int, description: SpcEdpDoorButtonDescription
    ) -> None:
        """Initialize the door action button."""
        super().__init__(hub)
        self._door_id = door_id
        self.entity_description = description
        self._attr_unique_id = f"{hub.unique_id}-door-{door_id}-{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Door actions belong to the panel device (doors aren't per-area)."""
        return hub_device_info(self._hub)

    async def async_press(self) -> None:
        """Invoke the described door action."""
        await async_run_command(
            self.entity_description.press_fn(self._hub.panel, self._door_id),
            self.name or self.entity_description.key,
        )


class SpcEdpZoneButton(SpcEdpEntity, ButtonEntity):
    """A secondary action (inhibit/isolate/...) for one zone."""

    entity_description: SpcEdpZoneButtonDescription

    def __init__(
        self, hub: SpcEdpHub, zone_id: int, description: SpcEdpZoneButtonDescription
    ) -> None:
        """Initialize the zone action button."""
        super().__init__(hub)
        self._zone_id = zone_id
        self.entity_description = description
        self._attr_unique_id = f"{hub.unique_id}-zone-{zone_id}-{description.key}"

    @property
    def device_info(self) -> DeviceInfo:
        """Zone actions belong to the panel device."""
        return hub_device_info(self._hub)

    async def async_press(self) -> None:
        """Invoke the described zone action."""
        await async_run_command(
            self.entity_description.press_fn(self._hub.panel, self._zone_id),
            self.name or self.entity_description.key,
        )
