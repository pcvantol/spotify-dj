from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientResponseError, ClientTimeout
from awesomeversion import AwesomeVersion
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
    FIRMWARE_CHANNEL_BETA,
)

_LOGGER = logging.getLogger(__name__)
SUPPORTED_FIRMWARE_DEVICES = {"lilygo-t-embed-s3", "esp32-s3-box-3"}


@dataclass(slots=True)
class FirmwareRelease:
    version: str
    title: str
    body: str | None
    firmware_url: str
    firmware_asset: str
    manifest_url: str | None = None
    sha256: str | None = None
    device: str | None = None
    size: int | None = None
    min_ha_integration: str | None = None

    @property
    def release_notes(self) -> str:
        return self.body or self.title


def normalize_version(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("v"):
        value = value[1:]
    return value


def is_newer(latest: str | None, installed: str | None) -> bool:
    latest_n = normalize_version(latest)
    installed_n = normalize_version(installed)
    if not latest_n or not installed_n:
        return False
    try:
        return AwesomeVersion(latest_n) > AwesomeVersion(installed_n)
    except Exception:  # noqa: BLE001
        return latest_n != installed_n


@dataclass(slots=True)
class FirmwareAssets:
    manifest: dict[str, Any] | None = None
    sha256: dict[str, Any] | None = None


async def fetch_latest_firmware_release(
    hass: HomeAssistant,
    config: dict[str, Any],
) -> FirmwareRelease | None:
    repo = config.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO).strip()
    if not repo or "/" not in repo:
        return None

    session = async_get_clientsession(hass)
    channel = _firmware_channel(config.get(CONF_FIRMWARE_CHANNEL))
    try:
        release = await _fetch_release_json(session, repo, channel)
    except ClientResponseError as exc:
        if exc.status == 403:
            _LOGGER.debug(
                "DJConnect firmware release check is currently rate limited by GitHub"
            )
            return None
        _LOGGER.warning("DJConnect firmware release check failed: %s", exc)
        return None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("DJConnect firmware release check failed: %s", exc)
        return None
    if release is None:
        _LOGGER.debug(
            "DJConnect firmware repo %s has no release for channel %s",
            repo,
            channel,
        )
        return None

    version = normalize_version(release.get("tag_name")) or "0.0.0"
    device = config.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)
    assets = _select_release_assets(release.get("assets", []))

    if assets.manifest is None:
        _LOGGER.warning(
            "DJConnect latest release %s has no firmware_manifest.json",
            version,
        )
        return None
    manifest = await _fetch_manifest(session, assets.manifest)
    selected_firmware = _select_manifest_firmware(manifest, device)
    if selected_firmware is None:
        _LOGGER.warning(
            "DJConnect firmware manifest for %s has no firmware for device %s",
            version,
            device,
        )
        return None
    target_device = str(selected_firmware.get("device") or device).strip()
    if target_device not in SUPPORTED_FIRMWARE_DEVICES:
        _LOGGER.warning(
            "DJConnect firmware manifest for %s targets unsupported device %s",
            version,
            target_device,
        )
    asset_name = str(selected_firmware.get("asset") or "").strip()
    firmware_url = str(selected_firmware.get("url") or "").strip()
    if not firmware_url and asset_name:
        firmware_url = _release_asset_url(release.get("assets", []), asset_name) or ""
    if not firmware_url:
        _LOGGER.warning(
            "DJConnect firmware manifest for %s device %s has no firmware URL",
            version,
            target_device,
        )
        return None

    return FirmwareRelease(
        version=normalize_version(manifest.get("version")) or version,
        title=release.get("name") or release.get("tag_name") or version,
        body=release.get("body"),
        firmware_url=firmware_url,
        firmware_asset=asset_name,
        manifest_url=_asset_download_url(assets.manifest),
        sha256=selected_firmware.get("sha256") or await _fetch_sha256(session, assets.sha256),
        device=target_device,
        size=_manifest_size(selected_firmware.get("size")),
        min_ha_integration=manifest.get("min_ha_integration"),
    )


