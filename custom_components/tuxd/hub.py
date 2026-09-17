import asyncio
import json
import logging
import secrets
import time
import uuid

from homeassistant.components import websocket_api
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    HUB_IDENTIFIER,
    ISSUE_PENDING_DEVICES,
    PLATFORMS,
    SIGNAL_DEVICE_APPROVED,
    SIGNAL_HUB_STATS_UPDATE,
    SIGNAL_LAST_SEEN_UPDATE,
    SIGNAL_NEW_ENTITY,
    SIGNAL_OFFLINE_UPDATE_URL_CHANGED,
    SIGNAL_REMOVE_ENTITY,
    SIGNAL_STATE_UPDATE,
    SIGNAL_THRESHOLDS_CHANGED,
    THRESHOLD_METRICS,
)

_THRESHOLD_OBJECT_IDS = frozenset(row[0] for row in THRESHOLD_METRICS)

_LOGGER = logging.getLogger(__name__)

_MAX_PENDING_DEVICES = 50


def _is_stats_relevant_object_id(object_id):
    object_id = object_id or ""
    return (
        object_id in ("system_error", "host_update", "self_update")
        or object_id in _THRESHOLD_OBJECT_IDS
        or (object_id.startswith("disk_") and object_id.endswith("_smart_errors"))
    )


