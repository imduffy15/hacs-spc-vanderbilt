"""Lock platform for Vanderbilt SPC (EDP) access-control doors.

spcedp's ``Door.state`` is a raw, largely unverified string (see
``spcedp.panel.Door``'s docstring: "the attribute set is inferred from the
DOOR_STATUS schema and may need re-confirmation against a panel that
actually has doors configured"). We treat "1" as locked and "0" as
unlocked, mirroring the zone/output/area conventions used elsewhere on the
same firmware, but surface the raw value as an attribute so it can be
verified/overridden per-installation.

The supplied SPC Web Gateway binary confirms that EDP opcode ``0x1B`` locks
an access-control door. ``unlock`` maps to ``open_permanent`` (hold the door
released) and ``open`` to ``open_momentary`` (a brief release).
"""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp.panel import Door

from .commands import async_run_command
from .const import SIGNAL_NEW_DOORS, SIGNAL_UPDATE_DOOR
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up lock entities for known and future doors."""
    hub: SpcEdpHub = entry.runtime_data
    added: set[int] = set()

    @callback
    def _add_doors(door_ids: set[int]) -> None:
        new = door_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(SpcEdpDoorLock(hub, door_id) for door_id in new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_DOORS.format(entry.entry_id), _add_doors
        )
    )

    if hub.panel is not None:
        _add_doors(set(hub.panel.doors))


class SpcEdpDoorLock(SpcEdpEntity, LockEntity):
    """Representation of one SPC access-control door."""

    _attr_supported_features = LockEntityFeature.OPEN

    def __init__(self, hub: SpcEdpHub, door_id: int) -> None:
        """Initialize the lock for one door."""
        super().__init__(hub)
        self._door_id = door_id
        self._attr_unique_id = f"{hub.unique_id}-door-{door_id}"

    @property
    def _door(self) -> Door | None:
        panel = self._hub.panel
        return panel.doors.get(self._door_id) if panel else None

    @property
    def name(self) -> str:
        """Use the door's real name from the panel (e.g. "Front Door")."""
        door = self._door
        return door.name if door and door.name else f"Door {self._door_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Doors are panel-wide, not tied to a single area."""
        return hub_device_info(self._hub)

    @property
    def is_locked(self) -> bool | None:
        """Best-effort locked state; see module docstring for caveats."""
        door = self._door
        if door is None or not door.state:
            return None
        return door.state == "1"

    @property
    def extra_state_attributes(self) -> dict[str, str] | None:
        """Expose the raw, not-yet-fully-verified door state string."""
        door = self._door
        return {"raw_state": door.state} if door else None

    async def async_added_to_hass(self) -> None:
        """Subscribe to door-specific + availability updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_DOOR.format(self._hub.entry.entry_id, self._door_id),
                self._handle_door_update,
            )
        )

    @callback
    def _handle_door_update(self) -> None:
        self.async_write_ha_state()

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the access-control door (EDP opcode 0x1B)."""
        await async_run_command(
            self._hub.panel.door(self._door_id).lock(), f"locking door {self._door_id}"
        )

    async def async_unlock(self, **kwargs: Any) -> None:
        """Hold the door open/released (permanent open)."""
        await async_run_command(
            self._hub.panel.door(self._door_id).open_permanent(),
            f"unlocking door {self._door_id}",
        )

    async def async_open(self, **kwargs: Any) -> None:
        """Momentarily release the door."""
        await async_run_command(
            self._hub.panel.door(self._door_id).open_momentary(),
            f"opening door {self._door_id}",
        )
