import asyncio
import secrets

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers import selector

from .const import ALERT_CATEGORIES, DOMAIN, OFFLINE_LEVELS


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
        if hub.devices:
            menu_options.append("config")
            menu_options.append("agent_password")
        menu_options.append("master_password")
        menu_options.append("global_alerts")
        if hub.device_keys:
            menu_options.append("offline_alerts")
        if hub.terminal_enabled_devices():
            menu_options.append("run_command")
        if hub.device_keys:
            menu_options.append("restore_entity_ids")
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

    async def async_step_config(self, user_input=None, errors=None):
        hub = self._hub()
        device_id = getattr(self, "_config_device", None)
        if not device_id or device_id not in hub.devices:
            return await self.async_step_config_device()

        password = getattr(self, "_config_password", None)
        if user_input is not None:
            text = user_input.get("yaml", "")
            result = await hub.async_set_device_config(device_id, text, password)
            if result.get("ok"):
                return self.async_create_entry(title="", data={})
            if result.get("auth"):
                return await self.async_step_config_device(errors={"password": f"password_{result['auth']}"})
            return self._config_form(device_id, text, result.get("error") or "Could not save the configuration")

        result = await hub.async_get_device_config(device_id, password)
        if result.get("auth"):
            return await self.async_step_config_device(errors={"password": f"password_{result['auth']}"})
        if not result.get("ok"):
            return self.async_abort(reason="config_failed", description_placeholders={
                "device": device_id, "error": result.get("error") or "Could not read the configuration",
            })
        self._config_content = result.get("content", "")
        return self._config_form(device_id, self._config_content)

    def _config_form(self, device_id, text, error=None):
        return self.async_show_form(
            step_id="config",
            data_schema=vol.Schema({
                vol.Required("yaml", default=text): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
            }),
            errors={"base": "config_failed"} if error else {},
            description_placeholders={"device": device_id, "error": error or ""},
        )

    async def async_step_config_device(self, user_input=None, errors=None):
        hub = self._hub()
        if user_input is not None:
            self._config_device = user_input["device"]
            self._config_password = user_input.get("password") or None
            return await self.async_step_config()
        choices = {device_id: device_id for device_id in hub.devices}
        if not choices:
            return self.async_create_entry(title="", data={})
        return self.async_show_form(
            step_id="config_device",
            data_schema=vol.Schema({
                vol.Required("device", default=getattr(self, "_config_device", None) or vol.UNDEFINED): vol.In(choices),
                vol.Optional("password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            }),
            errors=errors or {},
        )


    async def async_step_run_command(self, user_input=None, errors=None):
        hub = self._hub()
        devices = hub.terminal_enabled_devices()
        if not devices:
            return self.async_create_entry(title="", data={})

        if user_input is not None:
            targets = user_input.get("devices") or []
            cmd = (user_input.get("command") or "").strip()
            password = (user_input.get("password") or "").strip()
            if not targets:
                return await self.async_step_run_command(errors={"devices": "no_devices_selected"})
            if not cmd:
                return await self.async_step_run_command(errors={"command": "command_required"})
            if len(targets) > 1 and not await hub.check_master(user_input.get("master_password")):
                return await self.async_step_run_command(errors={"master_password": "master_incorrect"})
            results = await asyncio.gather(*[
                hub.run_terminal_command(device_id, cmd, password or None) for device_id in targets
            ])
            return await self.async_step_run_command_result(
                results=dict(zip(targets, results))
            )

        choices = {device_id: device_id for device_id in devices}
        schema = vol.Schema({
            vol.Required("devices", default=devices): cv.multi_select(choices),
            vol.Required("command"): str,
            vol.Optional("password", default=""): selector.TextSelector(
                selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)
            ),
        })
        if hub.master_required():
            schema = schema.extend({vol.Optional("master_password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})
        return self.async_show_form(step_id="run_command", data_schema=schema, errors=errors or {})


    async def async_step_agent_password(self, user_input=None, errors=None):
        hub = self._hub()
        devices = sorted(hub.devices)
        if not devices:
            return self.async_create_entry(title="", data={})

        if user_input is not None:
            targets = user_input.get("devices") or []
            new = user_input.get("new_password") or ""
            remove = bool(user_input.get("remove"))
            if not targets:
                return await self.async_step_agent_password(errors={"devices": "no_devices_selected"})
            if not remove and not new:
                return await self.async_step_agent_password(errors={"new_password": "password_empty"})
            if not remove and new != (user_input.get("confirm_password") or ""):
                return await self.async_step_agent_password(errors={"confirm_password": "password_mismatch"})
            if len(targets) > 1 and not await hub.check_master(user_input.get("master_password")):
                return await self.async_step_agent_password(errors={"master_password": "master_incorrect"})
            current = user_input.get("current_password") or None
            results = await asyncio.gather(*[
                hub.async_set_device_password(d, "" if remove else new, current) for d in targets
            ])
            lines = []
            for device_id, result in zip(targets, results):
                if result.get("ok"):
                    lines.append(f"**{device_id}** - {'removed' if remove else 'set'}")
                else:
                    lines.append(f"**{device_id}** - FAILED: {result.get('error', 'no answer')}")
            return self.async_show_form(
                step_id="agent_password_result", data_schema=vol.Schema({}),
                description_placeholders={"results": "\n\n".join(lines)},
            )

        schema = vol.Schema({
            vol.Required("devices", default=devices): cv.multi_select({d: d for d in devices}),
            vol.Optional("current_password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional("new_password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional("confirm_password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
            vol.Optional("remove", default=False): bool,
        })
        if hub.master_required():
            schema = schema.extend({vol.Optional("master_password", default=""): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))})
        return self.async_show_form(step_id="agent_password", data_schema=schema, errors=errors or {})

    async def async_step_agent_password_result(self, user_input=None):
        return self.async_create_entry(title="", data={})

    async def async_step_master_password(self, user_input=None, errors=None):
        hub = self._hub()
        if user_input is not None:
            new = user_input.get("new_password") or ""
            remove = bool(user_input.get("remove"))
            if hub.master_required() and not await hub.check_master(user_input.get("current_password")):
                return await self.async_step_master_password(errors={"current_password": "master_incorrect"})
            if not remove and not new:
                return await self.async_step_master_password(errors={"new_password": "password_empty"})
            if not remove and new != (user_input.get("confirm_password") or ""):
                return await self.async_step_master_password(errors={"confirm_password": "password_mismatch"})
            await hub.set_master_password("" if remove else new)
            return self.async_create_entry(title="", data={})

        fields = {}
        if hub.master_required():
            fields[vol.Optional("current_password", default="")] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
        fields[vol.Optional("new_password", default="")] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
        fields[vol.Optional("confirm_password", default="")] = selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD))
        if hub.master_required():
            fields[vol.Optional("remove", default=False)] = bool
        return self.async_show_form(step_id="master_password", data_schema=vol.Schema(fields), errors=errors or {})

    async def async_step_global_alerts(self, user_input=None):
        hub = self._hub()
        devices = sorted(hub.device_keys)
        current = hub.global_alerts
        if user_input is not None:
            default = list(user_input.get("default") or [])
            old_default = sorted(current["default"])
            own = {}
            for d in devices:
                picked = sorted(user_input.get(d) or [])
                had_own = d in current["devices"]
                if picked != sorted(default) and (had_own or picked != old_default):
                    own[d] = picked
            await hub.set_global_alerts(user_input.get("warning_delay", 0), user_input.get("error_delay", 0), default, own)
            return self.async_create_entry(title="", data={})

        kinds = selector.SelectSelector(selector.SelectSelectorConfig(
            options=[selector.SelectOptionDict(value=k, label=label) for k, label in ALERT_CATEGORIES],
            multiple=True, mode=selector.SelectSelectorMode.LIST,
        ))
        seconds = selector.NumberSelector(selector.NumberSelectorConfig(
            min=0, max=86400, step=1, unit_of_measurement="s", mode=selector.NumberSelectorMode.BOX,
        ))
        fields = {
            vol.Required("warning_delay", default=current["warning_delay"]): seconds,
            vol.Required("error_delay", default=current["error_delay"]): seconds,
            vol.Optional("default", default=current["default"]): kinds,
        }
        for device_id in devices:
            fields[vol.Optional(device_id, default=sorted(hub.alert_categories(device_id)))] = kinds
        return self.async_show_form(step_id="global_alerts", data_schema=vol.Schema(fields))

    async def async_step_offline_alerts(self, user_input=None):
        hub = self._hub()
        devices = sorted(hub.device_keys)
        if user_input is not None:
            own = {d: user_input[d] for d in devices if user_input.get(d) in OFFLINE_LEVELS}
            await hub.set_offline_alerts(user_input.get("default", "off"), own)
            return self.async_create_entry(title="", data={})

        def levels(with_default):
            options = [selector.SelectOptionDict(value="default", label="Use default")] if with_default else []
            options += [selector.SelectOptionDict(value=v, label=label)
                        for v, label in (("off", "Off"), ("warning", "Warning"), ("error", "Error"))]
            return selector.SelectSelector(selector.SelectSelectorConfig(options=options, mode=selector.SelectSelectorMode.DROPDOWN))

        current = hub.offline_alerts
        fields = {vol.Required("default", default=current.get("default", "off")): levels(False)}
        for device_id in devices:
            fields[vol.Required(device_id, default=current.get("devices", {}).get(device_id, "default"))] = levels(True)
        return self.async_show_form(step_id="offline_alerts", data_schema=vol.Schema(fields))

    async def async_step_run_command_result(self, user_input=None, results=None):
        if results is not None:
            self._run_command_results = results
        if user_input is not None:
            return self.async_create_entry(title="", data={})

        blocks = []
        for device_id, result in self._run_command_results.items():
            status = "OK" if result["ok"] else f"FAILED - {result['error']}"
            output = result["output"].strip() or "(no output)"
            blocks.append(f"**{device_id}** - {status}\n```\n{output}\n```")
        return self.async_show_form(
            step_id="run_command_result",
            data_schema=vol.Schema({}),
            description_placeholders={"results": "\n\n".join(blocks)},
        )


    async def async_step_restore_entity_ids(self, user_input=None):
        hub = self._hub()
        if user_input is not None:
            renamed, skipped = hub.restore_entity_ids()
            return await self.async_step_restore_entity_ids_done(renamed=renamed, skipped=skipped)
        return self.async_show_form(step_id="restore_entity_ids", data_schema=vol.Schema({}))

    async def async_step_restore_entity_ids_done(self, user_input=None, renamed=None, skipped=None):
        if renamed is not None:
            self._restore_result = (renamed, skipped)
        if user_input is not None:
            return self.async_create_entry(title="", data={})
        renamed, skipped = self._restore_result
        return self.async_show_form(
            step_id="restore_entity_ids_done",
            data_schema=vol.Schema({}),
            description_placeholders={"renamed": str(renamed), "skipped": str(skipped)},
        )


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
