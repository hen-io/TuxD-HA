from homeassistant.components.text import TextEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW_ENTITY
from .entity import TuxdEntity

_DOMAIN_KEY = "text"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    added = set()

    @callback
    def _add(unique_id):
        if unique_id in added:
            return
        added.add(unique_id)
        async_add_entities([TuxdText(hub, unique_id)])

    for uid, e in list(hub.entities.items()):
        if e.get("domain") == _DOMAIN_KEY:
            _add(uid)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_ENTITY.format(domain=_DOMAIN_KEY), _add)
    )


class TuxdText(TuxdEntity, TextEntity):
    @property
    def native_value(self):
        return self._entry.get("state")

    async def async_set_value(self, value: str) -> None:
        command_topic = self._config.get("command_topic") or self._config.get("cmd_t")
        self._send_command(command_topic, value)
