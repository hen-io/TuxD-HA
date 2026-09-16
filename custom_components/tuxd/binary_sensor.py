from homeassistant.components.binary_sensor import BinarySensorEntity

from .const import DOMAIN
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "binary_sensor"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdBinarySensor, hub)


class TuxdBinarySensor(TuxdEntity, BinarySensorEntity):
    @property
    def is_on(self):
        state = self._entry.get("state")
        payload_on = self._config.get("payload_on", "ON")
        return state == payload_on

    @property
    def device_class(self):
        return self._config.get("device_class")
