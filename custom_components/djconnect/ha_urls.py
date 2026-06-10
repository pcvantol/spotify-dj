from __future__ import annotations

import inspect
import logging
from urllib.parse import urlparse
from typing import Any

from .const import CONF_HA_EXTERNAL_URL

_LOGGER = logging.getLogger(__name__)
HOMEASSISTANT_LOCAL_FALLBACK = "http://homeassistant.local:8123"


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

        url_getter = getattr(network, "async_get_url", None)
        url = (
            await _maybe_await(url_getter(hass, prefer_external=False))
            if callable(url_getter)
            else ""
        )
        cleaned = _clean_local_url(url)
        source_ip_getter = getattr(network, "async_get_source_ip", None)
        source_ip = (
            await _maybe_await(source_ip_getter(hass))
            if callable(source_ip_getter)
            else ""
        )
        fallback = _local_url_from_source_ip(source_ip)
        if cleaned and not _is_homeassistant_local_url(cleaned):
            return cleaned
        if fallback:
            return fallback
        if cleaned:
            return cleaned
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("DJConnect could not determine HA local URL from network helper: %s", exc)

    config = getattr(hass, "config", None)
    for value in (
        getattr(config, "internal_url", None),
        getattr(getattr(config, "api", None), "internal_url", None),
        _call_config_url_getter(config, "get_internal_url"),
        _call_config_url_getter(config, "async_get_internal_url"),
    ):
        cleaned = _clean_local_url(value)
        if cleaned:
            return cleaned
    _LOGGER.info(
        "DJConnect pairing local HA URL is unknown; using %s fallback",
        HOMEASSISTANT_LOCAL_FALLBACK,
    )
    return HOMEASSISTANT_LOCAL_FALLBACK


def _clean_url(value: Any) -> str:
    return str(value or "").strip().rstrip("/")


def _clean_local_url(value: Any) -> str:
    url = _clean_url(value)
    if not url or _is_nabu_casa_url(url):
        return ""
    return url


def _is_nabu_casa_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host.endswith(".ui.nabu.casa")


def _is_homeassistant_local_url(value: str) -> bool:
    host = (urlparse(value).hostname or "").lower()
    return host == "homeassistant.local"


def _local_url_from_source_ip(value: Any) -> str:
    ip = str(value or "").strip()
    if not ip:
        return ""
    return f"http://{ip}:8123"


def _call_config_url_getter(config: Any, name: str) -> Any:
    getter = getattr(config, name, None)
    if not callable(getter):
        return None
    try:
        value = getter()
    except TypeError:
        return None
    if inspect.isawaitable(value):
        return None
    return value


async def _maybe_await(value: Any) -> Any:
    if inspect.isawaitable(value):
        return await value
    return value
