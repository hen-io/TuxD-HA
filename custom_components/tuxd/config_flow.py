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

        if not hub.pending_devices and not hub.device_keys:
            return self.async_show_form(
                step_id="no_pending", data_schema=vol.Schema({}),
                description_placeholders={"pairing_key": hub.pairing_key},
            )

        menu_options = []
        if hub.pending_devices:
            menu_options.append("pending")
        if hub.device_keys:
            menu_options.append("manage")
            menu_options.append("view_keys")
        menu_options.append("manual_key")

        return self.async_show_menu(
            step_id="init",
            menu_options=menu_options,
            description_placeholders={
                "pairing_key": hub.pairing_key,
                "pending_summary": self._pending_summary(hub),
            },
        )

    def _pending_summary(self, hub):
        if not hub.pending_devices:
            return "No new devices are currently awaiting approval."
        lines = [
            f"- **{device_id}** (model: {info.get('model') or 'unknown'}, "
            f"version: {info.get('sw_version') or 'unknown'})"
            for device_id, info in hub.pending_devices.items()
        ]
        return "New devices awaiting approval:\n" + "\n".join(lines)


    async def async_step_pending(self, user_input=None):
        hub = self._hub()

        if user_input is not None:
            issued = {}
            for device_id in user_input.get("approve") or []:
                new_key = await hub.approve_device(device_id)
                if new_key:
                    issued[device_id] = new_key
            for device_id in user_input.get("trust") or []:
                await hub.trust_device_key(device_id)
            for device_id in user_input.get("reject") or []:
                await hub.reject_device(device_id)
            if issued:
                return await self.async_step_issued(issued=issued)
            return self.async_create_entry(title="", data={})

        pending = hub.pending_devices
        if not pending:
            return self.async_create_entry(title="", data={})

        choices = {
            device_id: f"{device_id} (model: {info.get('model') or 'unknown'}, "
                       f"version: {info.get('sw_version') or 'unknown'})"
            for device_id, info in pending.items()
        }
        trust_choices = {
            device_id: choices[device_id]
            for device_id, info in pending.items()
            if info.get("presented_key") and info["presented_key"] != hub.pairing_key
        }
        fields = {vol.Optional("approve", default=[]): cv.multi_select(choices)}
        if trust_choices:
            fields[vol.Optional("trust", default=[])] = cv.multi_select(trust_choices)
        fields[vol.Optional("reject", default=[])] = cv.multi_select(choices)

        return self.async_show_form(
            step_id="pending", data_schema=vol.Schema(fields),
            description_placeholders={"pairing_key": hub.pairing_key},
        )


    async def async_step_manage(self, user_input=None):
        hub = self._hub()

        if user_input is not None:
            issued = {}
            for device_id in user_input.get("rotate") or []:
                new_key = await hub.rotate_device_key(device_id)
                if new_key:
                    issued[device_id] = new_key
            for device_id in user_input.get("revoke") or []:
                await hub.revoke_device(device_id)
            if issued:
                return await self.async_step_issued(issued=issued)
            return self.async_create_entry(title="", data={})

        approved = hub.device_keys
        if not approved:
            return self.async_create_entry(title="", data={})

        choices = {device_id: device_id for device_id in approved}
        schema = vol.Schema({
            vol.Optional("rotate", default=[]): cv.multi_select(choices),
            vol.Optional("revoke", default=[]): cv.multi_select(choices),
        })
        return self.async_show_form(step_id="manage", data_schema=schema)


    async def async_step_view_keys(self, user_input=None):
        hub = self._hub()
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        if not hub.device_keys:
            return self.async_create_entry(title="", data={})
        lines = "\n".join(f"- **{d}**: `{k}`" for d, k in hub.device_keys.items())
        return self.async_show_form(
            step_id="view_keys",
            data_schema=vol.Schema({}),
            description_placeholders={"keys": lines},
        )


    async def async_step_manual_key(self, user_input=None, errors=None):
        hub = self._hub()

        if user_input is not None:
            ok, reason = await hub.set_device_key(user_input.get("device"), (user_input.get("key") or "").strip())
            if not ok:
                return await self.async_step_manual_key(
                    errors={"key": "key_collision" if reason == "collision" else "key_required"}
                )
            return self.async_create_entry(title="", data={})

        choices = {}
        choices.update({d: f"{d} (pending)" for d in hub.pending_devices})
        choices.update({d: f"{d} (approved)" for d in hub.device_keys})
        if not choices:
            return self.async_create_entry(title="", data={})

        schema = vol.Schema({
            vol.Required("device"): vol.In(choices),
            vol.Required("key"): str,
        })
        return self.async_show_form(step_id="manual_key", data_schema=schema, errors=errors or {})

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
