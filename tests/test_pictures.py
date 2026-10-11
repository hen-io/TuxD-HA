import importlib.util
import sys
import types
import unittest
from unittest import mock


def _load(name):
    for m in ("aiohttp", "homeassistant", "homeassistant.components", "homeassistant.components.http",
              "homeassistant.helpers", "homeassistant.helpers.aiohttp_client"):
        sys.modules.setdefault(m, mock.MagicMock())
    sys.modules["homeassistant.components.http"].HomeAssistantView = object
    pkg = sys.modules.setdefault("custom_components.tuxd", types.ModuleType("custom_components.tuxd"))
    pkg.__path__ = ["custom_components/tuxd"]
    spec = importlib.util.spec_from_file_location("custom_components.tuxd.const", "custom_components/tuxd/const.py")
    const = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(const)
    sys.modules["custom_components.tuxd.const"] = const
    spec = importlib.util.spec_from_file_location(f"custom_components.tuxd.{name}", f"custom_components/tuxd/{name}.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod, const


class PictureTest(unittest.TestCase):
    def test_registered_sources_only(self):
        pic, _ = _load("picture")
        hass = types.SimpleNamespace(data={})
        url = pic.picture_url(hass, "https://cdn.example/svg/bazarr.svg")
        self.assertTrue(url.startswith("/api/tuxd/picture/"))
        self.assertEqual(list(hass.data[pic._KEY]["sources"].values()), ["https://cdn.example/svg/bazarr.svg"])
        self.assertTrue(pic.picture_url(hass, "distros/ubuntu.svg"))
        for bad in ("../const.py", "distros/none.svg", "javascript:x", "", None):
            self.assertIsNone(pic.picture_url(hass, bad), bad)

    def test_margin(self):
        pic, _ = _load("picture")
        svg = pic.wrap(b"<svg/>", "image/svg+xml").decode()
        self.assertIn('x="15" y="15" width="70" height="70"', svg)
        self.assertIn("data:image/svg+xml;base64,", svg)

    def test_windows_logo(self):
        _, const = _load("picture")
        self.assertEqual(const.distro_logo(["windows"]), "distros/windows.svg")
        self.assertEqual(const.distro_logo(None), "distros/linux.svg")


if __name__ == "__main__":
    unittest.main()
