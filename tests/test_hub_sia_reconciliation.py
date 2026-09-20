"""Tests for pushed SIA event reconciliation in the runtime hub."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from spcedp.events import SiaEvent
from spcedp.panel import EventStateUpdate

from custom_components.spc_edp.const import SIGNAL_UPDATE_AREA
from custom_components.spc_edp.hub import SpcEdpHub


@pytest.mark.asyncio
async def test_area_event_is_reconciled_before_entity_dispatch(hass) -> None:
    """The push consumer awaits authoritative state before updating HA."""
    entry = MagicMock()
    entry.entry_id = "test-entry"
    entry.data = {}
    entry.options = {}
    hub = SpcEdpHub(hass, entry)

    event = SiaEvent(
        spc_id=1001,
        timestamp=None,
        timestamp_raw="11002320092026",
        sia_code="NL",
        address="1",
        description="Home¦Remote Engineer¦9998",
        verification_id="",
    )
    panel = MagicMock()
    panel.reconcile_event = AsyncMock(
        return_value=EventStateUpdate(area_ids=frozenset({1}))
    )

    with patch(
        "custom_components.spc_edp.hub.async_dispatcher_send"
    ) as dispatcher_send:
        await hub._handle_sia_event(panel, event)

    panel.reconcile_event.assert_awaited_once_with(event)
    dispatcher_send.assert_called_once_with(
        hass, SIGNAL_UPDATE_AREA.format("test-entry", 1)
    )
