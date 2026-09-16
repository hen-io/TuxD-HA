from homeassistant.components.text import TextEntity

from .const import DOMAIN
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "text"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdText, hub)


class TuxdText(TuxdEntity, TextEntity):
    @property
    def native_value(self):
        return self._entry.get("state")

    async def async_set_value(self, value: str) -> None:
        command_topic = self._config.get("command_topic") or self._config.get("cmd_t")
        self._send_command(command_topic, value)
