import json

from homeassistant.components.update import UpdateEntity, UpdateEntityFeature

from .const import DOMAIN, ENTITY_PICTURE_LOGO
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
        if self._full_summary:
            features |= UpdateEntityFeature.RELEASE_NOTES
        return features

    @property
    def _full_summary(self):
        data = self._state_json
        summary = data.get("release_summary") if data is not None else None
        return summary if isinstance(summary, str) and summary.strip() else None

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

    _SUMMARY_LIMIT = 255

    @property
    def release_summary(self):
        full = self._full_summary
        if full is None:
            return None
        lines = [line for line in full.splitlines() if line.strip()]
        if len("\n".join(lines)) <= self._SUMMARY_LIMIT:
            return "\n".join(lines)
        kept, used = [], 0
        for i, line in enumerate(lines):
            tail = f"\n+{len(lines) - i} more (see release notes)"
            if used + len(line) + (1 if kept else 0) + len(tail) > self._SUMMARY_LIMIT:
                break
            used += len(line) + (1 if kept else 0)
            kept.append(line)
        if not kept:
            return lines[0][: self._SUMMARY_LIMIT - 1] + "…"
        return "\n".join(kept) + f"\n+{len(lines) - len(kept)} more (see release notes)"

    async def async_release_notes(self):
        return self._full_summary

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
        return ENTITY_PICTURE_LOGO

    async def async_install(self, version, backup: bool, **kwargs) -> None:
        command_topic = self._config.get("command_topic")
        payload = self._config.get("payload_install", "INSTALL")
        self._send_command(command_topic, payload)
