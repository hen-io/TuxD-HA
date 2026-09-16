from homeassistant.components.sensor import SensorEntity, SensorStateClass
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo

from .const import DOMAIN, HUB_IDENTIFIER, SIGNAL_HUB_STATS_UPDATE
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


class TuxdSensor(TuxdEntity, SensorEntity):
    @property
    def native_value(self):
        return self._entry.get("state")

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
