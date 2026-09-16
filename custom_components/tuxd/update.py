import json

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW_ENTITY
from .entity import TuxdEntity

_DOMAIN_KEY = "update"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    added = set()

    @callback
    def _add(unique_id):
        if unique_id in added:
            return
        added.add(unique_id)
        async_add_entities([TuxdUpdate(hub, unique_id)])

    for uid, e in list(hub.entities.items()):
        if e.get("domain") == _DOMAIN_KEY:
            _add(uid)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_ENTITY.format(domain=_DOMAIN_KEY), _add)
    )


class TuxdUpdate(TuxdEntity, UpdateEntity):
    @property
    def _state_json(self):
        raw = self._entry.get("state")
        if isinstance(raw, str):
            try:
                data = json.loads(raw)
                if isinstance(data, dict):
                    return data
            except Exception:
                pass
        return None

    @property
    def supported_features(self):
        features = UpdateEntityFeature(0)
        if self._config.get("command_topic"):
            features |= UpdateEntityFeature.INSTALL
        return features

    @property
    def installed_version(self):
        data = self._state_json
        if data is not None:
            return data.get("installed_version")
        return None

    @property
    def latest_version(self):
        data = self._state_json
        if data is not None:
            return data.get("latest_version")
        raw = self._entry.get("state")
        return "update available" if raw == "ON" else self.installed_version

    @property
    def in_progress(self):
        data = self._state_json
        if data is not None:
            return bool(data.get("in_progress"))
        return False

    @property
    def release_summary(self):
        data = self._state_json
        return data.get("release_summary") if data is not None else None

    @property
    def release_url(self):
        data = self._state_json
        return data.get("release_url") if data is not None else None

    @property
    def device_class(self):
        return self._config.get("device_class")

    async def async_install(self, version, backup: bool, **kwargs) -> None:
        command_topic = self._config.get("command_topic")
        payload = self._config.get("payload_install", "INSTALL")
        self._send_command(command_topic, payload)
