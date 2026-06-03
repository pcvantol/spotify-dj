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


async def fetch_latest_firmware_release(hass: HomeAssistant, config: dict[str, Any]) -> FirmwareRelease | None:
    repo = config.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO).strip()
    if not repo or "/" not in repo:
        return None
    url = f"https://api.github.com/repos/{repo}/releases/latest"
    session = async_get_clientsession(hass)
    async with session.get(url, headers={"Accept": "application/vnd.github+json"}, timeout=ClientTimeout(total=20)) as resp:
        if resp.status == 404:
            _LOGGER.warning("SpotifyDJ firmware repo has no latest release: %s", repo)
            return None
        resp.raise_for_status()
        release = await resp.json()

    version = normalize_version(release.get("tag_name")) or "0.0.0"
    assets = release.get("assets", [])
    prefix = config.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)
    device = config.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)

    firmware_asset = None
    manifest_asset = None
    sha_asset = None
    for asset in assets:
        name = asset.get("name", "")
        if name.endswith(".bin") and prefix in name:
            firmware_asset = asset
        elif name in {"spotifydj-firmware-manifest.json", "manifest.json"}:
            manifest_asset = asset
        elif name.endswith(".sha256") or name == "sha256.txt":
            sha_asset = asset

    if firmware_asset is None:
        _LOGGER.warning("SpotifyDJ latest release %s has no matching .bin asset with prefix %s", version, prefix)
        return None

    manifest: dict[str, Any] = {}
    if manifest_asset:
        try:
            async with session.get(manifest_asset["browser_download_url"], timeout=ClientTimeout(total=15)) as resp:
                if resp.ok:
                    manifest = await resp.json()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("SpotifyDJ could not read firmware manifest: %s", exc)

    sha256 = manifest.get("sha256")
    if not sha256 and sha_asset:
        try:
            async with session.get(sha_asset["browser_download_url"], timeout=ClientTimeout(total=15)) as resp:
                if resp.ok:
                    text = await resp.text()
                    match = re.search(r"\b[a-fA-F0-9]{64}\b", text)
                    if match:
                        sha256 = match.group(0).lower()
        except Exception as exc:  # noqa: BLE001
            _LOGGER.warning("SpotifyDJ could not read sha256 asset: %s", exc)

    return FirmwareRelease(
        version=normalize_version(manifest.get("version")) or version,
        title=release.get("name") or release.get("tag_name") or version,
        body=release.get("body"),
        firmware_url=firmware_asset["browser_download_url"],
        firmware_asset=firmware_asset["name"],
        manifest_url=manifest_asset["browser_download_url"] if manifest_asset else None,
        sha256=sha256,
        device=manifest.get("device") or device,
        min_ha_integration=manifest.get("min_ha_integration"),
    )


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
