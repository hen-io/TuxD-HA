DOMAIN = "tuxd"
WS_PATH = "/api/tuxd/ws"

HUB_IDENTIFIER = "hub"

CONF_PAIRING_KEY = "pairing_key"

ISSUE_PENDING_DEVICES = "pending_devices"

SIGNAL_NEW_ENTITY = "tuxd_new_entity_{domain}"
SIGNAL_REMOVE_ENTITY = "tuxd_remove_entity_{domain}"
SIGNAL_STATE_UPDATE = "tuxd_state_{unique_id}"
SIGNAL_HUB_STATS_UPDATE = "tuxd_hub_stats_update"
SIGNAL_LAST_SEEN_UPDATE = "tuxd_last_seen_{device_id}"
SIGNAL_DEVICE_APPROVED = "tuxd_device_approved"

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
