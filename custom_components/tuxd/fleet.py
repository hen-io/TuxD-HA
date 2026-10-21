from homeassistant.core import callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.event import async_call_later

from .const import (
    DOMAIN,
    ERROR_OBJECT_ID,
    ERROR_REASON_OBJECT_ID,
    HUB_IDENTIFIER,
    SIGNAL_HUB_STATS_UPDATE,
    SIGNAL_PROBLEM_DELAY_CHANGED,
    SIGNAL_THRESHOLDS_CHANGED,
    WARNING_OBJECT_ID,
    WARNING_REASON_OBJECT_ID,
    alert_category,
)

_EMPTY = (None, "", "None", "unknown", "unavailable")


def _offline(hub, device_id, level):
    check = getattr(hub, "offline_alert", None)
    return check(device_id, level) if check else ""


def _threshold(hub, device_id):
    check = getattr(hub, "threshold_warning", None)
    return check(device_id) if check else ""


def host_reason(hub, device_id, level, own=None):
    if own is None:
        reason_oid = WARNING_REASON_OBJECT_ID if level == "warning" else ERROR_REASON_OBJECT_ID
        own = (hub.entities.get(f"{device_id}_{reason_oid}") or {}).get("state")
    own = "" if own in _EMPTY else str(own)
    over = _threshold(hub, device_id) if level == "warning" else ""
    return "; ".join(p for p in (_offline(hub, device_id, level), own, over) if p)[:255]


def reason_text(problems):
    return "; ".join(f"{device}: {reason}" if reason else device for device, reason in sorted(problems.items()))


class FleetProblemsMixin:

    _attr_should_poll = False
    _attr_has_entity_name = False
    LEVEL = "error"

    def _init_problems(self, hub):
        self.hub = hub
        self._next_due = None
        self._due_cancel = None

    @property
    def device_info(self):
        return DeviceInfo(identifiers={(DOMAIN, HUB_IDENTIFIER)})

    def _lasted(self, since):
        left = self.hub.problem_left(since, self.LEVEL) if hasattr(self.hub, "problem_left") else 0.0
        if left > 0:
            self._next_due = left if self._next_due is None else min(self._next_due, left)
            return False
        return True

    def _counts(self, device, kind):
        kinds = getattr(self.hub, "alert_categories", None)
        return kinds is None or kind in kinds(device)

    def _problems(self):
        flag, reason_oid = (
            (WARNING_OBJECT_ID, WARNING_REASON_OBJECT_ID) if self.LEVEL == "warning"
            else (ERROR_OBJECT_ID, ERROR_REASON_OBJECT_ID)
        )
        reasons = {e.get("device_id"): e.get("state") for e in self.hub.entities.values() if e.get("object_id") == reason_oid}
        problems = {}
        for e in self.hub.entities.values():
            if e.get("object_id") != flag:
                continue
            device = e.get("device_id")
            parts, hit = [], False
            if e.get("state") == "ON":
                sources = (e.get("attributes") or {}).get("sources")
                if isinstance(sources, dict) and sources:
                    since = e.get("source_since") or {}
                    for key, text in sources.items():
                        if self._counts(device, alert_category(key)) and self._lasted(since.get(key, e.get("changed_at"))):
                            hit = True
                            parts.append("" if text in _EMPTY else str(text))
                elif self._counts(device, "agent") and self._lasted(e.get("changed_at")):
                    hit = True
                    own = reasons.get(device)
                    parts.append("" if own in _EMPTY else str(own))
            if self.LEVEL == "warning" and hasattr(self.hub, "threshold_parts"):
                for metric, (text, since) in self.hub.threshold_parts(device).items():
                    if self._counts(device, f"threshold_{metric}") and self._lasted(since):
                        hit = True
                        parts.append(text)
            elif self.LEVEL == "warning":
                over = _threshold(self.hub, device)
                since = self.hub.threshold_warning_since(device) if hasattr(self.hub, "threshold_warning_since") else 0
                if over and self._lasted(since):
                    hit = True
                    parts.append(over)
            if hit:
                problems[device] = "; ".join(p for p in parts if p)
        for device in list(getattr(self.hub, "device_keys", {}) or {}):
            offline = _offline(self.hub, device, self.LEVEL)
            if offline and self._counts(device, "offline") and self._lasted(self.hub.offline_since(device)):
                problems[device] = "; ".join(p for p in (offline, problems.get(device)) if p)
        return problems

    def _problem_attributes(self):
        problems = self._problems()
        delay = self.hub.problem_delay(self.LEVEL) if callable(getattr(self.hub, "problem_delay", None)) else 0
        return {"devices": sorted(problems), "reasons": problems, "reason": reason_text(problems), "delay": delay}

    @callback
    def _refresh(self, *_args):
        self._next_due = None
        self.async_write_ha_state()
        if self._due_cancel:
            self._due_cancel()
            self._due_cancel = None
        if self._next_due is not None:
            self._due_cancel = async_call_later(self.hass, self._next_due + 0.5, self._refresh)

    async def async_added_to_hass(self):
        for signal in (SIGNAL_HUB_STATS_UPDATE, SIGNAL_PROBLEM_DELAY_CHANGED, SIGNAL_THRESHOLDS_CHANGED):
            self.async_on_remove(async_dispatcher_connect(self.hass, signal, self._refresh))
        self.async_on_remove(lambda: self._due_cancel and self._due_cancel())
