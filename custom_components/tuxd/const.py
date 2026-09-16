DOMAIN = "tuxd"
WS_PATH = "/api/tuxd/ws"

HUB_IDENTIFIER = "hub"

CONF_PAIRING_KEY = "pairing_key"

SIGNAL_NEW_ENTITY = "tuxd_new_entity_{domain}"
SIGNAL_STATE_UPDATE = "tuxd_state_{unique_id}"
SIGNAL_HUB_STATS_UPDATE = "tuxd_hub_stats_update"

PLATFORMS = [
    "sensor",
    "binary_sensor",
    "number",
    "switch",
    "text",
    "button",
    "update",
    "select",
]
