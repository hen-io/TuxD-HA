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
            return self.async_create_entry(title="TuxD", data={"pairing_key": self._pairing_key})

        self._pairing_key = secrets.token_hex(32)
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({}),
            description_placeholders={"pairing_key": self._pairing_key},
        )

    async def async_step_reconfigure(self, user_input=None):
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            new_data = dict(entry.data)
            new_data["pairing_key"] = self._pairing_key
            self.hass.config_entries.async_update_entry(entry, data=new_data)
            return self.async_abort(reason="reconfigure_successful")

        self._pairing_key = secrets.token_hex(32)
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema({}),
            description_placeholders={"pairing_key": self._pairing_key},
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return TuxdOptionsFlow()


class TuxdOptionsFlow(config_entries.OptionsFlow):

    def _hub(self):
        return self.hass.data[DOMAIN][self.config_entry.entry_id]

    async def async_step_init(self, user_input=None):
        hub = self._hub()

        if user_input is not None:
            return await self._apply(hub, user_input)

        if not hub.pending_devices and not hub.device_keys:
            return self.async_show_form(
                step_id="no_pending", data_schema=vol.Schema({}),
                description_placeholders={"pairing_key": hub.pairing_key},
            )

        return self.async_show_form(
            step_id="init",
            data_schema=self._schema(hub),
            description_placeholders={"pairing_key": hub.pairing_key},
        )

    def _schema(self, hub):
        pending = hub.pending_devices
        approved = hub.device_keys
        fields = {}

        if pending:
            pending_choices = {
                device_id: f"{device_id} (model: {info.get('model') or 'unknown'}, "
                           f"version: {info.get('sw_version') or 'unknown'})"
                for device_id, info in pending.items()
            }
            trust_choices = {
                device_id: pending_choices[device_id]
                for device_id, info in pending.items()
                if info.get("presented_key") and info["presented_key"] != hub.pairing_key
            }
            fields[vol.Optional("approve", default=[])] = cv.multi_select(pending_choices)
            if trust_choices:
                fields[vol.Optional("trust", default=[])] = cv.multi_select(trust_choices)
            fields[vol.Optional("reject", default=[])] = cv.multi_select(pending_choices)

        if approved:
            approved_choices = {device_id: device_id for device_id in approved}
            fields[vol.Optional("rotate", default=[])] = cv.multi_select(approved_choices)
            fields[vol.Optional("revoke", default=[])] = cv.multi_select(approved_choices)

        manual_choices = {}
        manual_choices.update({d: f"{d} (pending)" for d in pending})
        manual_choices.update({d: f"{d} (approved)" for d in approved})
        if manual_choices:
            fields[vol.Optional("manual_key_device")] = vol.In(manual_choices)
            fields[vol.Optional("manual_key_value")] = str

        return vol.Schema(fields)

    async def _apply(self, hub, user_input):
        issued = {}

        for device_id in user_input.get("approve") or []:
            new_key = hub.approve_device(device_id)
            if new_key:
                issued[device_id] = new_key

        for device_id in user_input.get("trust") or []:
            hub.trust_device_key(device_id)

        for device_id in user_input.get("reject") or []:
            hub.reject_device(device_id)

        for device_id in user_input.get("rotate") or []:
            new_key = hub.rotate_device_key(device_id)
            if new_key:
                issued[device_id] = new_key

        for device_id in user_input.get("revoke") or []:
            hub.revoke_device(device_id)

        manual_device = user_input.get("manual_key_device")
        manual_value = (user_input.get("manual_key_value") or "").strip()
        if bool(manual_device) != bool(manual_value):
            return self.async_show_form(
                step_id="init", data_schema=self._schema(hub),
                description_placeholders={"pairing_key": hub.pairing_key},
                errors={"manual_key_value": "key_required"},
            )
        if manual_device and manual_value:
            ok, reason = hub.set_device_key(manual_device, manual_value)
            if not ok:
                return self.async_show_form(
                    step_id="init", data_schema=self._schema(hub),
                    description_placeholders={"pairing_key": hub.pairing_key},
                    errors={"manual_key_value": "key_collision" if reason == "collision" else "key_required"},
                )

        if issued:
            return await self.async_step_issued(issued=issued)
        return self.async_create_entry(title="", data={})

    async def async_step_no_pending(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        hub = self._hub()
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
