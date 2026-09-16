import asyncio
import json
import logging
import secrets

from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    DOMAIN,
    HUB_IDENTIFIER,
    ISSUE_PENDING_DEVICES,
    PLATFORMS,
    SIGNAL_HUB_STATS_UPDATE,
    SIGNAL_NEW_ENTITY,
    SIGNAL_STATE_UPDATE,
)

_LOGGER = logging.getLogger(__name__)


class TuxdHub:

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self.pairing_key = entry.data.get("pairing_key", "")
        self.device_keys = dict(entry.data.get("device_keys", {}))
        self.pending_devices = dict(entry.data.get("pending_devices", {}))

        self.devices = {}
        self.entities = {}
        self.key_to_unique_ids = {}

        self._sync_pending_issue()


    def check_auth(self, device_id, presented_key):
        if not device_id or not presented_key:
            return "rejected"
        known_key = self.device_keys.get(device_id)
        if known_key is not None:
            return "ok" if secrets.compare_digest(presented_key, known_key) else "rejected"
        if self.pairing_key and secrets.compare_digest(presented_key, self.pairing_key):
            return "pending"
        return "rejected"

    def record_pending(self, device_id, hello):
        self.pending_devices[device_id] = {
            "model": hello.get("model"),
            "sw_version": hello.get("sw_version"),
        }
        self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s presented the pairing key and is awaiting approval", device_id)

    def approve_device(self, device_id):
        if device_id not in self.pending_devices:
            return None
        new_key = secrets.token_hex(32)
        self.device_keys[device_id] = new_key
        self.pending_devices.pop(device_id, None)
        self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s approved and issued its own key", device_id)
        self._notify_stats_changed()
        return new_key

    def reject_device(self, device_id):
        if device_id in self.pending_devices:
            self.pending_devices.pop(device_id, None)
            self._persist()
            self._sync_pending_issue()

    def _sync_pending_issue(self):
        if self.pending_devices:
            ir.async_create_issue(
                self.hass,
                DOMAIN,
                ISSUE_PENDING_DEVICES,
                is_fixable=True,
                severity=ir.IssueSeverity.WARNING,
                translation_key=ISSUE_PENDING_DEVICES,
                translation_placeholders={"count": str(len(self.pending_devices))},
                data={"entry_id": self.entry.entry_id},
            )
        else:
            ir.async_delete_issue(self.hass, DOMAIN, ISSUE_PENDING_DEVICES)

    def revoke_device(self, device_id):
        if device_id in self.device_keys:
            self.device_keys.pop(device_id, None)
            self._persist()
            self._notify_stats_changed()

    def _notify_stats_changed(self):
        async_dispatcher_send(self.hass, SIGNAL_HUB_STATS_UPDATE)

    def _persist(self):
        data = {
            "pairing_key": self.pairing_key,
            "device_keys": self.device_keys,
            "pending_devices": self.pending_devices,
        }
        self.hass.config_entries.async_update_entry(self.entry, data=data)


    async def async_device_connected(self, device_id, hello):
        model = hello.get("model")
        sw_version = hello.get("sw_version")
        self.devices.setdefault(device_id, {})
        self.devices[device_id]["sw_version"] = sw_version
        self.devices[device_id]["model"] = model

        dev_reg = dr.async_get(self.hass)
        hub_device = dev_reg.async_get_device_by_identifier((DOMAIN, HUB_IDENTIFIER), self.entry.entry_id)
        dev_reg.async_get_or_create(
            config_entry_id=self.entry.entry_id,
            identifiers={(DOMAIN, device_id)},
            name=device_id,
            manufacturer="Henrik Isefjær Olsen",
            model=model,
            sw_version=sw_version,
            via_device_id=hub_device.id if hub_device else None,
        )
        _LOGGER.info("TuxD device connected: %s", device_id)
        self._notify_stats_changed()

    def async_set_ws(self, device_id, ws):
        self.devices.setdefault(device_id, {})["ws"] = ws

    def async_device_disconnected(self, device_id):
        self.devices.pop(device_id, None)
        _LOGGER.info("TuxD device disconnected: %s", device_id)
        for uid, entry in self.entities.items():
            if entry.get("device_id") == device_id:
                async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATE.format(unique_id=uid))
        self._notify_stats_changed()


    async def async_handle_message(self, device_id, raw):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        mtype = msg.get("type")
        if mtype == "discovery":
            self._handle_discovery(device_id, msg)
        elif mtype == "discovery_clear":
            self._handle_discovery_clear(device_id, msg)
        elif mtype == "state":
            self._handle_state(device_id, msg)
        elif mtype == "ping":
            ws = self.devices.get(device_id, {}).get("ws")
            if ws is not None:
                await ws.send_str(json.dumps({"type": "pong"}))

    def _owns_key(self, device_id, key):
        return key == f"tuxd/{device_id}" or key.startswith(f"tuxd/{device_id}/")

    def _handle_discovery(self, device_id, msg):
        domain = msg.get("domain")
        object_id = msg.get("object_id")
        config = msg.get("config") or {}
        if not domain or not object_id:
            return
        if domain not in PLATFORMS:
            _LOGGER.warning(
                "TuxD: device %s tried to register unsupported domain %s - ignored",
                device_id, domain,
            )
            return
        unique_id = config.get("unique_id") or f"{device_id}_{object_id}"
        if unique_id != device_id and not unique_id.startswith(f"{device_id}_"):
            _LOGGER.warning(
                "TuxD: device %s tried to register entity %s outside its own namespace - ignored",
                device_id, unique_id,
            )
            return

        state_topic = config.get("state_topic") or config.get("stat_t")
        attrs_topic = config.get("json_attributes_topic")
        for topic in (state_topic, attrs_topic):
            if topic and not self._owns_key(device_id, topic):
                _LOGGER.warning(
                    "TuxD: device %s tried to register topic %s outside its own namespace - ignored",
                    device_id, topic,
                )
                return

        existing = self.entities.get(unique_id)
        if existing is not None and existing.get("device_id") not in (None, device_id):
            _LOGGER.warning(
                "TuxD: device %s tried to claim entity %s already owned by %s - ignored",
                device_id, unique_id, existing.get("device_id"),
            )
            return

        is_new = existing is None
        entry = self.entities.setdefault(unique_id, {"state": None, "attributes": {}})
        entry["domain"] = domain
        entry["object_id"] = object_id
        entry["device_id"] = device_id
        entry["config"] = config

        if state_topic:
            self.key_to_unique_ids.setdefault(state_topic, set()).add(unique_id)
        if attrs_topic:
            self.key_to_unique_ids.setdefault(attrs_topic, set()).add(unique_id)

        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_NEW_ENTITY.format(domain=domain), unique_id)
        else:
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATE.format(unique_id=unique_id))
        if object_id in ("system_error", "host_update", "self_update"):
            self._notify_stats_changed()

    def _handle_discovery_clear(self, device_id, msg):
        domain = msg.get("domain")
        object_id = msg.get("object_id")
        stale = [
            uid for uid, e in self.entities.items()
            if e.get("domain") == domain and e.get("object_id") == object_id
            and e.get("device_id") == device_id
        ]
        for uid in stale:
            self.entities.pop(uid, None)
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATE.format(unique_id=uid))
        if object_id in ("system_error", "host_update", "self_update"):
            self._notify_stats_changed()

    def _handle_state(self, device_id, msg):
        key = msg.get("key")
        value = msg.get("value")
        if not key or not self._owns_key(device_id, key):
            _LOGGER.warning(
                "TuxD: device %s tried to publish state for %s outside its own namespace - ignored",
                device_id, key,
            )
            return
        for uid in self.key_to_unique_ids.get(key, ()):
            entry = self.entities.get(uid)
            if not entry or entry.get("device_id") != device_id:
                continue
            cfg = entry.get("config", {})
            if cfg.get("json_attributes_topic") == key:
                try:
                    entry["attributes"] = json.loads(value)
                except Exception:
                    pass
            else:
                entry["state"] = value
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATE.format(unique_id=uid))
            if entry.get("object_id") in ("system_error", "host_update", "self_update"):
                self._notify_stats_changed()


    def send_command(self, device_id, key, payload):
        info = self.devices.get(device_id)
        if not info or "ws" not in info:
            _LOGGER.warning("TuxD: cannot send command, %s is not connected", device_id)
            return
        ws = info["ws"]
        asyncio.create_task(ws.send_str(json.dumps({"type": "command", "key": key, "payload": payload})))
