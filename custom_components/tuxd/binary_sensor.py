from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo, EntityCategory
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    HUB_IDENTIFIER,
    SIGNAL_DEVICE_APPROVED,
    SIGNAL_LAST_SEEN_UPDATE,
    SIGNAL_LAST_SEEN_ENABLED_CHANGED,
    SIGNAL_ONLINE_TIMEOUT_CHANGED,
)
from .entity import TuxdEntity, async_setup_dynamic_platform

_DOMAIN_KEY = "binary_sensor"


async def async_setup_entry(hass, entry, async_add_entities):
    hub = hass.data[DOMAIN][entry.entry_id]
    async_setup_dynamic_platform(hass, entry, async_add_entities, _DOMAIN_KEY, TuxdBinarySensor, hub)

    added = set()

    def _add_online(device_id):
        if device_id in added:
            return
        added.add(device_id)
        async_add_entities([TuxdOnlineBinarySensor(hub, device_id)])

    for device_id in list(hub.device_keys):
        _add_online(device_id)

    entry.async_on_unload(
        async_dispatcher_connect(hass, SIGNAL_DEVICE_APPROVED, _add_online)
    )


class TuxdBinarySensor(TuxdEntity, BinarySensorEntity):
    @property
    def is_on(self):
        state = self._entry.get("state")
        payload_on = self._config.get("payload_on", "ON")
        return state == payload_on

    @property
    def device_class(self):
        return self._config.get("device_class")


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
        return (dt_util.utcnow() - last_seen).total_seconds() <= self.hub.online_timeout * 60

    @property
    def available(self):
        return self.hub.last_seen_enabled

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
                SIGNAL_LAST_SEEN_ENABLED_CHANGED,
                self.async_write_ha_state,
            )
        )
