"""Vanderbilt SPC alarm controls and zone sensors."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import CONF_PANEL_ID, DOMAIN
from .hub import SpcEdpHub

PLATFORMS: list[Platform] = [
    Platform.ALARM_CONTROL_PANEL,
    Platform.BINARY_SENSOR,
]

type SpcEdpConfigEntry = ConfigEntry[SpcEdpHub]


def _panel_id_from_serial(serial_number: str | None) -> str | None:
    """Derive a panel's decimal device id from its eight-digit hex serial."""
    if not serial_number or len(serial_number) != 8:
        return None
    try:
        return str(int(serial_number, 16))
    except ValueError:
        return None


def _remove_obsolete_entities(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Remove entities outside the supported alarm-control/zone surface."""
    entity_registry = er.async_get(hass)
    for entity in list(entity_registry.entities.values()):
        if entity.config_entry_id != entry.entry_id:
            continue
        domain = entity.entity_id.partition(".")[0]
        _, marker, zone_id = entity.unique_id.rpartition("-zone-")
        is_zone = (
            domain == Platform.BINARY_SENSOR.value
            and bool(marker)
            and zone_id.isdigit()
        )
        if domain != Platform.ALARM_CONTROL_PANEL.value and not is_zone:
            entity_registry.async_remove(entity.entity_id)


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate address-based identifiers to the immutable panel device id.

    Entity ids are intentionally retained, so existing automations keep their
    familiar names. Only registry unique ids and the physical-device
    identifier change from ``bind:port`` to the decimal panel id.
    """
    if entry.version > 3:
        return False
    if entry.version < 2:
        old_identity = entry.unique_id or f"{entry.data['bind']}:{entry.data['port']}"
        device_registry = dr.async_get(hass)
        device = device_registry.async_get_device(identifiers={(DOMAIN, old_identity)})
        panel_id = _panel_id_from_serial(device.serial_number if device else None)

        if panel_id is not None:
            hass.config_entries.async_update_entry(
                entry,
                data={**entry.data, CONF_PANEL_ID: panel_id},
                title="SPC4300",
                unique_id=panel_id,
                version=2,
            )
        else:
            # Retain an established address identity for unusual panels whose
            # serial cannot safely be converted to a device id.
            hass.config_entries.async_update_entry(entry, version=2)

    if entry.version < 3:
        _remove_obsolete_entities(hass, entry)
        hass.config_entries.async_update_entry(entry, version=3)
    return True


async def _async_migrate_registry_identity(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Rewrite existing registry records once Home Assistant has loaded them."""
    panel_id = entry.data.get(CONF_PANEL_ID)
    if not panel_id:
        return
    old_identity = f"{entry.data['bind']}:{entry.data['port']}"
    if panel_id == old_identity:
        return

    entity_registry = er.async_get(hass)
    old_prefix = f"{old_identity}-"
    new_prefix = f"{panel_id}-"
    for entity in list(entity_registry.entities.values()):
        if entity.config_entry_id == entry.entry_id and entity.unique_id.startswith(
            old_prefix
        ):
            entity_registry.async_update_entity(
                entity.entity_id,
                new_unique_id=new_prefix + entity.unique_id.removeprefix(old_prefix),
            )

    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device(identifiers={(DOMAIN, old_identity)})
    if device is not None:
        device_registry.async_update_device(
            device.id,
            new_identifiers={(DOMAIN, panel_id)},
            name="SPC4300",
        )


async def async_setup_entry(hass: HomeAssistant, entry: SpcEdpConfigEntry) -> bool:
    """Set up Vanderbilt SPC (EDP) from a config entry."""
    # Run on every setup as well as migration. This cleans registry records
    # created by pre-0.3 releases even if another Home Assistant process (for
    # example config validation) advanced the config-entry version first.
    _remove_obsolete_entities(hass, entry)
    await _async_migrate_registry_identity(hass, entry)
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
