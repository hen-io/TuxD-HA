import asyncio
import json

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN

SERVICE_RUN_ACTION = "run_action"


def _hub(hass):
    hubs = hass.data.get(DOMAIN) or {}
    return next(iter(hubs.values()), None)


async def async_run_action(hass, device_id, integration, action, target=None, password=None):
    hub = _hub(hass)
    if hub is None:
        return {"ok": False, "error": "TuxD is not set up"}
    request = {"integration": integration, "action": action}
    if target:
        request["target"] = target
    return await hub.async_device_request(device_id, "run_action", json.dumps(request), password=password)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/action/run",
    vol.Required("device_id"): str,
    vol.Required("integration"): str,
    vol.Required("action"): str,
    vol.Optional("target"): str,
    vol.Optional("password"): str,
})
@websocket_api.async_response
async def _ws_run(hass, connection, msg):
    result = await async_run_action(hass, msg["device_id"], msg["integration"], msg["action"],
                                    msg.get("target"), msg.get("password"))
    connection.send_result(msg["id"], result)


@websocket_api.require_admin
@websocket_api.websocket_command({
    vol.Required("type"): "tuxd/action/run_multi",
    vol.Required("device_ids"): [str],
    vol.Required("integration"): str,
    vol.Required("action"): str,
    vol.Optional("target"): str,
    vol.Optional("password"): str,
    vol.Optional("master_password"): str,
})
@websocket_api.async_response
async def _ws_run_multi(hass, connection, msg):
    hub = _hub(hass)
    if hub is None:
        connection.send_result(msg["id"], {"ok": False, "error": "TuxD is not set up"})
        return
    given = msg.get("master_password")
    if not await hub.check_master(given):
        connection.send_result(msg["id"], {
            "ok": False, "master": "incorrect" if given else "required",
            "error": "Incorrect master password" if given else "Master password required",
        })
        return
    device_ids = list(dict.fromkeys(msg["device_ids"]))
    password = msg.get("password") or given
    results = await asyncio.gather(*[
        async_run_action(hass, d, msg["integration"], msg["action"], msg.get("target"), password) for d in device_ids
    ])
    connection.send_result(msg["id"], {"ok": all(r.get("ok") for r in results), "results": dict(zip(device_ids, results))})


_SERVICE_SCHEMA = vol.Schema({
    vol.Required("device_id"): cv.string,
    vol.Required("integration"): cv.string,
    vol.Required("action"): cv.string,
    vol.Optional("target"): cv.string,
    vol.Optional("password"): cv.string,
})


@callback
def async_setup_actions(hass: HomeAssistant) -> None:
    websocket_api.async_register_command(hass, _ws_run)
    websocket_api.async_register_command(hass, _ws_run_multi)

    async def _service(call: ServiceCall) -> None:
        data = call.data
        result = await async_run_action(hass, data["device_id"], data["integration"], data["action"],
                                        data.get("target"), data.get("password"))
        if not result.get("ok"):
            raise HomeAssistantError(result.get("error") or "The action was not run")

    hass.services.async_register(DOMAIN, SERVICE_RUN_ACTION, _service, schema=_SERVICE_SCHEMA)
