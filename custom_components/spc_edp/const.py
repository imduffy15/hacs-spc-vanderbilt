"""Constants for the Vanderbilt SPC (EDP) integration."""

from __future__ import annotations

DOMAIN = "spc_edp"
MANUFACTURER = "Vanderbilt (Siemens)"

# Config entry data
CONF_RECEIVER_ID = "receiver_id"
CONF_BIND = "bind"
CONF_PORT = "port"
CONF_ENCRYPTION_KEY = "encryption_key"
CONF_PANEL_ID = "panel_id"

# --- Config entry option keys (tunable after setup) -------------------------
CONF_IDLE_TIMEOUT = "idle_timeout"
CONF_AREA_REFRESH_INTERVAL = "area_refresh_interval"

DEFAULT_BIND = "0.0.0.0"
DEFAULT_PORT = 50000
DEFAULT_IDLE_TIMEOUT = 120
# EDP event reporting can be selectively disabled at the panel. A 30-second
# zone refresh is the lowest interval exposed by the options flow and keeps
# physical state current even when the panel does not publish SIA ZO/ZC events.
DEFAULT_AREA_REFRESH_INTERVAL = 30  # seconds; reconciles event drift/fallback

MIN_PORT = 1
MAX_PORT = 65535
MIN_RECEIVER_ID = 1
MAX_RECEIVER_ID = 999997

# --- Dispatcher signals ------------------------------------------------------
SIGNAL_AVAILABILITY = "spc_edp_availability_{}"
SIGNAL_UPDATE_AREA = "spc_edp_update_area_{}_{}"
SIGNAL_UPDATE_ZONE = "spc_edp_update_zone_{}_{}"
SIGNAL_NEW_AREAS = "spc_edp_new_areas_{}"
SIGNAL_NEW_ZONES = "spc_edp_new_zones_{}"
