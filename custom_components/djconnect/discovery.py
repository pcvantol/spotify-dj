"""mDNS discovery helpers for DJConnect clients."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
import logging
import re
from typing import Any

from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CLIENT_TYPE_ESP32,
    CLIENT_TYPE_IOS,
    CLIENT_TYPE_MACOS,
    CLIENT_TYPE_RASPBERRY_PI,
    CLIENT_TYPES,
    CONF_CLIENT_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_LOCAL_URL,
    CONF_PAIR_CODE,
)

_LOGGER = logging.getLogger(__name__)

MDNS_SERVICE_TYPE = "_djconnect._tcp.local."
DISCOVERY_TIMEOUT = 2.0
PROBE_TIMEOUT = 3.0


@dataclass(slots=True)
class DiscoveredClient:
    """A DJConnect client found through Bonjour/mDNS."""

    local_url: str
    device_id: str
    client_type: str
    device_name: str = "DJConnect"
    pair_code: str = ""
    version: str = ""
    paired: bool | None = None
    source: str = "mdns"
    pairing_info_failed: bool = False

    @property
    def label(self) -> str:
        """Return a compact human label for config-flow choices."""
        host = self.local_url.removeprefix("http://").removeprefix("https://")
        name = self.device_name or "DJConnect"
        suffix = " · pairing-info unavailable" if self.pairing_info_failed else ""
        return f"{name} · {self.device_id} · {host}{suffix}"


async def async_discover_djconnect_clients(hass: Any) -> list[DiscoveredClient]:
    """Discover visible DJConnect clients advertised as `_djconnect._tcp`."""
    try:
        from homeassistant.components import zeroconf

        async_zc = await zeroconf.async_get_async_instance(hass)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("DJConnect mDNS discovery unavailable: %s", exc)
        return []

    try:
        service_names = await _async_browse_service_names(async_zc)
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("DJConnect mDNS browse failed: %s", exc)
        return []

    session = async_get_clientsession(hass)
    clients: list[DiscoveredClient] = []
    for service_name in sorted(service_names):
        info = await _async_get_service_info(async_zc, service_name)
        client = _client_from_service_info(info)
        if client is None:
            continue
        pairing_info = await async_probe_pairing_info(session, client.local_url)
        if not pairing_info:
            _LOGGER.debug(
                "DJConnect ignoring stale/unreachable mDNS client device_id=%s url=%s",
                client.device_id,
                client.local_url,
            )
            continue
        client = _client_with_pairing_info(client, pairing_info)
        if _is_valid_discovered_client(client):
            clients.append(client)

    return _dedupe_clients(clients)


async def async_probe_pairing_info(session: Any, local_url: str) -> dict[str, Any]:
    """Fetch pairing-info from a discovered client, returning `{}` on failure."""
    if session is None or not local_url:
        return {}
    url = local_url.rstrip("/") + "/api/device/pairing-info"
    try:
        response = await asyncio.wait_for(session.get(url), timeout=PROBE_TIMEOUT)
        async with response:
            status = getattr(response, "status", 0)
            if status != 200:
                _LOGGER.debug(
                    "DJConnect pairing-info probe failed status=%s url=%s",
                    status,
                    url,
                )
                return {}
            data = await response.json(content_type=None)
            return data if isinstance(data, dict) else {}
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("DJConnect pairing-info probe failed url=%s error=%s", url, exc)
    return {}


async def _async_browse_service_names(async_zc: Any) -> set[str]:
    """Browse `_djconnect._tcp` for a short window and return service names."""
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser
    except Exception as exc:  # noqa: BLE001
        _LOGGER.debug("DJConnect zeroconf browser unavailable: %s", exc)
        return set()

    found: set[str] = set()

    def _on_service_state_change(
        zeroconf: Any,
        service_type: str,
        name: str,
        state_change: Any,
    ) -> None:
        if state_change == ServiceStateChange.Added:
            found.add(name)

    zc = getattr(async_zc, "zeroconf", async_zc)
    browser = AsyncServiceBrowser(
        zc,
        MDNS_SERVICE_TYPE,
        handlers=[_on_service_state_change],
    )
    try:
        await asyncio.sleep(DISCOVERY_TIMEOUT)
    finally:
        cancel = getattr(browser, "async_cancel", None)
        if cancel:
            result = cancel()
            if asyncio.iscoroutine(result):
                await result
    return found


async def _async_get_service_info(async_zc: Any, service_name: str) -> Any:
    """Resolve service info through HA's AsyncZeroconf wrapper."""
    getter = getattr(async_zc, "async_get_service_info", None)
    if getter is not None:
        return await getter(MDNS_SERVICE_TYPE, service_name)
    zc = getattr(async_zc, "zeroconf", async_zc)
    get_service_info = getattr(zc, "get_service_info", None)
    if get_service_info is None:
        return None
    return await asyncio.to_thread(get_service_info, MDNS_SERVICE_TYPE, service_name)


