import json

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature

from .const import DOMAIN, ENTITY_PICTURE_LOGO_BORDER
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "update"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdUpdate, hub)


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
        features = UpdateEntityFeature.PROGRESS
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

    @property
    def entity_picture(self):
        if (self._entry.get("object_id") or "").startswith("docker_image_"):
            return None
        return ENTITY_PICTURE_LOGO_BORDER

    async def async_install(self, version, backup: bool, **kwargs) -> None:
        command_topic = self._config.get("command_topic")
        payload = self._config.get("payload_install", "INSTALL")
        self._send_command(command_topic, payload)
