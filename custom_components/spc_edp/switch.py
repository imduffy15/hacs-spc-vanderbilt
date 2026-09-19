"""Switch platform for Vanderbilt SPC (EDP) controllable outputs."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from spcedp.panel import Output

from .commands import async_run_command
from .const import SIGNAL_NEW_OUTPUTS, SIGNAL_UPDATE_OUTPUT
from .entity import SpcEdpEntity, hub_device_info
from .hub import SpcEdpHub


async def async_setup_entry(
    hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    """Set up switch entities for known and future outputs."""
    hub: SpcEdpHub = entry.runtime_data
    added: set[int] = set()

    @callback
    def _add_outputs(output_ids: set[int]) -> None:
        new = output_ids - added
        if not new:
            return
        added.update(new)
        async_add_entities(SpcEdpOutputSwitch(hub, output_id) for output_id in new)

    entry.async_on_unload(
        async_dispatcher_connect(
            hass, SIGNAL_NEW_OUTPUTS.format(entry.entry_id), _add_outputs
        )
    )

    if hub.panel is not None:
        _add_outputs(set(hub.panel.outputs))


class SpcEdpOutputSwitch(SpcEdpEntity, SwitchEntity):
    """Representation of one SPC controllable output (e.g. a siren/relay)."""

    _attr_entity_registry_enabled_default = True

    def __init__(self, hub: SpcEdpHub, output_id: int) -> None:
        """Initialize the switch for one output."""
        super().__init__(hub)
        self._output_id = output_id
        self._attr_unique_id = f"{hub.unique_id}-output-{output_id}"

    @property
    def _output(self) -> Output | None:
        panel = self._hub.panel
        return panel.outputs.get(self._output_id) if panel else None

    @property
    def name(self) -> str:
        """Use the output's real name from the panel (e.g. "Siren")."""
        output = self._output
        return output.name if output and output.name else f"Output {self._output_id}"

    @property
    def device_info(self) -> DeviceInfo:
        """Outputs are panel-wide, not tied to a single area."""
        return hub_device_info(self._hub)

    @property
    def is_on(self) -> bool | None:
        """Whether the output is currently active."""
        output = self._output
        return output.is_active if output else None

    async def async_added_to_hass(self) -> None:
        """Subscribe to output-specific + availability updates."""
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_UPDATE_OUTPUT.format(self._hub.entry.entry_id, self._output_id),
                self._handle_output_update,
            )
        )

    @callback
    def _handle_output_update(self) -> None:
        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the output."""
        await async_run_command(
            self._hub.panel.output(self._output_id).set(),
            f"turning on output {self._output_id}",
        )

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Reset the output."""
        await async_run_command(
            self._hub.panel.output(self._output_id).reset(),
            f"turning off output {self._output_id}",
        )
