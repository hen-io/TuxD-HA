from homeassistant.components.switch import SwitchEntity

from .const import DOMAIN
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "switch"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdSwitch, hub)


class TuxdSwitch(TuxdEntity, SwitchEntity):
    @property
    def is_on(self):
        return self._entry.get("state") == self._config.get("payload_on", "ON")

    async def async_turn_on(self, **kwargs) -> None:
        self._send_command(self._config.get("command_topic"), self._config.get("payload_on", "ON"))

    async def async_turn_off(self, **kwargs) -> None:
        self._send_command(self._config.get("command_topic"), self._config.get("payload_off", "OFF"))
