from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from homeassistant.core import HomeAssistant

_LOGGER = logging.getLogger(__name__)

BLE_SERVICE_UUID = "7f705000-9f8f-4f1a-9b5f-570071fd0001"
BLE_WIFI_CHAR_UUID = "7f705001-9f8f-4f1a-9b5f-570071fd0001"
BLE_STATUS_CHAR_UUID = "7f705002-9f8f-4f1a-9b5f-570071fd0001"
BLE_NAME_PREFIX = "DJConnect"
BLE_CONNECT_TIMEOUT = 12
BLE_WRITE_TIMEOUT = 10
BLE_STATUS_TIMEOUT = 8


def wifi_payload(ssid: str, password: str) -> bytes:
    """Build the BLE WiFi provisioning payload without logging secrets."""
    return json.dumps(
        {
            "ssid": ssid,
            "password": password,
        },
        separators=(",", ":"),
    ).encode("utf-8")


def parse_status(raw: bytes | bytearray | str | None) -> dict[str, Any]:
    """Parse the device status characteristic into a dict."""
    if raw is None:
        return {}
    text = raw.decode("utf-8") if isinstance(raw, (bytes, bytearray)) else str(raw)
    try:
        status = json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid BLE status JSON: {text}") from exc
    return status if isinstance(status, dict) else {}


async def async_discover_devices(hass: HomeAssistant) -> dict[str, str]:
    """Return visible DJConnect BLE setup devices by address."""
    try:
        from homeassistant.components import bluetooth

        infos = bluetooth.async_discovered_service_info(hass, connectable=True)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect BLE discovery unavailable", exc_info=True)
        return {}

    devices: dict[str, str] = {}
    for info in infos or []:
        name = getattr(info, "name", "") or getattr(info, "device_name", "")
        address = getattr(info, "address", "")
        uuids = {uuid.lower() for uuid in getattr(info, "service_uuids", []) or []}
        if not address:
            continue
        if name.startswith(BLE_NAME_PREFIX) or BLE_SERVICE_UUID in uuids:
            devices[address] = name or f"DJConnect {address}"
    return devices


async def async_provision_wifi(
    hass: HomeAssistant,
    address: str,
    ssid: str,
    password: str,
) -> dict[str, Any]:
    """Write WiFi credentials to a DJConnect BLE device and read its status."""
    if not address:
        raise RuntimeError("No DJConnect BLE device selected")
    if not ssid:
        raise RuntimeError("WiFi SSID is required")

    _LOGGER.debug("DJConnect BLE WiFi provisioning started for %s", address)
    client = await _connect_client(hass, address)
    try:
        await asyncio.wait_for(
            client.write_gatt_char(
                BLE_WIFI_CHAR_UUID,
                wifi_payload(ssid, password),
                response=True,
            ),
            timeout=BLE_WRITE_TIMEOUT,
        )
        try:
            raw_status = await asyncio.wait_for(
                client.read_gatt_char(BLE_STATUS_CHAR_UUID),
                timeout=BLE_STATUS_TIMEOUT,
            )
            status = parse_status(raw_status)
        except TimeoutError:
            status = {
                "state": "submitted",
                "message": "WiFi credentials written; waiting for device restart",
            }
        _LOGGER.debug(
            "DJConnect BLE WiFi provisioning status for %s: %s",
            address,
            status.get("state"),
        )
        if status.get("state") == "error":
            raise RuntimeError(status.get("message") or "WiFi provisioning failed")
        return status
    finally:
        await _disconnect_client(client)


async def _connect_client(hass: HomeAssistant, address: str) -> Any:
    try:
        from bleak import BleakClient
        from bleak_retry_connector import establish_connection
        from homeassistant.components import bluetooth

        ble_device = bluetooth.async_ble_device_from_address(
            hass,
            address,
            connectable=True,
        )
        return await asyncio.wait_for(
            establish_connection(
                BleakClient,
                ble_device or address,
                "djconnect",
            ),
            timeout=BLE_CONNECT_TIMEOUT,
        )
    except Exception as exc:  # noqa: BLE001
        raise RuntimeError(f"Could not connect to DJConnect BLE device: {exc}") from exc


async def _disconnect_client(client: Any) -> None:
    try:
        await client.disconnect()
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect BLE disconnect failed", exc_info=True)
