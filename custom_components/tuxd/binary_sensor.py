from homeassistant.components.binary_sensor import BinarySensorDeviceClass, BinarySensorEntity
from homeassistant.core import callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    HUB_IDENTIFIER,
    SIGNAL_DEVICE_APPROVED,
    SIGNAL_LAST_SEEN_UPDATE,
    SIGNAL_ONLINE_SENSORS_ENABLED_CHANGED,
    SIGNAL_ONLINE_TIMEOUT_CHANGED,
)
from .entity import TuxdEntity, async_setup_dynamic_platform
from .const import ERROR_OBJECT_ID, WARNING_OBJECT_ID
from .fleet import FleetProblemsMixin, _offline, host_reason

_DOMAIN_KEY = "binary_sensor"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdBinarySensor, hub)

    added = set()

    @callback
    def _add_online(device_id):
        if not hub.online_sensors_enabled:
            return
        if device_id in added:
            return
        added.add(device_id)
        async_add_entities([TuxdOnlineBinarySensor(hub, device_id)])

    @callback
    def _remove_online(device_id):
        added.discard(device_id)
        ent_reg = er.async_get(hass)
        entity_id = ent_reg.async_get_entity_id(_DOMAIN_KEY, DOMAIN, f"{DOMAIN}_{device_id}_online")
        if entity_id:
            ent_reg.async_remove(entity_id)

    @callback
    def _on_online_sensors_enabled_changed():
        if hub.online_sensors_enabled:
            for device_id in list(hub.device_keys):
                _add_online(device_id)
        else:
            for device_id in list(added):
                _remove_online(device_id)

    for device_id in list(hub.device_keys):
        _add_online(device_id)

    async_add_entities([TuxdFleetErrorBinarySensor(hub), TuxdFleetWarningBinarySensor(hub)])

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_APPROVED, _add_online)
    )
    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_ONLINE_SENSORS_ENABLED_CHANGED, _on_online_sensors_enabled_changed)
    )


class TuxdBinarySensor(TuxdEntity, BinarySensorEntity):
    @property
    def is_on(self):
        state = self._entry.get("state")
        payload_on = self._config.get("payload_on", "ON")
        object_id, device = self._entry.get("object_id"), self._entry.get("device_id")
        if object_id == WARNING_OBJECT_ID and (self.hub.threshold_warning(device) or _offline(self.hub, device, "warning")):
            return True
        if object_id == ERROR_OBJECT_ID and _offline(self.hub, device, "error"):
            return True
        return state == payload_on

    @property
    def device_class(self):
        return self._config.get("device_class")

    @property
    def extra_state_attributes(self):
        attrs = super().extra_state_attributes
        level = {WARNING_OBJECT_ID: "warning", ERROR_OBJECT_ID: "error"}.get(self._entry.get("object_id"))
        if level:
            attrs = dict(attrs or {}, reason=host_reason(self.hub, self._entry.get("device_id"), level) if self.is_on else "")
        return attrs


class TuxdOnlineBinarySensor(BinarySensorEntity):
    _attr_has_entity_name = False
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_device_class = "connectivity"
    _attr_icon = "mdi:lan-connect"
    _attr_should_poll = True
    _attr_scan_interval = 30

    def __init__(self, hub, device_id):
        self.hub = hub
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_online"
        self._attr_name = f"{device_id} Online"

    @property
    def is_on(self):
        last_seen = self.hub.device_last_seen.get(self._device_id)
        if last_seen is None:
            return False
        return (dt_util.utcnow() - last_seen).total_seconds() <= self.hub.online_timeout

    @property
    def available(self):
        return self.hub.online_sensors_enabled

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(DOMAIN, HUB_IDENTIFIER)})

    async def async_update(self):
        self.async_write_ha_state()

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_SEEN_UPDATE.format(device_id=self._device_id),
                self.async_write_ha_state,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ONLINE_TIMEOUT_CHANGED,
                self.async_write_ha_state,
            )
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_ONLINE_SENSORS_ENABLED_CHANGED,
                self.async_write_ha_state,
            )
        )


class TuxdFleetErrorBinarySensor(FleetProblemsMixin, BinarySensorEntity):

    _attr_device_class = BinarySensorDeviceClass.PROBLEM
    _attr_icon = "mdi:alert-circle-outline"
    LEVEL = "error"

    def __init__(self, hub):
        self._init_problems(hub)
        self._attr_unique_id = f"{DOMAIN}_hub_fleet_error"
        self._attr_name = "TuxD Error"

    @property
    def is_on(self):
        return bool(self._problems())

    @property
    def extra_state_attributes(self):
        return self._problem_attributes()


class TuxdFleetWarningBinarySensor(TuxdFleetErrorBinarySensor):

    _attr_icon = "mdi:alert-outline"
    LEVEL = "warning"

    def __init__(self, hub):
        self._init_problems(hub)
        self._attr_unique_id = f"{DOMAIN}_hub_fleet_warning"
        self._attr_name = "TuxD Warning"
