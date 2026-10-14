
import asyncio

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN


def _hub(hass: HomeAssistant):
    hubs = hass.data.get(DOMAIN) or {}
    return next(iter(hubs.values()), None)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/config/get",
    vol.Required("device_id"): str,
    vol.Optional("password"): str,
})
@websocket_api.async_response
async def _get(hass, connection, msg):
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_found", "TuxD is not set up")
        return
    result = await hub.async_get_device_config(msg["device_id"], msg.get("password"))
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/config/set",
    vol.Required("device_id"): str,
    vol.Required("content"): str,
    vol.Optional("password"): str,
})
@websocket_api.async_response
async def _set(hass, connection, msg):
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_found", "TuxD is not set up")
        return
    result = await hub.async_set_device_config(msg["device_id"], msg["content"], msg.get("password"))
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/terminal/send",
    vol.Required("device_id"): str,
    vol.Optional("command", default=""): str,
    vol.Optional("stop", default=False): bool,
    vol.Optional("password"): str,
})
@websocket_api.async_response
async def _terminal_send(hass, connection, msg):
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_found", "TuxD is not set up")
        return
    connection.send_result(msg["id"], await _send_one(hub, msg["device_id"], msg, msg.get("password")))


async def _send_one(hub, device_id, msg, password):
    if msg["stop"]:
        return await hub.async_device_request(device_id, "terminal_stop", password=password)
    return await hub.async_device_request(device_id, "terminal", msg["command"], password=password)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/terminal/send_multi",
    vol.Required("device_ids"): [str],
    vol.Optional("command", default=""): str,
    vol.Optional("stop", default=False): bool,
    vol.Optional("password"): str,
    vol.Optional("master_password"): str,
})
@websocket_api.async_response
async def _terminal_send_multi(hass, connection, msg):
    hub = _hub(hass)
    if hub is None:
        connection.send_error(msg["id"], "not_found", "TuxD is not set up")
        return
    if not await hub.check_master(msg.get("master_password")):
        connection.send_result(msg["id"], {
            "ok": False, "master": "incorrect" if msg.get("master_password") else "required",
            "error": "Incorrect master password" if msg.get("master_password") else "Master password required",
        })
        return
    password = msg.get("password") or msg.get("master_password")
    results = await asyncio.gather(*[_send_one(hub, d, msg, password) for d in msg["device_ids"]])
    connection.send_result(msg["id"], {"ok": True, "results": dict(zip(msg["device_ids"], results))})


@callback
def async_setup_config_editor(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _get)
    websocket_api.async_register_command(hass, _set)
    websocket_api.async_register_command(hass, _terminal_send)
    websocket_api.async_register_command(hass, _terminal_send_multi)
