"""Vanderbilt SPC alarm controls and zone sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .hub import SpcEdpHub

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
]

type SpcEdpConfigEntry = ConfigEntry[SpcEdpHub]


async def async_setup_entry(hass: HomeAssistant, entry: SpcEdpConfigEntry) -> bool:
    """Set up Vanderbilt SPC (EDP) from a config entry."""
    hub = SpcEdpHub(hass, entry)
    await hub.async_start()
    entry.runtime_data = hub

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    try:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    except BaseException:
        await hub.async_stop()
        raise
    return True


async def async_unload_entry(hass: HomeAssistant, entry: SpcEdpConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        await entry.runtime_data.async_stop()
    return unload_ok


async def _async_update_listener(hass: HomeAssistant, entry: SpcEdpConfigEntry) -> None:
    """Reload the entry when its options change."""
    await hass.config_entries.async_reload(entry.entry_id)
