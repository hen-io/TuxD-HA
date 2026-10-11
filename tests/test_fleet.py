import importlib
import importlib.util
import sys
import types
import unittest
from unittest import mock

from test_entity_name import _load_entity_module


def _load(name):
    _load_entity_module()
    spec = importlib.util.spec_from_file_location("custom_components.tuxd.const", "custom_components/tuxd/const.py")
    const = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const)
    sys.modules["custom_components.tuxd.const"] = const
    picture = types.ModuleType("custom_components.tuxd.picture")
    picture.picture_url = lambda hass, source: None
    sys.modules["custom_components.tuxd.picture"] = picture
    for m in ("homeassistant.components", "homeassistant.components.sensor",
              "homeassistant.components.binary_sensor", "homeassistant.components.update"):
        sys.modules.setdefault(m, mock.MagicMock())
    sys.modules["homeassistant.components.sensor"].SensorEntity = object
    sys.modules["homeassistant.components.binary_sensor"].BinarySensorEntity = object
    sys.modules["homeassistant.components.update"].UpdateEntity = object
    return importlib.import_module(f"custom_components.tuxd.{name}")


def hub(*entities):
    return types.SimpleNamespace(entities={str(i): e for i, e in enumerate(entities)})


def stack(device, oid, name, state):
    return {"device_id": device, "object_id": oid, "state": state, "config": {"name": f"{name} Health"}}


class FleetTest(unittest.TestCase):
    def test_stack_health_is_the_worst(self):
        S = _load("sensor").TuxdFleetStackHealthSensor
        healthy = [stack(f"h{i}", f"tugboat_s{i}_health", f"s{i}", "healthy") for i in range(9)]
        s = S(hub(*healthy, stack("h9", "docker_stack_web_health", "web", "unhealthy")))
        self.assertEqual(s.native_value, "unhealthy")
        self.assertEqual(s.extra_state_attributes["problems"], {"h9": {"web": "unhealthy"}})
        self.assertEqual(S(hub(*healthy)).native_value, "healthy")
        self.assertEqual(S(hub(*healthy, stack("x", "tugboat_a_health", "a", "stopped"))).native_value, "stopped")
        self.assertIsNone(S(hub(stack("x", "tugboat_a_health", "a", "unknown"))).native_value)

    def test_fleet_error(self):
        B = _load("binary_sensor").TuxdFleetErrorBinarySensor
        ok = {"device_id": "a", "object_id": "system_error", "state": "OFF"}
        bad = {"device_id": "b", "object_id": "system_error", "state": "ON"}
        reason = {"device_id": "b", "object_id": "system_error_reason", "state": "Root storage is full"}
        self.assertFalse(B(hub(ok)).is_on)
        b = B(hub(ok, bad, reason))
        self.assertTrue(b.is_on)
        self.assertEqual(b.extra_state_attributes, {"devices": ["b"], "reasons": {"b": "Root storage is full"}})


if __name__ == "__main__":
    unittest.main()
