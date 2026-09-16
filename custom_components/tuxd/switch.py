from homeassistant.components.switch import SwitchEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW_ENTITY
from .entity import TuxdEntity

_DOMAIN_KEY = "switch"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    added = set()

    @callback
    def _add(unique_id):
        if unique_id in added:
            return
        added.add(unique_id)
        async_add_entities([TuxdSwitch(hub, unique_id)])

    for uid, e in list(hub.entities.items()):
        if e.get("domain") == _DOMAIN_KEY:
            _add(uid)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_ENTITY.format(domain=_DOMAIN_KEY), _add)
    )


class TuxdSwitch(TuxdEntity, SwitchEntity):
    @property
    def is_on(self):
        return self._entry.get("state") == self._config.get("payload_on", "ON")

    async def async_turn_on(self, **kwargs) -> None:
        self._send_command(self._config.get("command_topic"), self._config.get("payload_on", "ON"))

    async def async_turn_off(self, **kwargs) -> None:
        self._send_command(self._config.get("command_topic"), self._config.get("payload_off", "OFF"))
