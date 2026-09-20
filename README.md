# Vanderbilt SPC for Home Assistant

Local zone sensors and alarm controls for Vanderbilt/Siemens SPC panels.
The panel connects directly to Home Assistant over EDP v2; no web gateway
or cloud service is needed. Requires Python 3.14 or newer.

## Install

1. Add `https://github.com/imduffy15/hacs-spc-vanderbilt` as a HACS custom
   repository (category **Integration**), install, and restart Home Assistant.
   For manual installation, copy `custom_components/spc_edp` into `/config/custom_components`.
2. Open **Settings → Devices & services → Add integration → Vanderbilt SPC (EDP)**.
3. Enter the receiver ID, TCP port (default `50000`), bind address (default
   `0.0.0.0`), and optional 32-hex-digit AES key.
4. In the panel's **Communications → Reporting → EDP**, configure:
   - The same receiver ID, port and encryption key.
   - Home Assistant's reachable IP as the receiver address.
   - EDP version **2**, **TCP/IP**, **Network** and **Commands** enabled.
   - **Always connected**, **Panel master**, **Primary receiver** and
     **Verification** enabled, live streaming always available, polling **10 seconds**.

For a container installation, expose the TCP port on the host or use host
networking. Setup checks that Home Assistant can listen; entities appear
when the panel connects. Keep EDP on a trusted network: its optional AES
mode does not authenticate messages.

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
uv venv --python 3.14
uv pip install -r requirements-test.txt ruff
uv run pytest -q
uv run ruff check custom_components tests
```

The integration pins [spcedp](https://github.com/imduffy15/spcedp) to a tested
commit. When changing both projects, install the library checkout with
`uv pip install -e ../spcedp`, run both test suites, then update the pin.

SPC brand artwork comes from Home Assistant's brands repository. MIT license.
