from homeassistant.helpers.entity import Entity, DeviceInfo, EntityCategory
from homeassistant.helpers.dispatcher import async_dispatcher_connect

from .const import DOMAIN, HUB_IDENTIFIER, SIGNAL_STATE_UPDATE


_READ_ONLY_ENTITY_CLASSES = frozenset({"TuxdSensor", "TuxdBinarySensor", "TuxdUpdate"})


class TuxdEntity(Entity):

    _attr_should_poll = False
    _attr_has_entity_name = False

    def __init__(self, hub, unique_id):
        self.hub = hub
        self._unique_id = unique_id

    @property
    def _entry(self):
        return self.hub.entities.get(self._unique_id) or {}

    @property
    def _config(self):
        return self._entry.get("config") or {}

    @property
    def unique_id(self):
        return self._unique_id

    @property
    def available(self):
        entry = self._entry
        if not entry:
            return False
        return entry.get("device_id") in self.hub.devices

    @property
    def name(self):
        return self._config.get("name")

    @property
    def icon(self):
        return self._config.get("icon")

    @property
    def entity_category(self):
        try:
            category = EntityCategory(self._config.get("entity_category"))
        except ValueError:
            return None
        if category is EntityCategory.CONFIG and type(self).__name__ in _READ_ONLY_ENTITY_CLASSES:
            return EntityCategory.DIAGNOSTIC
        return category

    @property
    def device_info(self):
        dev = self._config.get("device") or {}
        identifiers = dev.get("identifiers") or [self._entry.get("device_id")]
        return DeviceInfo(
            identifiers={(DOMAIN, i) for i in identifiers if i},
            name=dev.get("name"),
            manufacturer=dev.get("manufacturer"),
            model=dev.get("model"),
            sw_version=dev.get("sw_version"),
            via_device=(DOMAIN, HUB_IDENTIFIER),
        )

    @property
    def extra_state_attributes(self):
        attrs = self._entry.get("attributes")
        return attrs or None

    def _send_command(self, key, payload):
        device_id = self._entry.get("device_id")
        if device_id:
            self.hub.send_command(device_id, key, payload)

    async def async_added_to_hass(self):
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_STATE_UPDATE.format(unique_id=self._unique_id),
                self.async_write_ha_state,
            )
        )
