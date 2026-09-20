"""Runtime hub that owns a spcedp PanelServer for one config entry.

Unlike most Home Assistant integrations, the SPC panel is the one that
dials *in* to us: :class:`spcedp.PanelServer` opens a TCP listen socket and
waits for the panel to connect, authenticate, and start polling. This hub
wraps that lifecycle, keeps the latest :class:`spcedp.Panel` snapshot,
reconciles state on every pushed SIA event, and runs light periodic polling
only for the pieces of state (outputs, doors) that have no SIA push
equivalent.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_interval
from spcedp import Panel, PanelServer, Session, SiaEvent, SpcError

from .const import (
    CONF_AREA_REFRESH_INTERVAL,
    CONF_AUX_REFRESH_INTERVAL,
    CONF_BIND,
    CONF_ENCRYPTION_KEY,
    CONF_IDLE_TIMEOUT,
    CONF_PANEL_ID,
    CONF_PORT,
    CONF_RECEIVER_ID,
    DEFAULT_AREA_REFRESH_INTERVAL,
    DEFAULT_AUX_REFRESH_INTERVAL,
    DEFAULT_IDLE_TIMEOUT,
    EVENT_SIA,
    SIGNAL_AVAILABILITY,
    SIGNAL_NEW_AREAS,
    SIGNAL_NEW_DOORS,
    SIGNAL_NEW_OUTPUTS,
    SIGNAL_NEW_ZONES,
    SIGNAL_UPDATE_AREA,
    SIGNAL_UPDATE_DOOR,
    SIGNAL_UPDATE_OUTPUT,
    SIGNAL_UPDATE_ZONE,
)

_LOGGER = logging.getLogger(__name__)

class SpcEdpHub:
    """Owns the PanelServer/Panel lifecycle for a single config entry."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        """Initialize the hub (does not start listening yet)."""
        self.hass = hass
        self.entry = entry
        self.panel: Panel | None = None
        self.available = False
        self._server: PanelServer | None = None
        self._aux_unsub: object | None = None
        self._area_unsub: object | None = None
        self._refresh_lock = asyncio.Lock()

        self._known_area_ids: set[int] = set()
        self._known_zone_ids: set[int] = set()
        self._known_output_ids: set[int] = set()
        self._known_door_ids: set[int] = set()

        # Live inbound EDP connections (normally exactly one: the panel).
        # Tracked so async_stop() can force them closed; see its docstring.
        # Session is a mutable dataclass and consequently unhashable.  Keep
        # sessions keyed by object identity rather than in a set.
        self._active_sessions: dict[int, Session] = {}

    # ------------------------------------------------------------------ config
    @property
    def receiver_id(self) -> int:
        """The EDP receiver id the panel is configured to dial."""
        return self.entry.data[CONF_RECEIVER_ID]

    @property
    def bind(self) -> str:
        """The local address the listen socket is bound to."""
        return self.entry.data[CONF_BIND]

    @property
    def port(self) -> int:
        """The local TCP port the listen socket is bound to."""
        return self.entry.data[CONF_PORT]

    @property
    def encryption_key(self) -> str | None:
        """The 32-hex-digit EDP AES key, or None if encryption is disabled."""
        return self.entry.data.get(CONF_ENCRYPTION_KEY)

    @property
    def idle_timeout(self) -> float:
        """Seconds of silence before a stale panel connection is dropped."""
        return self.entry.options.get(CONF_IDLE_TIMEOUT, DEFAULT_IDLE_TIMEOUT)

    @property
    def aux_refresh_interval(self) -> int:
        """Poll interval (seconds) for outputs/doors, which have no SIA push."""
        return self.entry.options.get(
            CONF_AUX_REFRESH_INTERVAL, DEFAULT_AUX_REFRESH_INTERVAL
        )

    @property
    def area_refresh_interval(self) -> int:
        """Poll interval (seconds) for the area/zone drift-reconciliation pass."""
        return self.entry.options.get(
            CONF_AREA_REFRESH_INTERVAL, DEFAULT_AREA_REFRESH_INTERVAL
        )

    # ------------------------------------------------------------------ unique id
    @property
    def unique_id(self) -> str:
        """Stable physical-panel identity, with an old-entry fallback."""
        return str(self.entry.data.get(CONF_PANEL_ID, f"{self.bind}:{self.port}"))

    # ------------------------------------------------------------------ lifecycle
    async def async_start(self) -> None:
        """Open the EDP listen socket. Raises ConfigEntryNotReady on failure."""
        self._server = PanelServer(
            receiver_id=self.receiver_id,
            bind=self.bind,
            port=self.port,
            key=self.encryption_key,
            idle_timeout=self.idle_timeout,
            on_session=self._on_session,
        )
        try:
            await self._server.__aenter__()
        except OSError as err:
            self._server = None
            raise ConfigEntryNotReady(
                f"Could not bind EDP receiver on {self.bind}:{self.port}: {err}"
            ) from err

    async def async_stop(self) -> None:
        """Stop listening and force-close any live panel connection.

        Closing the listen socket alone is not enough: ``asyncio.Server.
        wait_closed()`` waits for every already-accepted connection handler
        to finish naturally, which never happens on its own while the panel
        keeps its EDP session open and polling. Force-close the writer of
        any live session first so the server's read loop unblocks promptly,
        then bound the whole teardown with a timeout so a config entry
        reload/unload can never hang indefinitely on a misbehaving peer.
        """
        self._stop_aux_refresh()
        self._stop_area_refresh()
        server, self._server = self._server, None
        if server is None:
            return
        for session in list(self._active_sessions.values()):
            with contextlib.suppress(Exception):
                session.writer.close()
        try:
            async with asyncio.timeout(10):
                await server.__aexit__(None, None, None)
        except TimeoutError:
            _LOGGER.warning(
                "Timed out waiting for the EDP listen socket on %s:%s to "
                "close cleanly; continuing unload anyway",
                self.bind,
                self.port,
            )

    # ------------------------------------------------------------------ session
    async def _on_session(self, session: Session) -> None:
        """Handle one inbound panel connection for its whole lifetime.

        ``spcedp`` invokes this once per TCP session and keeps it running
        concurrently with the read loop; it returns (and the panel is
        considered disconnected) once ``panel.events()`` stops iterating,
        which ``spcedp`` guarantees happens on disconnect.
        """
        _LOGGER.info("Panel connected to receiver %s:%s", self.bind, self.port)
        self._active_sessions[id(session)] = session
        try:
            panel = await Panel.from_session(session)
        except SpcError:
            _LOGGER.exception("Failed to read initial panel state")
            return

        self.panel = panel
        self.available = True
        self._announce_new_entities()
        self._async_set_availability(True)
        self._start_aux_refresh()
        self._start_area_refresh()

        try:
            async for event in panel.events():
                await self._handle_sia_event(panel, event)
        except SpcError:
            _LOGGER.debug("SIA event stream ended", exc_info=True)
        finally:
            self._active_sessions.pop(id(session), None)
            self.available = False
            self._stop_aux_refresh()
            self._stop_area_refresh()
            self._async_set_availability(False)
            _LOGGER.warning(
                "Panel disconnected from receiver %s:%s", self.bind, self.port
            )

    def _async_set_availability(self, available: bool) -> None:
        async_dispatcher_send(
            self.hass, SIGNAL_AVAILABILITY.format(self.entry.entry_id), available
        )

    def _announce_new_entities(self) -> None:
        """Diff the latest snapshot against known ids and notify platforms.

        Areas/zones/outputs/doors are normally static for the lifetime of a
        panel's configuration, but a panel re-programmed after the entry was
        first set up can introduce new ones; this lets platforms add
        entities for them without a full Home Assistant restart.
        """
        panel = self.panel
        if panel is None:
            return
        new_areas = set(panel.areas) - self._known_area_ids
        new_zones = set(panel.zones) - self._known_zone_ids
        new_outputs = set(panel.outputs) - self._known_output_ids
        new_doors = set(panel.doors) - self._known_door_ids

        self._known_area_ids |= new_areas
        self._known_zone_ids |= new_zones
        self._known_output_ids |= new_outputs
        self._known_door_ids |= new_doors

        entry_id = self.entry.entry_id
        if new_areas:
            async_dispatcher_send(self.hass, SIGNAL_NEW_AREAS.format(entry_id), new_areas)
        if new_zones:
            async_dispatcher_send(self.hass, SIGNAL_NEW_ZONES.format(entry_id), new_zones)
        if new_outputs:
            async_dispatcher_send(self.hass, SIGNAL_NEW_OUTPUTS.format(entry_id), new_outputs)
        if new_doors:
            async_dispatcher_send(self.hass, SIGNAL_NEW_DOORS.format(entry_id), new_doors)

    # ------------------------------------------------------------------ events
    async def _handle_sia_event(self, panel: Panel, event: SiaEvent) -> None:
        """Reconcile the snapshot and notify entities for one pushed SIA event.

        Area-mode SIA messages are push notifications, but their payload is
        not a complete state snapshot. ``spcedp`` immediately follows those
        messages with an AREA_STATUS read, matching the behaviour of the old
        web-gateway integration without waiting for the periodic safety poll.
        """
        self.hass.bus.async_fire(
            EVENT_SIA,
            {
                "entry_id": self.entry.entry_id,
                "spc_id": event.spc_id,
                "sia_code": event.sia_code,
                "category": event.category,
                "address": event.address,
                "description": event.description,
                "extra": event.extra,
                "verification_id": event.verification_id,
                "timestamp": event.timestamp.isoformat() if event.timestamp else None,
            },
        )

        try:
            async with self._refresh_lock:
                update = await panel.reconcile_event(event)
        except SpcError:
            _LOGGER.warning(
                "Immediate state reconciliation failed for SIA code %s; "
                "the periodic refresh will retry",
                event.sia_code,
                exc_info=True,
            )
            update = panel.apply_event(event)

        entry_id = self.entry.entry_id
        for zone_id in update.zone_ids:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_ZONE.format(entry_id, zone_id))
        for area_id in update.area_ids:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_AREA.format(entry_id, area_id))

    # ------------------------------------------------------------------ periodic polling
    def _start_aux_refresh(self) -> None:
        self._stop_aux_refresh()
        self._aux_unsub = async_track_time_interval(
            self.hass, self._async_refresh_aux, timedelta(seconds=self.aux_refresh_interval)
        )

    def _stop_aux_refresh(self) -> None:
        if self._aux_unsub is not None:
            self._aux_unsub()
            self._aux_unsub = None

    async def _async_refresh_aux(self, _now: object = None) -> None:
        """Poll outputs and doors, which have no SIA push equivalent."""
        panel = self.panel
        if panel is None or not self.available:
            return
        try:
            async with self._refresh_lock:
                await panel.refresh_outputs()
                await panel.refresh_doors()
        except SpcError:
            _LOGGER.debug("Auxiliary (output/door) refresh failed", exc_info=True)
            return
        self._announce_new_entities()
        entry_id = self.entry.entry_id
        for output_id in panel.outputs:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_OUTPUT.format(entry_id, output_id))
        for door_id in panel.doors:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_DOOR.format(entry_id, door_id))

    def _start_area_refresh(self) -> None:
        self._stop_area_refresh()
        self._area_unsub = async_track_time_interval(
            self.hass, self._async_refresh_areas, timedelta(seconds=self.area_refresh_interval)
        )

    def _stop_area_refresh(self) -> None:
        if self._area_unsub is not None:
            self._area_unsub()
            self._area_unsub = None

    async def _async_refresh_areas(self, _now: object = None) -> None:
        """Periodically reconcile areas/zones beyond what SIA events cover.

        ``Panel.apply_event`` is a best-effort, partial reconciliation (see
        its docstring): a generic "closing" event can't distinguish part-set
        from full-set, for example. This slower full refresh is the
        authoritative correction pass.
        """
        panel = self.panel
        if panel is None or not self.available:
            return
        try:
            async with self._refresh_lock:
                await panel.refresh_areas()
                await panel.refresh_zones()
        except SpcError:
            _LOGGER.debug("Area/zone reconciliation refresh failed", exc_info=True)
            return
        self._announce_new_entities()
        entry_id = self.entry.entry_id
        for area_id in panel.areas:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_AREA.format(entry_id, area_id))
        for zone_id in panel.zones:
            async_dispatcher_send(self.hass, SIGNAL_UPDATE_ZONE.format(entry_id, zone_id))
