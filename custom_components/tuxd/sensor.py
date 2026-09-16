from homeassistant.components.sensor import SensorDeviceClass, SensorEntity, SensorStateClass
from homeassistant.core import callback
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.util import dt as dt_util

from .const import DOMAIN, HUB_IDENTIFIER, SIGNAL_DEVICE_APPROVED, SIGNAL_HUB_STATS_UPDATE, SIGNAL_LAST_SEEN_UPDATE
from .entity import TuxdEntity, async_setup_dynamic_platform
from .update import TuxdUpdate

_DOMAIN_KEY = "sensor"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdSensor, hub)

    async_add_entities([
        TuxdConfiguredDevicesSensor(hub),
        TuxdOnlineDevicesSensor(hub),
        TuxdDevicesWithErrorsSensor(hub),
        TuxdDevicesWithHostUpdatesSensor(hub),
        TuxdDevicesWithScriptUpdatesSensor(hub),
    ])

    added = set()

    @callback
    def _add_last_seen(device_id):
        if device_id in added:
            return
        added.add(device_id)
        async_add_entities([TuxdLastSeenSensor(hub, device_id)])

    for device_id in list(hub.device_keys.keys()):
        _add_last_seen(device_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_APPROVED, _add_last_seen)
    )


class TuxdSensor(TuxdEntity, SensorEntity):
    @property
    def native_value(self):
        value = self._entry.get("state")
        if isinstance(value, str):
            device_class = self._config.get("device_class")
            if device_class == "timestamp":
                return dt_util.parse_datetime(value)
            if device_class == "date":
                return dt_util.parse_date(value)
        return value

    @property
    def native_unit_of_measurement(self):
        return self._config.get("unit_of_measurement")

    @property
    def state_class(self):
        return self._config.get("state_class")

    @property
    def device_class(self):
        return self._config.get("device_class")


def _has_update(hub, unique_id):
    upd = TuxdUpdate(hub, unique_id)
    installed, latest = upd.installed_version, upd.latest_version
    return installed is not None and latest is not None and installed != latest


class TuxdHubStatSensor(SensorEntity):

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = "devices"

    def __init__(self, hub, oid, name, icon):
        self.hub = hub
        self._attr_unique_id = f"{DOMAIN}_hub_{oid}"
        self._attr_name = name
        self._attr_icon = icon

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(DOMAIN, HUB_IDENTIFIER)})

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_HUB_STATS_UPDATE, self.async_write_ha_state)
        )


class TuxdConfiguredDevicesSensor(TuxdHubStatSensor):
    def __init__(self, hub):
        super().__init__(hub, "configured_devices", "TuxD Configured Devices", "mdi:server-network")

    @property
    def native_value(self):
        return len(self.hub.device_keys)


class TuxdOnlineDevicesSensor(TuxdHubStatSensor):
    def __init__(self, hub):
        super().__init__(hub, "online_devices", "TuxD Online Devices", "mdi:server-network-outline")

    @property
    def native_value(self):
        return len(self.hub.devices)


class TuxdDevicesWithErrorsSensor(TuxdHubStatSensor):
    def __init__(self, hub):
        super().__init__(hub, "devices_with_errors", "TuxD Devices With Errors", "mdi:alert-circle-outline")

    @property
    def native_value(self):
        return sum(
            1 for e in self.hub.entities.values()
            if e.get("object_id") == "system_error" and e.get("state") == "ON"
        )


class TuxdDevicesWithHostUpdatesSensor(TuxdHubStatSensor):
    def __init__(self, hub):
        super().__init__(hub, "devices_with_host_updates", "TuxD Devices With Host Updates", "mdi:package-up")

    @property
    def native_value(self):
        return sum(
            1 for uid, e in self.hub.entities.items()
            if e.get("object_id") == "host_update" and _has_update(self.hub, uid)
        )


class TuxdDevicesWithScriptUpdatesSensor(TuxdHubStatSensor):
    def __init__(self, hub):
        super().__init__(hub, "devices_with_script_updates", "TuxD Devices With Script Updates", "mdi:script-text-outline")

    @property
    def native_value(self):
        return sum(
            1 for uid, e in self.hub.entities.items()
            if e.get("object_id") == "self_update" and _has_update(self.hub, uid)
        )


class TuxdLastSeenSensor(SensorEntity):

    _attr_should_poll = False
    _attr_has_entity_name = False
    _attr_name = "Last Seen"
    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_icon = "mdi:clock-check-outline"

    def __init__(self, hub, device_id):
        self.hub = hub
        self._device_id = device_id
        self._attr_unique_id = f"{DOMAIN}_{device_id}_last_seen"

    @property
    def native_value(self):
        return self.hub.device_last_seen.get(self._device_id)

    @property
    def device_info(self):
        dev_reg = dr.async_get(self.hass)
        hub_device = dev_reg.async_get_device_by_identifier((DOMAIN, HUB_IDENTIFIER), self.hub.entry.entry_id)
        return DeviceInfo(
            identifiers={(DOMAIN, self._device_id)},
            via_device_id=hub_device.id if hub_device else None,
        )

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_LAST_SEEN_UPDATE.format(device_id=self._device_id),
                self.async_write_ha_state,
            )
        )
