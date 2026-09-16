from homeassistant.components.number import NumberEntity

from .const import DOMAIN
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "number"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdNumber, hub)


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
