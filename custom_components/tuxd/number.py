from homeassistant.components.number import NumberEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW_ENTITY
from .entity import TuxdEntity

_DOMAIN_KEY = "number"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    added = set()

    @callback
    def _add(unique_id):
        if unique_id in added:
            return
        added.add(unique_id)
        async_add_entities([TuxdNumber(hub, unique_id)])

    for uid, e in list(hub.entities.items()):
        if e.get("domain") == _DOMAIN_KEY:
            _add(uid)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_ENTITY.format(domain=_DOMAIN_KEY), _add)
    )


class TuxdNumber(TuxdEntity, NumberEntity):
    @property
    def native_value(self):
        state = self._entry.get("state")
        try:
            return float(state)
        except (TypeError, ValueError):
            return None

    @property
    def native_min_value(self):
        return self._config.get("min", 0)

    @property
    def native_max_value(self):
        return self._config.get("max", 100)

    @property
    def native_step(self):
        return self._config.get("step", 1)

    @property
    def native_unit_of_measurement(self):
        return self._config.get("unit_of_measurement")

    async def async_set_native_value(self, value: float) -> None:
        self._send_command(self._config.get("command_topic"), str(value))
