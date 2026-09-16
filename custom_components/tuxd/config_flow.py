import secrets

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN


class TuxdConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")

        if user_input is not None:
            return self.async_create_entry(title="TuxD", data={"api_key": self._pairing_key})

        self._pairing_key = secrets.token_hex(32)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={"api_key": self._pairing_key},
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            new_data = dict(entry.data)
            new_data["api_key"] = self._pairing_key
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            return self.async_abort(reason="reconfigure_successful")

        self._pairing_key = secrets.token_hex(32)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({}),
            description_placeholders={"api_key": self._pairing_key},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return TuxdOptionsFlow()


class TuxdOptionsFlow(config_entries.OptionsFlow):

    async def async_step_init(self, user_input=None):
        hub = self.hass.data[DOMAIN][self.config_entry.entry_id]

        if user_input is not None:
            approve = user_input.get("approve") or []
            reject = user_input.get("reject") or []
            issued = {}
            for device_id in approve:
                new_key = hub.approve_device(device_id)
                if new_key:
                    issued[device_id] = new_key
            for device_id in reject:
                hub.reject_device(device_id)
            if issued:
                return await self.async_step_issued(issued=issued)
            return self.async_create_entry(title="", data={})

        pending = hub.pending_devices
        if not pending:
            return self.async_show_form(
                step_id="no_pending", data_schema=vol.Schema({}),
                description_placeholders={"pairing_key": hub.pairing_key},
            )

        choices = {
            device_id: f"{device_id} (model: {info.get('model') or 'unknown'}, "
                       f"version: {info.get('sw_version') or 'unknown'})"
            for device_id, info in pending.items()
        }
        schema = vol.Schema({
            vol.Optional("approve", default=[]): cv.multi_select(choices),
            vol.Optional("reject", default=[]): cv.multi_select(choices),
        })
        return self.async_show_form(
            step_id="init", data_schema=schema,
            description_placeholders={"pairing_key": hub.pairing_key},
        )

    async def async_step_no_pending(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        hub = self.hass.data[DOMAIN][self.config_entry.entry_id]
        return self.async_show_form(
            step_id="no_pending", data_schema=vol.Schema({}),
            description_placeholders={"pairing_key": hub.pairing_key},
        )

    async def async_step_issued(self, user_input=None, issued=None):
        if issued is not None:
            self._issued = issued
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        lines = "\n".join(f"- **{d}**: `{k}`" for d, k in self._issued.items())
        return self.async_show_form(
            step_id="issued",
            data_schema=vol.Schema({}),
            description_placeholders={"keys": lines},
        )
