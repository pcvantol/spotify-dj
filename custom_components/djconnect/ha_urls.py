from __future__ import annotations

from typing import Any

from .const import CONF_HA_EXTERNAL_URL


async def async_ha_url_payload(hass: Any, conf: dict[str, Any]) -> dict[str, str]:
    """Build HA URLs for ESP local-first/cloud-fallback pairing."""
    local_url = await async_ha_local_url(hass, conf)
    remote_url = _clean_url(conf.get(CONF_HA_EXTERNAL_URL))
    payload: dict[str, str] = {}
    if local_url:
        payload["ha_local_url"] = local_url
    if remote_url:
        payload["ha_remote_url"] = remote_url
    return payload


async def async_ha_local_url(hass: Any, conf: dict[str, Any]) -> str:
    """Return the best local HA base URL known to Home Assistant."""
    try:
        from homeassistant.helpers import network

        url = await network.async_get_url(hass, prefer_external=False)
        cleaned = _clean_url(url)
        if cleaned:
            return cleaned
    except Exception:  # noqa: BLE001
        pass

    config = getattr(hass, "config", None)
    for value in (
        getattr(config, "internal_url", None),
        getattr(config, "external_url", None),
        conf.get(CONF_HA_EXTERNAL_URL),
    ):
        cleaned = _clean_url(value)
        if cleaned:
            return cleaned
    return ""


def _clean_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")
