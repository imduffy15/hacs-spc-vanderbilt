# Vanderbilt SPC for Home Assistant

Local zone sensors and alarm controls for Vanderbilt/Siemens SPC panels.
The panel connects directly to Home Assistant over EDP v2; no web gateway
or cloud service is needed. Requires Home Assistant 2026.9.3 or newer (Python 3.14.2+).

## Support

Release candidate: live-tested on **SPC4300 firmware 3.15.0**, one area,
15 zones, unencrypted EDP TCP, and Home Assistant **2026.9.3**. Home, night
and away arming/disarming have been exercised with live sensor updates.
Encrypted connections and multiple areas are covered by simulated-panel tests;
they and other models/firmware still need field validation. Longer observation
is pending before v1 general availability.

## Install

1. Add `https://github.com/imduffy15/hacs-spc-vanderbilt` as a HACS custom
   repository (category **Integration**), install, and restart Home Assistant.
   For `v1.0.0rc3`, enable **Show beta versions** in the repository menu and select
   that release when downloading.
   For manual installation, copy `custom_components/spc_edp` into `/config/custom_components`.
2. Open **Settings → Devices & services → Add integration → Vanderbilt SPC (EDP)**.
3. Enter the receiver ID, TCP port (default `50000`), bind address (default
   `0.0.0.0`), and optional 32-hex-digit AES key.

For containers, expose the listen port over TCP or use host networking.
Keep EDP on a trusted network: its optional AES mode does not authenticate messages.

## Panel setup

In the panel's web interface, open **Communications → Reporting → EDP**.

**1. Open Settings to enable EDP globally.** These are reference values from
a working SPC4300's **EDP Settings (Panel)** screen:

| Setting | Value |
| --- | --- |
| Enable | Checked |
| EDP Panel ID | Keep your panel's existing ID; example `1000` |
| Panel Port | `50000` |
| Packet Size Limit | `1440` |
| Event Timeout / Retry Count | `10` seconds / `10` retries |

Save, then go **Back**. The panel ID identifies the alarm panel; the receiver
ID identifies Home Assistant. The **Panel Port** belongs to the panel;
Home Assistant's listen port is configured in the receiver entry below.
Modem dial settings can stay as they are for this TCP connection.
**Event Logging Options** control the panel's log; command permission and
reported events are configured separately below.

**2. Add or edit a receiver for Home Assistant.**

| Receiver setting | Value |
| --- | --- |
| Receiver ID | Match Home Assistant; example `1001` |
| Protocol Version | Version 2 |
| Commands Enable / Network Enable | Checked |
| Network Protocol | TCP/IP |
| Receiver IP Address | Home Assistant host's LAN IP |
| Receiver IP Port | Home Assistant's listen port; default `50000` |
| Always Connected / Primary Receiver | Checked |
| Polling Interval | `10` seconds |
| Encryption | Match Home Assistant; use the same 32-hex-digit key if enabled |

**3. Open Event Filter.** Enable **Zone state**, **Settings**, **Alarms** and
**Confirmed Alarms**, and select the areas you want to monitor. Save the
receiver and exit engineer mode so remote arming is allowed.

Audio/video streaming, verification and virtual-keypad access are unused.
Panel Master applies to UDP. See [Vanderbilt's EDP setup reference](https://doc.vanderbiltindustries.com/docs/Intrusion/SPC/SPCPanel/v_3.11/InstallAndConfig_OLH/EN/Content/Topics/EDP_Setup.htm)
for the panel's other settings.

Setup succeeds when Home Assistant can listen. Once the panel connects,
the alarm area and zone sensors appear. Open a door to check its sensor:
it updates immediately with zone reporting enabled, or within the refresh
interval. If entities remain unavailable, check the receiver address, exposed
TCP port and encryption key.

## Use

One device contains a binary sensor for each zone and an alarm entity for
each area. Zone names come from the panel; open/active zones report `on`.
Device classes are best-effort; change them in Home Assistant if needed.

| Home Assistant action/state | SPC mode |
| --- | --- |
| Disarm / `disarmed` | Unset |
| Arm home / `armed_home` | Part set A |
| Arm night / `armed_night` | Part set B |
| Arm away / `armed_away` | Full set |

Use the alarm card or the standard `alarm_control_panel.alarm_arm_home`,
`alarm_arm_night`, `alarm_arm_away` and `alarm_disarm` actions. A Home Assistant
PIN is not required; access is controlled by Home Assistant and the panel's
EDP permissions. Exit engineer mode at the panel if remote arming is rejected.

Sensors update from pushed events. Arm/disarm events trigger an immediate
area-state read because their payload cannot reliably identify the arm mode.
A full area/zone read runs every **30 seconds** to cover missed events and
panels that do not stream zone changes. Under **Configure**, adjust this
interval and the idle timeout (default **120 seconds**). Use **Reconfigure**
to change receiver settings.

Entities become unavailable on disconnect or removal from the panel;
new zones and areas appear automatically. Alarm `triggered` is inferred
from events received during the connection and clears on a confirmed disarm.
It is not a complete panel-native record of active alarms after a restart.

## Development

```sh
mise install
mise run setup       # Locked dependencies and prek Git hooks
mise run format      # Apply Ruff formatting
mise run ci          # All checks, tests and release packaging
```

`mise run check` runs Ruff lint/format, strict mypy, Pylint, Bandit,
workflow checks and file hygiene. `mise run test` runs the tests separately.
Tool versions and dependencies are pinned in `mise.lock` and `uv.lock`.
GitHub Actions call these same tasks and cache tools, dependencies and check results.
Tag builds bypass caches before publishing their validated artifacts.

The full CI task also runs Hassfest and HACS validation using Docker.
For local HACS checks, run `gh auth login` first; HACS checks the pushed commit.
To release, update the version in both `pyproject.toml` and `manifest.json`,
then push a matching `vX.Y.Z` tag. CI publishes `spc_edp.zip` for HACS.

The integration pins [spcedp](https://github.com/imduffy15/spcedp) to a tested
commit in both `manifest.json` and `pyproject.toml`; metadata validation keeps
them aligned. When updating the library, update both pins, run `mise exec -- uv lock`,
and run both test suites.

SPC brand artwork comes from Home Assistant's brands repository. MIT license.