def _firmware_channel(value: Any) -> str:
    channel = str(value or DEFAULT_FIRMWARE_CHANNEL).strip().lower()
    return FIRMWARE_CHANNEL_BETA if channel == FIRMWARE_CHANNEL_BETA else DEFAULT_FIRMWARE_CHANNEL


async def _fetch_release_json(
    session: Any,
    repo: str,
    channel: str,
) -> dict[str, Any] | None:
    if channel == FIRMWARE_CHANNEL_BETA:
        return await _fetch_latest_prerelease_json(session, repo)
    return await _fetch_latest_release_json(session, repo)


async def _fetch_latest_release_json(session: Any, repo: str) -> dict[str, Any] | None:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    async with session.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=ClientTimeout(total=20),
    ) as resp:
        if resp.status == 404:
            _LOGGER.warning("DJConnect firmware repo has no latest release: %s", repo)
            return None
        resp.raise_for_status()
        return await resp.json()


async def _fetch_latest_prerelease_json(session: Any, repo: str) -> dict[str, Any] | None:
    url = f"https://api.github.com/repos/{repo}/releases?per_page=20"
    async with session.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=ClientTimeout(total=20),
    ) as resp:
        if resp.status == 404:
            _LOGGER.warning("DJConnect firmware repo has no releases: %s", repo)
            return None
        resp.raise_for_status()
        releases = await resp.json()
    if not isinstance(releases, list):
        return None
    for release in releases:
        if isinstance(release, dict) and release.get("prerelease"):
            return release
    return None


def _select_release_assets(assets: list[dict[str, Any]]) -> FirmwareAssets:
    selected = FirmwareAssets()
    for asset in assets:
        name = asset.get("name", "")
        if name in {
            "djconnect-firmware-manifest.json",
            "firmware_manifest.json",
            "manifest.json",
        }:
            selected.manifest = asset
        elif name.endswith(".sha256") or name == "sha256.txt":
            selected.sha256 = asset
    return selected


def _select_manifest_firmware(
    manifest: dict[str, Any],
    device: str,
) -> dict[str, Any] | None:
    firmwares = manifest.get("firmwares")
    if not isinstance(firmwares, list):
        return None
    wanted = str(device or DEFAULT_FIRMWARE_DEVICE).strip()
    for firmware in firmwares:
        if not isinstance(firmware, dict):
            continue
        if str(firmware.get("device") or "").strip() == wanted:
            return firmware
    return None


def _release_asset_url(assets: list[dict[str, Any]], asset_name: str) -> str | None:
    for asset in assets:
        if asset.get("name") == asset_name:
            return asset.get("browser_download_url")
    return None


async def _fetch_manifest(session: Any, asset: dict[str, Any] | None) -> dict[str, Any]:
    if asset is None:
        return {}
    try:
        async with session.get(
            asset["browser_download_url"],
            timeout=ClientTimeout(total=15),
        ) as resp:
            if not resp.ok:
                return {}
            return json.loads(await resp.text())
    except json.JSONDecodeError as exc:
        _LOGGER.warning("DJConnect firmware manifest is not valid JSON: %s", exc)
        return {}
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("DJConnect could not read firmware manifest: %s", exc)
        return {}


async def _fetch_sha256(session: Any, asset: dict[str, Any] | None) -> str | None:
    if asset is None:
        return None
    try:
        async with session.get(
            asset["browser_download_url"],
            timeout=ClientTimeout(total=15),
        ) as resp:
            if not resp.ok:
                return None
            match = re.search(r"\b[a-fA-F0-9]{64}\b", await resp.text())
            return match.group(0).lower() if match else None
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("DJConnect could not read sha256 asset: %s", exc)
        return None


def _asset_download_url(asset: dict[str, Any] | None) -> str | None:
    return asset["browser_download_url"] if asset else None


def _manifest_size(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
