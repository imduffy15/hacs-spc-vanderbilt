"""Binary sensor platform for Vanderbilt SPC (EDP) zones."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp import ZoneType
from spcedp.panel import Zone

from .const import SIGNAL_NEW_ZONES, SIGNAL_UPDATE_ZONE
from .entity import SpcEdpEntity
from .hub import SpcEdpHub

# This remains an adapter concern: Home Assistant's entity device classes are
# not part of the protocol SDK. The SDK owns the complete ZoneType vocabulary.
_DEVICE_CLASS_BY_TYPE: dict[ZoneType, BinarySensorDeviceClass] = {
    ZoneType.ALARM: BinarySensorDeviceClass.MOTION,
    ZoneType.ENTRY_EXIT: BinarySensorDeviceClass.DOOR,
    ZoneType.ENTRY_EXIT_2: BinarySensorDeviceClass.DOOR,
    ZoneType.FIRE: BinarySensorDeviceClass.SMOKE,
    ZoneType.PANIC: BinarySensorDeviceClass.SAFETY,
    ZoneType.HOLD_UP: BinarySensorDeviceClass.SAFETY,
    ZoneType.TAMPER: BinarySensorDeviceClass.TAMPER,
    ZoneType.TECHNICAL: BinarySensorDeviceClass.POWER,
    ZoneType.MEDICAL: BinarySensorDeviceClass.SAFETY,
    ZoneType.GLASSBREAK: BinarySensorDeviceClass.VIBRATION,
    ZoneType.WATER: BinarySensorDeviceClass.MOISTURE,
    ZoneType.HEAT: BinarySensorDeviceClass.HEAT,
    ZoneType.FRIDGE_FREEZER: BinarySensorDeviceClass.COLD,
    ZoneType.GAS: BinarySensorDeviceClass.GAS,
    ZoneType.CO: BinarySensorDeviceClass.CO,
    ZoneType.SEISMIC: BinarySensorDeviceClass.VIBRATION,
}


def _device_class(zone_type: ZoneType | None) -> BinarySensorDeviceClass | None:
    return _DEVICE_CLASS_BY_TYPE.get(zone_type)


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up binary sensor entities for known and future zones."""
    hub: SpcEdpHub = entry.runtime_data

    added: set[int] = set()

    @callback
    def _add_zones(zone_ids: set[int]) -> None:
        new = zone_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(SpcEdpZoneBinarySensor(hub, zone_id) for zone_id in new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_ZONES.format(entry.entry_id), _add_zones
        )
    )

    if hub.panel is not None:
        _add_zones(set(hub.panel.zones))


class SpcEdpZoneBinarySensor(SpcEdpEntity, BinarySensorEntity):
    """Representation of one SPC detection zone."""

    def __init__(self, hub: SpcEdpHub, zone_id: int) -> None:
        """Initialize the binary sensor for one zone."""
        super().__init__(hub)
        self._zone_id = zone_id
        self._attr_unique_id = f"{hub.unique_id}-zone-{zone_id}"

    @property
    def _zone(self) -> Zone | None:
        panel = self._hub.panel
        return panel.zones.get(self._zone_id) if panel else None

    @property
    def name(self) -> str:
        """Use the zone's real name from the panel (e.g. "Front Door")."""
        zone = self._zone
        return zone.name if zone and zone.name else f"Zone {self._zone_id}"

    @property
    def available(self) -> bool:
        return super().available and self._zone is not None

    @property
    def device_class(self) -> BinarySensorDeviceClass | None:
        """Best-effort device class derived from the SDK's typed zone type."""
        zone = self._zone
        return _device_class(zone.zone_type) if zone else None

    @property
    def is_on(self) -> bool | None:
        """Whether the zone is currently open/active.

        The protocol SDK resolves the physical ``INPUT`` value, including its
        safe fallback for older or unexpected panel replies.
        """
        zone = self._zone
        if zone is None:
            return None
        return zone.is_open

    async def async_added_to_hass(self) -> None:
        """Subscribe to zone-specific + availability updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_ZONE.format(self._hub.entry.entry_id, self._zone_id),
                self.async_write_ha_state,
            )
        )
