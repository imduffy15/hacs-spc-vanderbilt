"""Event platform for Vanderbilt SPC (EDP): a live SIA event stream."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_SIA
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub

# Mirrors spcedp.events.SiaEvent.category's coarse classification.
_EVENT_TYPES = ["alarm", "restore", "trouble", "access", "test", "unknown"]


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up the panel-wide SIA event entity."""
    hub: SpcEdpHub = entry.runtime_data
    async_add_entities([SpcEdpSiaEventEntity(hub)])


class SpcEdpSiaEventEntity(SpcEdpEntity, EventEntity):
    """Surfaces every pushed SIA event as a Home Assistant event entity."""

    _attr_name = "SIA events"
    _attr_event_types = _EVENT_TYPES

    def __init__(self, hub: SpcEdpHub) -> None:
        """Initialize the SIA event entity."""
        super().__init__(hub)
        self._attr_unique_id = f"{hub.unique_id}-sia-events"

    @property
    def device_info(self) -> DeviceInfo:
        """Belongs to the panel device."""
        return hub_device_info(self._hub)

    async def async_added_to_hass(self) -> None:
        """Start listening for SIA events on the event bus."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.hass.bus.async_listen(EVENT_SIA, self._handle_sia_event)
        )

    @callback
    def _handle_sia_event(self, event: Event) -> None:
        data = event.data
        if data.get("entry_id") != self._hub.entry.entry_id:
            return
        category = data.get("category") or "unknown"
        if category not in _EVENT_TYPES:
            category = "unknown"
        self._trigger_event(
            category,
            {
                "sia_code": data.get("sia_code"),
                "address": data.get("address"),
                "description": data.get("description"),
            },
        )
        self.async_write_ha_state()
