"""Sensor platform for Vanderbilt SPC (EDP): a diagnostic last-event sensor."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from .const import EVENT_SIA
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the last-SIA-event diagnostic sensor."""
    hub: SpcEdpHub = entry.runtime_data
    async_add_entities([SpcEdpLastEventSensor(hub)])


class SpcEdpLastEventSensor(SpcEdpEntity, RestoreEntity, SensorEntity):
    """The description of the most recently received SIA event."""

    entity_description = SensorEntityDescription(
        key="last_event",
        translation_key="last_event",
        entity_category=EntityCategory.DIAGNOSTIC,
    )

    def __init__(self, hub: SpcEdpHub) -> None:
        """Initialize the last-event sensor."""
        super().__init__(hub)
        self._attr_unique_id = f"{hub.unique_id}-last-event"
        self._attr_native_value: str | None = None
        self._attr_extra_state_attributes: dict[str, str | None] = {}

    @property
    def device_info(self) -> DeviceInfo:
        """Belongs to the panel device."""
        return hub_device_info(self._hub)

    @property
    def available(self) -> bool:
        """The last known event stays visible even while disconnected."""
        return True

    async def async_added_to_hass(self) -> None:
        """Restore the last known value and start listening for new events."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) is not None:
            self._attr_native_value = last_state.state
            self._attr_extra_state_attributes = dict(last_state.attributes)
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_SIA, self._handle_sia_event)
        )

    @callback
    def _handle_sia_event(self, event: Event) -> None:
        data = event.data
        if data.get("entry_id") != self._hub.entry.entry_id:
            return
        self._attr_native_value = data.get("description") or data.get("sia_code")
        self._attr_extra_state_attributes = {
            "sia_code": data.get("sia_code"),
            "category": data.get("category"),
            "address": data.get("address"),
            "timestamp": data.get("timestamp"),
        }
        self.async_write_ha_state()