class TuxdHub:

    _RECONCILE_SETTLE_SECONDS = 10.0

    def __init__(self, hass, entry):
        self.hass = hass
        self.entry = entry
        self._store = Store(hass, 1, f"{DOMAIN}_{entry.entry_id}")
        self.pairing_key = ""
        self.device_keys = {}
        self.pending_devices = {}
        self.thresholds = {}

        self.devices = {}
        self.device_last_seen = {}
        self._last_seen_dispatched = {}
        self.entities = {}
        self.key_to_unique_ids = {}
        self._device_generation = {}
        self._tty_sessions = {}
        self.offline_update_url = ""

    async def async_load(self):
        stored = await self._store.async_load()
        if stored is not None:
            self.pairing_key = stored.get("pairing_key", "")
            self.device_keys = dict(stored.get("device_keys", {}))
            self.pending_devices = dict(stored.get("pending_devices", {}))
            self.thresholds = dict(stored.get("thresholds", {}))
        else:
            self.pairing_key = self.entry.data.get("pairing_key", "")
            self.device_keys = dict(self.entry.data.get("device_keys", {}))
            self.pending_devices = dict(self.entry.data.get("pending_devices", {}))
            await self._persist()

        self._sync_pending_issue()


    def check_auth(self, device_id, presented_key):
        if not device_id or not presented_key:
            return "rejected"
        known_key = self.device_keys.get(device_id)
        if known_key is not None:
            return "ok" if secrets.compare_digest(presented_key, known_key) else "rejected"
        return "pending"

    async def record_pending(self, device_id, hello, presented_key=None):
        await self._resync()
        if device_id not in self.pending_devices and len(self.pending_devices) >= _MAX_PENDING_DEVICES:
            _LOGGER.warning(
                "TuxD: pending-devices list is full (%d) - ignoring pairing attempt from %s",
                _MAX_PENDING_DEVICES, device_id,
            )
            return
        self.pending_devices[device_id] = {
            "model": hello.get("model"),
            "sw_version": hello.get("sw_version"),
            "presented_key": presented_key,
        }
        await self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s is awaiting approval", device_id)

    async def approve_device(self, device_id):
        await self._resync()
        if device_id not in self.pending_devices:
            return None
        new_key = secrets.token_hex(32)
        self.device_keys[device_id] = new_key
        self.pending_devices.pop(device_id, None)
        await self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s approved and issued its own key", device_id)
        self._notify_stats_changed()
        async_dispatcher_send(self.hass, SIGNAL_DEVICE_APPROVED, device_id)
        return new_key

    async def trust_device_key(self, device_id):
        await self._resync()
        info = self.pending_devices.get(device_id)
        if not info:
            return None
        presented_key = info.get("presented_key")
        if not presented_key or presented_key == self.pairing_key:
            return None
        self.device_keys[device_id] = presented_key
        self.pending_devices.pop(device_id, None)
        await self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s approved, trusting the key it already presented", device_id)
        self._notify_stats_changed()
        async_dispatcher_send(self.hass, SIGNAL_DEVICE_APPROVED, device_id)
        return presented_key

    async def set_device_key(self, device_id, key):
        await self._resync()
        key = (key or "").strip()
        if not key:
            return False, "empty"
        for other_id, other_key in self.device_keys.items():
            if other_id != device_id and secrets.compare_digest(other_key, key):
                return False, "collision"
        self.device_keys[device_id] = key
        self.pending_devices.pop(device_id, None)
        await self._persist()
        self._sync_pending_issue()
        _LOGGER.info("TuxD: device %s given a manually-set key", device_id)
        self._notify_stats_changed()
        async_dispatcher_send(self.hass, SIGNAL_DEVICE_APPROVED, device_id)
        return True, None

    async def rotate_device_key(self, device_id):
        await self._resync()
        if device_id not in self.device_keys:
            return None
        new_key = secrets.token_hex(32)
        self.device_keys[device_id] = new_key
        await self._persist()
        _LOGGER.info("TuxD: device %s issued a new key", device_id)
        return new_key

    async def reject_device(self, device_id):
        await self._resync()
        if device_id in self.pending_devices:
            self.pending_devices.pop(device_id, None)
            await self._persist()
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

    async def revoke_device(self, device_id):
        await self._resync()
        if device_id in self.device_keys:
            self.device_keys.pop(device_id, None)
            await self._persist()
            self._notify_stats_changed()

    async def remove_device(self, device_id):
        await self.revoke_device(device_id)
        self.device_last_seen.pop(device_id, None)
        if device_id in self.pending_devices:
            self.pending_devices.pop(device_id, None)
            await self._persist()
            self._sync_pending_issue()

        info = self.devices.pop(device_id, None)
        if info and info.get("ws") is not None:
            asyncio.create_task(info["ws"].close())

        stale = [(uid, e.get("domain")) for uid, e in self.entities.items() if e.get("device_id") == device_id]
        for uid, domain in stale:
            self.entities.pop(uid, None)
            if domain:
                async_dispatcher_send(self.hass, SIGNAL_REMOVE_ENTITY.format(domain=domain), uid)
        for uids in self.key_to_unique_ids.values():
            uids.difference_update(uid for uid, _domain in stale)

        self._notify_stats_changed()

    _LAST_SEEN_DISPATCH_MIN_INTERVAL = 60.0

    def _touch_last_seen(self, device_id):
        self.device_last_seen[device_id] = dt_util.utcnow()
        now = time.monotonic()
        last_dispatch = self._last_seen_dispatched.get(device_id, 0.0)
        if now - last_dispatch < self._LAST_SEEN_DISPATCH_MIN_INTERVAL:
            return
        self._last_seen_dispatched[device_id] = now
        async_dispatcher_send(self.hass, SIGNAL_LAST_SEEN_UPDATE.format(device_id=device_id))

    def _notify_stats_changed(self):
        async_dispatcher_send(self.hass, SIGNAL_HUB_STATS_UPDATE)

    async def _resync(self):
        fresh_store = Store(self.hass, 1, f"{DOMAIN}_{self.entry.entry_id}")
        stored = await fresh_store.async_load()
        if stored is not None:
            self.pairing_key = stored.get("pairing_key", self.pairing_key)
            self.device_keys = dict(stored.get("device_keys", self.device_keys))
            self.pending_devices = dict(stored.get("pending_devices", self.pending_devices))
            self.thresholds = dict(stored.get("thresholds", self.thresholds))

    async def _persist(self):
        data = {
            "pairing_key": self.pairing_key,
            "device_keys": self.device_keys,
            "pending_devices": self.pending_devices,
            "thresholds": self.thresholds,
        }
        await self._store.async_save(data)


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
        self._touch_last_seen(device_id)

        self._device_generation[device_id] = self._device_generation.get(device_id, 0) + 1
        self.hass.async_create_task(
            self._reconcile_device_entities(device_id, self._device_generation[device_id])
        )

        self._notify_stats_changed()

    async def _reconcile_device_entities(self, device_id, generation):
        await asyncio.sleep(self._RECONCILE_SETTLE_SECONDS)
        if self._device_generation.get(device_id) != generation:
            return

        stale = [
            (uid, e.get("domain")) for uid, e in self.entities.items()
            if e.get("device_id") == device_id and e.get("_generation") != generation
        ]
        for uid, domain in stale:
            self.entities.pop(uid, None)
            if domain:
                async_dispatcher_send(self.hass, SIGNAL_REMOVE_ENTITY.format(domain=domain), uid)
        for uids in self.key_to_unique_ids.values():
            uids.difference_update(uid for uid, _domain in stale)
        removed = len(stale)

        dev_reg = dr.async_get(self.hass)
        device_entry = dev_reg.async_get_device_by_identifier((DOMAIN, device_id), self.entry.entry_id)
        if device_entry is not None:
            ent_reg = er.async_get(self.hass)
            confirmed = {
                uid for uid, e in self.entities.items()
                if e.get("device_id") == device_id and e.get("_generation") == generation
            }
            for reg_entry in list(er.async_entries_for_device(ent_reg, device_entry.id, include_disabled_entities=True)):
                if reg_entry.unique_id not in confirmed:
                    ent_reg.async_remove(reg_entry.entity_id)
                    removed += 1

        if removed:
            _LOGGER.info(
                "TuxD: device %s no longer announces %d entit%s - removed",
                device_id, removed, "y" if removed == 1 else "ies",
            )
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

        for session_id, info in list(self._tty_sessions.items()):
            if info["device_id"] == device_id:
                self._tty_sessions.pop(session_id, None)
                info["connection"].send_message(
                    websocket_api.event_message(info["msg_id"], {"type": "tty_exit", "code": -1})
                )


    def tty_open(self, device_id, connection, msg_id, cols, rows):
        info = self.devices.get(device_id)
        if not info or "ws" not in info:
            return None
        session_id = uuid.uuid4().hex[:12]
        self._tty_sessions[session_id] = {
            "device_id": device_id, "connection": connection, "msg_id": msg_id,
        }
        ws = info["ws"]
        asyncio.create_task(ws.send_str(json.dumps({
            "type": "tty_open", "session": session_id, "cols": cols, "rows": rows,
        })))
        return session_id

    def tty_input(self, session_id, data):
        self._tty_send(session_id, {"type": "tty_input", "session": session_id, "data": data})

    def tty_resize(self, session_id, cols, rows):
        self._tty_send(session_id, {"type": "tty_resize", "session": session_id, "cols": cols, "rows": rows})

    def tty_close(self, session_id):
        self._tty_send(session_id, {"type": "tty_close", "session": session_id})
        self._tty_sessions.pop(session_id, None)

    def _tty_send(self, session_id, obj):
        info = self._tty_sessions.get(session_id)
        if not info:
            return
        dev = self.devices.get(info["device_id"])
        if not dev or "ws" not in dev:
            return
        asyncio.create_task(dev["ws"].send_str(json.dumps(obj)))

    def _handle_tty_data(self, device_id, msg):
        session_id = msg.get("session")
        info = self._tty_sessions.get(session_id)
        if not info or info["device_id"] != device_id:
            return
        info["connection"].send_message(
            websocket_api.event_message(info["msg_id"], {"type": "tty_data", "data": msg.get("data", "")})
        )

    def _handle_tty_exit(self, device_id, msg):
        session_id = msg.get("session")
        info = self._tty_sessions.pop(session_id, None)
        if not info or info["device_id"] != device_id:
            return
        info["connection"].send_message(
            websocket_api.event_message(info["msg_id"], {"type": "tty_exit", "code": msg.get("code", -1)})
        )


    async def async_handle_message(self, device_id, raw):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        self._touch_last_seen(device_id)

        mtype = msg.get("type")
        if mtype == "discovery":
            self._handle_discovery(device_id, msg)
        elif mtype == "discovery_clear":
            self._handle_discovery_clear(device_id, msg)
        elif mtype == "state":
            self._handle_state(device_id, msg)
        elif mtype == "tty_data":
            self._handle_tty_data(device_id, msg)
        elif mtype == "tty_exit":
            self._handle_tty_exit(device_id, msg)
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
        entry["_generation"] = self._device_generation.get(device_id, 0)

        if state_topic:
            self.key_to_unique_ids.setdefault(state_topic, set()).add(unique_id)
        if attrs_topic:
            self.key_to_unique_ids.setdefault(attrs_topic, set()).add(unique_id)

        if is_new:
            async_dispatcher_send(self.hass, SIGNAL_NEW_ENTITY.format(domain=domain), unique_id)
        else:
            async_dispatcher_send(self.hass, SIGNAL_STATE_UPDATE.format(unique_id=unique_id))
        if _is_stats_relevant_object_id(object_id):
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
            async_dispatcher_send(self.hass, SIGNAL_REMOVE_ENTITY.format(domain=domain), uid)
        for uids in self.key_to_unique_ids.values():
            uids.difference_update(stale)
        if _is_stats_relevant_object_id(object_id):
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
            if _is_stats_relevant_object_id(entry.get("object_id") or ""):
                self._notify_stats_changed()


    def send_command(self, device_id, key, payload):
        info = self.devices.get(device_id)
        if not info or "ws" not in info:
            _LOGGER.warning("TuxD: cannot send command, %s is not connected", device_id)
            return
        ws = info["ws"]
        asyncio.create_task(ws.send_str(json.dumps({"type": "command", "key": key, "payload": payload})))

    _FLEET_COMMAND_STAGGER_SECONDS = 2.0

    async def _send_staggered(self, topic_suffix, payload="PRESS"):
        for device_id in list(self.devices.keys()):
            self.send_command(device_id, f"tuxd/{device_id}/{topic_suffix}/set", payload)
            await asyncio.sleep(self._FLEET_COMMAND_STAGGER_SECONDS)

    def restart_all_devices(self):
        self.hass.async_create_task(self._send_staggered("restart"))

    def refresh_all_devices(self):
        self.hass.async_create_task(self._send_staggered("force_poll"))

    def set_offline_update_url(self, url):
        self.offline_update_url = (url or "").strip()
        async_dispatcher_send(self.hass, SIGNAL_OFFLINE_UPDATE_URL_CHANGED)

    def update_all_devices(self):
        if self.offline_update_url:
            self.hass.async_create_task(
                self._send_staggered("self_update/install_from_url", payload=self.offline_update_url)
            )
        else:
            self.hass.async_create_task(self._send_staggered("self_update"))

    def check_host_updates_all_devices(self):
        self.hass.async_create_task(self._send_staggered("host_update/check"))

    async def set_threshold(self, key, value):
        self.thresholds[key] = value
        await self._persist()
        async_dispatcher_send(self.hass, SIGNAL_THRESHOLDS_CHANGED)
