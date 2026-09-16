from homeassistant.components.sensor import SensorEntity
from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, SIGNAL_NEW_ENTITY
from .entity import TuxdEntity

_DOMAIN_KEY = "sensor"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    added = set()

    @callback
    def _add(unique_id):
        if unique_id in added:
            return
        added.add(unique_id)
        async_add_entities([TuxdSensor(hub, unique_id)])

    for uid, e in list(hub.entities.items()):
        if e.get("domain") == _DOMAIN_KEY:
            _add(uid)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_NEW_ENTITY.format(domain=_DOMAIN_KEY), _add)
    )


class TuxdSensor(TuxdEntity, SensorEntity):
    @property
    def native_value(self):
        return self._entry.get("state")

    @property
    def native_unit_of_measurement(self):
        return self._config.get("unit_of_measurement")

    @property
    def state_class(self):
        return self._config.get("state_class")

    @property
    def device_class(self):
        return self._config.get("device_class")
