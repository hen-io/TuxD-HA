DOMAIN = "tuxd"
WS_PATH = "/api/tuxd/ws"

HUB_IDENTIFIER = "hub"

CONF_API_KEY = "api_key"

SIGNAL_NEW_ENTITY = "tuxd_new_entity_{domain}"
SIGNAL_STATE_UPDATE = "tuxd_state_{unique_id}"

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
