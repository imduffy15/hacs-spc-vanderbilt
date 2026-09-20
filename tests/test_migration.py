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
