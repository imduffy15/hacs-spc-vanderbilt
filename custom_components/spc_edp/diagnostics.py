"""Diagnostics support for Vanderbilt SPC (EDP)."""

from __future__ import annotations

from dataclasses import asdict
from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import CONF_ENCRYPTION_KEY
from .hub import SpcEdpHub

TO_REDACT = {CONF_ENCRYPTION_KEY}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    hub: SpcEdpHub = entry.runtime_data
    panel = hub.panel

    return {
        "entry_data": async_redact_data(dict(entry.data), TO_REDACT),
        "entry_options": dict(entry.options),
        "available": hub.available,
        "triggered_areas": (
            sorted(area_id for area_id, area in panel.areas.items() if area.triggered)
            if panel is not None
            else []
        ),
        "panel": (
            {
                "info": asdict(panel.info),
                "areas": {k: asdict(v) for k, v in panel.areas.items()},
                "zones": {k: asdict(v) for k, v in panel.zones.items()},
                "outputs": {k: asdict(v) for k, v in panel.outputs.items()},
                "doors": {k: asdict(v) for k, v in panel.doors.items()},
                "last_refresh": (
                    panel.last_refresh.isoformat() if panel.last_refresh else None
                ),
            }
            if panel is not None
            else None
        ),
    }