def _client_from_service_info(info: Any) -> DiscoveredClient | None:
    """Build a discovered client from zeroconf ServiceInfo-like objects."""
    if info is None:
        return None
    properties = _properties_from_service_info(info)
    client_type = str(properties.get(CONF_CLIENT_TYPE) or "").strip().lower()
    device_id = str(properties.get(CONF_DEVICE_ID) or "").strip()
    if client_type not in CLIENT_TYPES or not _device_id_matches_client_type(
        device_id,
        client_type,
    ):
        return None
    local_url = str(properties.get(CONF_LOCAL_URL) or "").strip()
    if not local_url:
        local_url = _local_url_from_service_info(info)
    if not local_url:
        return None
    return DiscoveredClient(
        local_url=local_url,
        device_id=device_id,
        client_type=client_type,
        device_name=str(
            properties.get(CONF_DEVICE_NAME)
            or properties.get("name")
            or properties.get("friendly_name")
            or "DJConnect"
        ).strip(),
        pair_code=str(properties.get(CONF_PAIR_CODE) or "").strip(),
        version=str(
            properties.get("version")
            or properties.get("app_version")
            or properties.get("firmware")
            or ""
        ).strip(),
        paired=_bool_or_none(properties.get("paired")),
    )


def _client_with_probe_failure(client: DiscoveredClient) -> DiscoveredClient:
    """Mark a TXT-discovered client when pairing-info could not be verified."""
    return DiscoveredClient(
        local_url=client.local_url,
        device_id=client.device_id,
        client_type=client.client_type,
        device_name=client.device_name,
        pair_code=client.pair_code,
        version=client.version,
        paired=client.paired,
        source=client.source,
        pairing_info_failed=True,
    )


def _client_with_pairing_info(
    client: DiscoveredClient,
    pairing_info: dict[str, Any],
) -> DiscoveredClient:
    """Merge pairing-info into an mDNS client; pairing-info is authoritative."""
    local_url = str(pairing_info.get(CONF_LOCAL_URL) or client.local_url).strip()
    device_id = str(pairing_info.get(CONF_DEVICE_ID) or client.device_id).strip()
    client_type = (
        str(pairing_info.get(CONF_CLIENT_TYPE) or client.client_type)
        .strip()
        .lower()
    )
    return DiscoveredClient(
        local_url=local_url,
        device_id=device_id,
        client_type=client_type,
        device_name=str(
            pairing_info.get(CONF_DEVICE_NAME)
            or pairing_info.get("name")
            or client.device_name
            or "DJConnect"
        ).strip(),
        pair_code=str(pairing_info.get(CONF_PAIR_CODE) or client.pair_code or "").strip(),
        version=str(
            pairing_info.get("app_version")
            or pairing_info.get("firmware")
            or pairing_info.get("version")
            or client.version
            or ""
        ).strip(),
        paired=_bool_or_none(pairing_info.get("paired"))
        if "paired" in pairing_info
        else client.paired,
        source="pairing-info",
        pairing_info_failed=False,
    )


def _properties_from_service_info(info: Any) -> dict[str, str]:
    """Decode TXT properties from zeroconf ServiceInfo-like objects."""
    raw = getattr(info, "properties", {}) or {}
    properties: dict[str, str] = {}
    for key, value in raw.items():
        decoded_key = _decode_txt_value(key).strip()
        decoded_value = _decode_txt_value(value).strip()
        if decoded_key:
            properties[decoded_key] = decoded_value
    return properties


def _local_url_from_service_info(info: Any) -> str:
    """Build an HTTP URL from ServiceInfo address/host and port."""
    host = ""
    parsed_addresses = getattr(info, "parsed_addresses", None)
    if callable(parsed_addresses):
        try:
            addresses = list(parsed_addresses())
            host = str(addresses[0]) if addresses else ""
        except Exception:  # noqa: BLE001
            host = ""
    if not host:
        host = str(
            getattr(info, "server", "")
            or getattr(info, "hostname", "")
            or getattr(info, "host", "")
            or ""
        )
    host = host.strip().rstrip(".")
    port = int(getattr(info, "port", 0) or 0)
    if not host or port <= 0:
        return ""
    if ":" in host and not host.startswith("["):
        host = f"[{host}]"
    suffix = "" if port == 80 else f":{port}"
    return f"http://{host}{suffix}"


def _is_valid_discovered_client(client: DiscoveredClient) -> bool:
    return bool(
        client.local_url
        and client.client_type in CLIENT_TYPES
        and _device_id_matches_client_type(client.device_id, client.client_type)
    )


def _dedupe_clients(clients: list[DiscoveredClient]) -> list[DiscoveredClient]:
    """Dedupe clients by device_id first, then local_url."""
    deduped: dict[str, DiscoveredClient] = {}
    for client in clients:
        key = client.device_id or client.local_url
        if key not in deduped or client.source == "pairing-info":
            deduped[key] = client
    return list(deduped.values())


def _device_id_matches_client_type(device_id: str, client_type: str) -> bool:
    normalized_device = str(device_id or "").strip()
    normalized_client = str(client_type or "").strip().lower()
    if normalized_client == CLIENT_TYPE_IOS:
        return bool(re.fullmatch(r"djconnect-ios-[A-Za-z0-9]{12}", normalized_device))
    if normalized_client == CLIENT_TYPE_MACOS:
        return bool(re.fullmatch(r"djconnect-macos-[A-Za-z0-9]{12}", normalized_device))
    if normalized_client == CLIENT_TYPE_RASPBERRY_PI:
        return bool(
            re.fullmatch(r"djconnect-raspberry-pi-[A-Za-z0-9]{12}", normalized_device)
        )
    if normalized_client == CLIENT_TYPE_ESP32:
        return bool(
            re.fullmatch(
                r"djconnect-(?:lilygo-t-embed-s3|esp32-s3-box-3)-[0-9A-Fa-f]{12}",
                normalized_device,
            )
        )
    return False


def _decode_txt_value(value: Any) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", "replace")
    return str(value or "")


def _bool_or_none(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on"}
