import asyncio
import importlib
import sys
import types
import unittest
from unittest import mock


def _load_entity_module():
    for name in ("homeassistant", "homeassistant.core", "homeassistant.exceptions", "homeassistant.helpers",
                 "homeassistant.helpers.device_registry", "homeassistant.helpers.entity_registry",
                 "homeassistant.helpers.entity", "homeassistant.helpers.dispatcher", "homeassistant.util"):
        sys.modules.setdefault(name, mock.MagicMock())

    class Entity:
        async def async_internal_added_to_hass(self):
            pass

    sys.modules["homeassistant.helpers.entity"].Entity = Entity
    sys.modules["homeassistant.util"].slugify = lambda s: str(s).lower()
    pkg = types.ModuleType("custom_components.tuxd"); pkg.__path__ = ["custom_components/tuxd"]
    sys.modules.setdefault("custom_components", types.ModuleType("custom_components")).__path__ = ["custom_components"]
    sys.modules["custom_components.tuxd"] = pkg
    const = types.ModuleType("custom_components.tuxd.const")
    for n in ("DOMAIN", "HUB_IDENTIFIER", "SIGNAL_NEW_ENTITY", "SIGNAL_REMOVE_ENTITY", "SIGNAL_STATE_UPDATE"):
        setattr(const, n, n)
    sys.modules["custom_components.tuxd.const"] = const
    return importlib.import_module("custom_components.tuxd.entity")


class Registry:
    def __init__(self, entry):
        self.entry, self.calls = entry, []

    def async_get(self, entity_id):
        return self.entry

    def async_update_entity(self, entity_id, **kwargs):
        self.calls.append((entity_id, kwargs))


class EntityNameTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mod = _load_entity_module()

    def _run(self, entry, name="CPU load"):
        registry = Registry(entry)
        ent = self.mod.TuxdEntity.__new__(self.mod.TuxdEntity)
        ent.hass, ent.entity_id = object(), "sensor.host_cpu_load"
        with mock.patch.object(self.mod.er, "async_get", return_value=registry), \
                mock.patch.object(self.mod.TuxdEntity, "name", new_callable=mock.PropertyMock, return_value=name):
            asyncio.run(ent.async_internal_added_to_hass())
        return registry.calls

    def test_sets_only_the_name(self):
        calls = self._run(types.SimpleNamespace(name=None))
        self.assertEqual(calls, [("sensor.host_cpu_load", {"name": "CPU load"})])

    def test_users_own_name_is_kept(self):
        self.assertEqual(self._run(types.SimpleNamespace(name="My name")), [])

    def test_no_registry_entry_or_name(self):
        self.assertEqual(self._run(None), [])
        self.assertEqual(self._run(types.SimpleNamespace(name=None), name=None), [])


if __name__ == "__main__":
    unittest.main()
