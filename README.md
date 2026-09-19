# Vanderbilt SPC (EDP) for Home Assistant

A modern, standalone [HACS](https://hacs.xyz) custom integration for
Vanderbilt/Siemens SPC alarm panels, built on top of
[`spcedp`](https://github.com/imduffy15/spcedp) — a from-scratch async
implementation of the panel's native **EDP** protocol.

This is **not** a replacement drop-in for Home Assistant core's built-in
[`spc`](https://github.com/home-assistant/core/tree/master/homeassistant/components/spc)
integration and it is not intended to ever be merged into Home Assistant
core. It uses a different `spc_edp` domain so the two can coexist, but they
talk to the panel in fundamentally different ways (see below) and are not
interchangeable.

## ⚠️ Python version requirement

`spcedp` declares `requires-python = ">=3.14"` in its `pyproject.toml`, so
this integration requires a Home Assistant install running on **Python
3.14 or newer**. Home Assistant Core added Python 3.14 support in its own
release cycle; if you're on an older Home Assistant Core release still
pinned to Python 3.13 (or earlier), installing this integration's
dependency will fail with a resolver error, and that's a constraint of
`spcedp` itself, not something this integration's code can work around.
Check your running Home Assistant's Python version (**Settings → System →
Repairs → ⋮ → System information**, or `python3 --version` in the HA
container) before installing, and update Home Assistant Core first if
needed.

## Why this integration is architected differently

Home Assistant's legacy `spc` integration (and both of the abandoned
upstream PRs this project draws inspiration from,
[home-assistant/core#135894](https://github.com/home-assistant/core/pull/135894)
and [home-assistant/core#135893](https://github.com/home-assistant/core/pull/135893))
are built on [`pyspcwebgw`](https://pypi.org/project/pyspcwebgw/), a client
for Vanderbilt's hosted **SPC Web Gateway** service: Home Assistant connects
*out* to that gateway, which in turn talks to the panel.

`spcedp` instead speaks the panel's native **EDP** protocol directly: Home
Assistant opens a TCP **listen socket** and the physical panel dials *in* to
it (configured panel-side under *Communications → Reporting → EDP*), the
same way the panel would normally report to a monitoring station. There is
no cloud/web-gateway dependency at all — communication stays entirely on
your local network (or over whatever WAN path you configure).

Practical implications of this model:

- Setup succeeds as soon as the listen socket is bound; entities go
  available once the panel actually connects and unavailable if it
  disconnects — the config flow's "connection test" can only confirm the
  port is bindable, not that the panel will actually dial in.
- Data is pushed to Home Assistant as SIA events arrive, rather than polled.
  A slower periodic reconciliation pass (see **Options** below) corrects for
  the few things SIA events can't fully disambiguate (see *Known
  limitations*) and for outputs/doors, which have no push equivalent at all.
- You must configure the panel itself (Receiver ID, this host's IP, and the
  port you choose here) under its EDP reporting settings for anything to
  happen.

## Features

Compared to the legacy `spc`/`pyspcwebgw` integration, this integration adds:

- **Full config flow**: UI-based setup, `reconfigure` support (change bind
  address/port/receiver ID/encryption key without deleting and re-adding the
  integration), and an **options flow** for tuning poll intervals and idle
  timeout — no YAML required.
- **Encrypted EDP support** (AES-128, matching `spcedp`'s capability), with
  format validation in the config flow.
- A proper Home Assistant **device hierarchy**: one device for the panel
  itself, and one sub-device per configured Area (via `via_device`), with
  zones/areas/outputs/doors attached to the appropriate device.
- **Dynamic entity discovery**: if the panel is reprogrammed with new
  areas/zones/outputs/doors after setup, matching entities appear
  automatically without a restart.
- Platforms: `alarm_control_panel`, `binary_sensor`, `switch`, `lock`,
  `button`, `sensor`, and `event` (see below) — versus core's
  `alarm_control_panel` + `binary_sensor` only.
- A **diagnostics** download (config entry diagnostics), with the
  encryption key redacted.
- A raw **SIA event bus event** (`spc_edp_sia_event`) and a dedicated
  `event` entity, so you can build automations off of any SIA code the panel
  sends — not just the ones mapped to entities.

### Entities created

| Platform | Description |
|---|---|
| `alarm_control_panel` | One per Area. Maps SPC arm modes (unset / part A / part B / full) to `disarmed` / `armed_home` / `armed_night` / `armed_away`, and reports `triggered` when an alarm zone has fired since the area was last disarmed. Exposes `last_set_time`, `last_unset_time`, `last_alarm`, and `not_ready_set` as extra attributes. |
| `binary_sensor` | One per Zone, with a best-effort `device_class` inferred from the zone's raw `TYPE` code (see *Known limitations*). |
| `binary_sensor` (diagnostic) | One panel-wide connectivity sensor reflecting whether the panel currently has an active EDP session. |
| `switch` | One per Output. |
| `lock` | One per Door, with `LockEntityFeature.OPEN` support (momentary release). `unlock` holds the door permanently released; `lock` uses the verified EDP door-lock opcode. |
| `button` | Panel-wide: silence bell, restore alert, play audio, self-test, reset. Per-door and per-zone protection controls are disabled by default: inhibit, deinhibit, isolate and deisolate; doors also expose “set normal mode”. |
| `sensor` (diagnostic) | A "Last event" sensor showing the most recent SIA event description, with the raw SIA code/category/address as attributes. |
| `event` | A panel-wide event entity firing on every pushed SIA event, typed into `alarm` / `restore` / `trouble` / `access` / `test` / `unknown`. |


## Installation

### Via HACS (recommended)

1. In HACS, add this repository as a **custom repository** (category:
   Integration): `https://github.com/imduffy15/hacs-spc-vanderbilt` (or your
   fork's URL).
2. Install "Vanderbilt SPC (EDP)" from HACS.
3. Restart Home Assistant.
4. Go to **Settings → Devices & Services → Add Integration**, search for
   "Vanderbilt SPC (EDP)".

### Manual

Copy `custom_components/spc_edp` into your Home Assistant's
`custom_components` directory and restart.

## Configuration

You'll need, from the panel's *Communications → Reporting → EDP* settings:

- **Receiver ID** — must match the panel's configured EDP receiver ID.
- **Port** — the TCP port Home Assistant will listen on. The panel must be
  configured to dial this same port on Home Assistant's IP.
- **Bind address** — defaults to `0.0.0.0` (listen on all interfaces).
- **Encryption key** — the 32 hex digit (16 byte) AES key, if the panel has
  EDP encryption enabled. Leave blank otherwise.

### Options

After setup, use the integration's **Configure** button to tune:

- **Idle timeout** — disconnect the panel if nothing is received for this
  long (the panel normally polls roughly every 10 seconds).
- **Output/door poll interval** — outputs and doors have no SIA push
  equivalent, so they're polled on this interval.
- **Area/zone reconciliation interval** — a slower full re-sync used to
  correct any drift not captured by pushed SIA events (see below).

## Known limitations

- **Zone `device_class` mapping is best-effort.** The `spcedp` SDK owns the
  typed SPC `ZoneType` vocabulary; this adapter maps the subset that has a
  meaningful Home Assistant device class. The remaining types intentionally
  fall back to a generic binary sensor rather than guessing.
- **Door state still needs validation on a panel with configured doors.** The
  integration now uses the verified EDP lock opcode for `lock`; `unlock`
  keeps the door permanently released and `open` releases it momentarily.
  The raw state remains an attribute until it has been confirmed across more
  real door-controller configurations.
- **Alarm "triggered" state is event-derived.** `spcedp` tracks it from
  alarm-category SIA events and clears it on a disarm event or a refresh
  that authoritatively reports the area unset. It is prompt and useful for
  automation, but it is not a replacement for a panel-native current-alarm
  field.
- **A generic panel "closing" SIA event can't distinguish a partial set from
  a full set** on its own; `spcedp.Panel.apply_event()` treats it as a full
  set. The periodic area/zone reconciliation pass corrects this drift, by
  default every 30 seconds (configurable). It also keeps zone state current
  on panels whose EDP reporting profile does not publish SIA zone-open/close
  events.
- **No historical polling of the panel's own event log** — only events
  pushed live over the SIA stream while connected are captured.

## Development

```bash
python -m py_compile custom_components/spc_edp/*.py
```

Pull requests welcome. This integration pins `spcedp` to a specific commit
in `manifest.json` (it has no PyPI release yet); bump that pin deliberately
and re-test against a real panel connection when doing so.

## Credits

- Built on [`spcedp`](https://github.com/imduffy15/spcedp) by Ian Duffy.
- Inspired by Home Assistant core's legacy `spc` integration and the
  unmerged config-flow work in
  [PR #135894](https://github.com/home-assistant/core/pull/135894) and
  [PR #135893](https://github.com/home-assistant/core/pull/135893).
- Brand icon/logo (`custom_components/spc_edp/brand/`) is Vanderbilt/Siemens's
  own SPC product mark, reused from the official `spc` core integration's
  entry in [home-assistant/brands](https://github.com/home-assistant/brands),
  loaded locally per the [HA 2026.3+ custom-integration brand images
  mechanism](https://developers.home-assistant.io/docs/core/integration/brand_images/#custom-integrations).
