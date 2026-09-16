import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers.device_registry import DeviceEntryType

from .const import DOMAIN, HUB_IDENTIFIER, ISSUE_PENDING_DEVICES, PLATFORMS
from .hub import TuxdHub
from .websocket_view import TuxdWebSocketView

_LOGGER = logging.getLogger(__name__)

_VIEW_KEY = f"{DOMAIN}_ws_view"


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hub = TuxdHub(hass, entry)
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = hub

    dev_reg = dr.async_get(hass)
    dev_reg.async_get_or_create(
        config_entry_id=entry.entry_id,
        identifiers={(DOMAIN, HUB_IDENTIFIER)},
        name="TuxD",
        manufacturer="Henrik Isefjær Olsen",
        model="TuxD Home Assistant Integration",
        entry_type=DeviceEntryType.SERVICE,
    )

    view = hass.data.get(_VIEW_KEY)
    if view is None:
        view = TuxdWebSocketView(hub)
        hass.http.register_view(view)
        hass.data[_VIEW_KEY] = view
    else:
        view.hub = hub

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        ir.async_delete_issue(hass, DOMAIN, ISSUE_PENDING_DEVICES)
    return unloaded


async def async_remove_config_entry_device(
    hass: HomeAssistant, entry: ConfigEntry, device_entry: dr.DeviceEntry
) -> bool:
    hub = hass.data[DOMAIN][entry.entry_id]
    for domain, identifier in device_entry.identifiers:
        if domain != DOMAIN:
            continue
        if identifier == HUB_IDENTIFIER:
            return False
        hub.remove_device(identifier)
    return True
