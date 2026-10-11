import base64
import hashlib
import mimetypes
from pathlib import Path

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import DOMAIN

URL_PREFIX = "/api/tuxd/picture"
PADDING = 0.15
MAX_BYTES = 1024 * 1024
_IMAGES_DIR = Path(__file__).parent / "images"
_KEY = f"{DOMAIN}_pictures"


def _store(hass):
    return hass.data.setdefault(_KEY, {"sources": {}, "cache": {}})


def picture_url(hass, source):
    if not source or hass is None:
        return None
    source = str(source)
    if not source.startswith(("https://", "http://")):
        path = (_IMAGES_DIR / source).resolve()
        if _IMAGES_DIR.resolve() not in path.parents or not path.is_file():
            return None
    key = hashlib.sha1(source.encode()).hexdigest()[:16]
    _store(hass)["sources"][key] = source
    return f"{URL_PREFIX}/{key}"


def wrap(data, content_type):
    inner = 100 * (1 - 2 * PADDING)
    href = f"data:{content_type};base64,{base64.b64encode(data).decode()}"
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 100 100">'
        f'<image x="{100 * PADDING:g}" y="{100 * PADDING:g}" width="{inner:g}" height="{inner:g}" '
        f'preserveAspectRatio="xMidYMid meet" href="{href}" xlink:href="{href}"/></svg>'
    ).encode()


class TuxdPictureView(HomeAssistantView):
    url = URL_PREFIX + "/{key}"
    name = "api:tuxd:picture"
    requires_auth = False

    def __init__(self, hass):
        self.hass = hass

    async def get(self, request, key):
        store = _store(self.hass)
        if key in store["cache"]:
            return self._reply(store["cache"][key])
        source = store["sources"].get(key)
        if source is None:
            return web.Response(status=404)
        try:
            if source.startswith(("https://", "http://")):
                session = async_get_clientsession(self.hass)
                async with session.get(source, timeout=10) as resp:
                    if resp.status != 200:
                        return web.Response(status=502)
                    data = await resp.content.read(MAX_BYTES + 1)
                    ctype = resp.content_type
            else:
                path = _IMAGES_DIR / source
                data = await self.hass.async_add_executor_job(path.read_bytes)
                ctype = mimetypes.guess_type(path.name)[0] or ""
        except Exception:
            return web.Response(status=502)
        if len(data) > MAX_BYTES or not ctype.startswith("image/"):
            return web.Response(status=502)
        body = wrap(data, ctype)
        store["cache"][key] = body
        return self._reply(body)

    @staticmethod
    def _reply(body):
        return web.Response(body=body, content_type="image/svg+xml", headers={"Cache-Control": "public, max-age=86400"})
