from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

from aiohttp import ClientTimeout
from awesomeversion import AwesomeVersion
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .const import (
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
)

_LOGGER = logging.getLogger(__name__)
SUPPORTED_FIRMWARE_DEVICES = {"lilygo-t-embed-s3"}


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
    firmware: dict[str, Any] | None = None
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
    release = await _fetch_latest_release_json(session, repo)
    if release is None:
        return None

    version = normalize_version(release.get("tag_name")) or "0.0.0"
    prefix = config.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)
    device = config.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)
    assets = _select_release_assets(release.get("assets", []), prefix)

    if assets.firmware is None:
        _LOGGER.warning("SpotifyDJ latest release %s has no matching .bin asset with prefix %s", version, prefix)
        return None

    if assets.manifest is None:
        _LOGGER.warning(
            "SpotifyDJ latest release %s has no firmware_manifest.json; using safe fallback metadata",
            version,
        )
    manifest = await _fetch_manifest(session, assets.manifest)
    sha256 = manifest.get("sha256") or await _fetch_sha256(session, assets.sha256)
    target_device = manifest.get("device") or device
    if not manifest.get("device"):
        _LOGGER.warning(
            "SpotifyDJ firmware manifest for %s has no device target; using fallback %s",
            version,
            target_device,
        )
    elif target_device not in SUPPORTED_FIRMWARE_DEVICES:
        _LOGGER.warning(
            "SpotifyDJ firmware manifest for %s targets unsupported device %s",
            version,
            target_device,
        )

    return FirmwareRelease(
        version=normalize_version(manifest.get("version")) or version,
        title=release.get("name") or release.get("tag_name") or version,
        body=release.get("body"),
        firmware_url=assets.firmware["browser_download_url"],
        firmware_asset=assets.firmware["name"],
        manifest_url=_asset_download_url(assets.manifest),
        sha256=sha256,
        device=target_device,
        size=_manifest_size(manifest.get("size")),
        min_ha_integration=manifest.get("min_ha_integration"),
    )


async def _fetch_latest_release_json(session: Any, repo: str) -> dict[str, Any] | None:
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    async with session.get(
        url,
        headers={"Accept": "application/vnd.github+json"},
        timeout=ClientTimeout(total=20),
    ) as resp:
        if resp.status == 404:
            _LOGGER.warning("SpotifyDJ firmware repo has no latest release: %s", repo)
            return None
        resp.raise_for_status()
        return await resp.json()


def _select_release_assets(assets: list[dict[str, Any]], prefix: str) -> FirmwareAssets:
    selected = FirmwareAssets()
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".bin") and prefix in name:
            selected.firmware = asset
        elif name in {
            "spotifydj-firmware-manifest.json",
            "firmware_manifest.json",
            "manifest.json",
        }:
            selected.manifest = asset
        elif name.endswith(".sha256") or name == "sha256.txt":
            selected.sha256 = asset
    return selected


async def _fetch_manifest(session: Any, asset: dict[str, Any] | None) -> dict[str, Any]:
    if asset is None:
        return {}
    try:
        async with session.get(
            asset["browser_download_url"],
            timeout=ClientTimeout(total=15),
        ) as resp:
            return await resp.json() if resp.ok else {}
    except Exception as exc:  # noqa: BLE001
        _LOGGER.warning("SpotifyDJ could not read firmware manifest: %s", exc)
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
        _LOGGER.warning("SpotifyDJ could not read sha256 asset: %s", exc)
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
