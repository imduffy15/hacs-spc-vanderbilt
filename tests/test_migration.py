"""Config-entry migration tests."""

from __future__ import annotations

import pytest
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import entity_registry as er
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.spc_edp import async_migrate_entry
from custom_components.spc_edp.const import DOMAIN

pytestmark = pytest.mark.usefixtures("enable_custom_integrations")


async def test_version_three_removes_obsolete_entity_platforms(
    hass: HomeAssistant,
) -> None:
    """Only area controls and zone sensors survive the surface reduction."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        data={"bind": "0.0.0.0", "port": 50000, "panel_id": "737624802"},
    )
    entry.add_to_hass(hass)
    registry = er.async_get(hass)

    keep_alarm = registry.async_get_or_create(
        Platform.ALARM_CONTROL_PANEL,
        DOMAIN,
        "737624802-area-1",
        config_entry=entry,
    )
    keep_zone = registry.async_get_or_create(
        Platform.BINARY_SENSOR,
        DOMAIN,
        "737624802-zone-1",
        config_entry=entry,
    )
    remove_connectivity = registry.async_get_or_create(
        Platform.BINARY_SENSOR,
        DOMAIN,
        "737624802-connectivity",
        config_entry=entry,
    )
    remove_event = registry.async_get_or_create(
        Platform.EVENT,
        DOMAIN,
        "737624802-sia-events",
        config_entry=entry,
    )
    remove_button = registry.async_get_or_create(
        Platform.BUTTON,
        DOMAIN,
        "737624802-panel-reset",
        config_entry=entry,
    )

    assert await async_migrate_entry(hass, entry)

    assert entry.version == 3
    assert registry.async_get(keep_alarm.entity_id) is not None
    assert registry.async_get(keep_zone.entity_id) is not None
    assert registry.async_get(remove_connectivity.entity_id) is None
    assert registry.async_get(remove_event.entity_id) is None
    assert registry.async_get(remove_button.entity_id) is None


@pytest.mark.parametrize("serial", ["000003e8", None, "unknown"])
async def test_legacy_identity_migration_preserves_names_and_entity_ids(hass, serial):
    from homeassistant.helpers import device_registry as dr

    from custom_components.spc_edp import _async_migrate_registry_identity

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="127.0.0.1:50000",
        title="Garage alarm",
        data={"bind": "127.0.0.1", "port": 50000},
    )
    entry.add_to_hass(hass)
    devices = dr.async_get(hass)
    device = devices.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name="SPC5300",
        serial_number=serial,
    )
    devices.async_update_device(device.id, name_by_user="Garage")
    entities = er.async_get(hass)
    sensor = entities.async_get_or_create(
        Platform.BINARY_SENSOR,
        DOMAIN,
        f"{entry.unique_id}-zone-1",
        config_entry=entry,
        device_id=device.id,
        suggested_object_id="garage_door",
    )
    assert await async_migrate_entry(hass, entry)
    await _async_migrate_registry_identity(hass, entry)
    await _async_migrate_registry_identity(hass, entry)  # Idempotent on subsequent setup.
    assert entry.version == 3
    assert entry.title == "Garage alarm"
    updated = devices.async_get(device.id)
    assert updated.name == "SPC5300"
    assert updated.name_by_user == "Garage"
    expected_identity = "1000" if serial == "000003e8" else "127.0.0.1:50000"
    assert entry.unique_id == expected_identity
    assert entities.async_get(sensor.entity_id).unique_id == f"{expected_identity}-zone-1"
    assert updated.identifiers == {(DOMAIN, expected_identity)}


async def test_migration_only_changes_device_owned_by_entry(hass):
    from homeassistant.helpers import device_registry as dr

    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        unique_id="127.0.0.1:50000",
        title="House",
        data={"bind": "127.0.0.1", "port": 50000},
    )
    other = MockConfigEntry(domain=DOMAIN, version=1, unique_id="other", data={})
    entry.add_to_hass(hass)
    other.add_to_hass(hass)
    devices = dr.async_get(hass)
    devices.async_get_or_create(
        config_entry_id=other.entry_id,
        identifiers={(DOMAIN, entry.unique_id)},
        name="Other panel",
        serial_number="000003e8",
    )
    assert await async_migrate_entry(hass, entry)
    assert entry.unique_id == "127.0.0.1:50000"
