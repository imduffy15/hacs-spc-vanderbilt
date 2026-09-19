"""Unit tests for the best-effort zone TYPE -> device_class mapping."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorDeviceClass
from spcedp import ZoneType

from custom_components.spc_edp.binary_sensor import _device_class


def test_known_zone_types_map_to_expected_device_classes() -> None:
    """Known raw TYPE codes should resolve to a sensible device class."""
    assert _device_class(ZoneType.ALARM) is BinarySensorDeviceClass.MOTION
    assert _device_class(ZoneType.ENTRY_EXIT) is BinarySensorDeviceClass.DOOR
    assert _device_class(ZoneType.FIRE) is BinarySensorDeviceClass.SMOKE


def test_unknown_zone_type_falls_back_to_none() -> None:
    """An unmapped/unverified TYPE code should degrade gracefully, not guess."""
    assert _device_class(ZoneType.UNUSED) is None
    assert _device_class(None) is None
