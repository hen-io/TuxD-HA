from homeassistant.components.button import ButtonEntity

from .const import DOMAIN
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "button"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdButton, hub)


class TuxdButton(TuxdEntity, ButtonEntity):
    async def async_press(self) -> None:
        self._send_command(self._config.get("command_topic"), "PRESS")
