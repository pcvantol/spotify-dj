from __future__ import annotations

import asyncio
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    API_COMMAND,
    API_EVENT,
    API_PAIR,
    API_SPOTIFY_CALLBACK,
    API_STATUS,
    API_TTS,
    API_VOICE,
    CONF_ASSIST_PIPELINE_ID,
    CONF_CLIENT_TYPE,
    CONF_DEVICE_ID,
    CONF_DEVICE_LANGUAGE,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_HA_EXTERNAL_URL,
    CONF_LOCAL_URL,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_DEVICE_LANGUAGE,
    DEFAULT_CLIENT_TYPE,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .http import (
    DJConnectCommandView,
    DJConnectEventView,
    DJConnectPairView,
    DJConnectSpotifyCallbackView,
    DJConnectStatusView,
    DJConnectTtsView,
    DJConnectVoiceDebugView,
    DJConnectVoiceView,
)
from .assist_stt import detect_stt_support
from .dj_response import async_send_dj_response, async_send_dj_response_best_effort
from .ha_urls import async_ha_url_payload
from .processor import process_text_command
from .repairs import async_create_fixable_issues
from .spotify_oauth import (
    build_authorize_url,
    build_redirect_uri,
    create_code_verifier,
    ensure_spotify_scopes,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_TEST_COMMAND = "Ik wil het nieuwste album van Pearl Jam horen"
DEFAULT_TEST_TTS_TEXT = (
    "Daar gaan we. DJConnect is gekoppeld, de stem werkt, "
    "en ik sta klaar voor je volgende plaat."
)
MDNS_SERVICE_TYPE = "_djconnect._tcp.local."
STATUS_SECRET_KEYS = {"device_token", "spotify_refresh_token", "refresh_token"}
REAL_DJCONNECT_DEVICE_ID_PATTERN = re.compile(
    r"djconnect-(?:lilygo-t-embed-s3|esp32-s3-box-3|lilygo)-[0-9A-Fa-f]{12}"
)
CONF_LAST_DEVICE_STATUS = "last_device_status"


def _is_empty_status_value(value: Any) -> bool:
    return value is None or value == "" or value == [] or value == {}


def _merge_cached_device_status(
    device_status: dict[str, Any],
    update: dict[str, Any],
    *,
    source: str,
    allow_empty_keys: set[str] | None = None,
) -> None:
    """Merge device status without erasing known values from sparse payloads."""
    allow_empty_keys = allow_empty_keys or set()
    if not update:
        _LOGGER.debug("Ignoring empty %s payload for device sensor update", source)
        return
    _LOGGER.debug("Merging %s payload without resetting missing fields", source)
    for key, value in update.items():
        if key in STATUS_SECRET_KEYS:
            continue
        if key == "ha_pairing_status" and value in (None, "", "unknown"):
            continue
        if _is_empty_status_value(value) and key in device_status and key not in allow_empty_keys:
            continue
        device_status[key] = value


def _runtime_last_command_value(runtime: Any) -> str | None:
    for key in ("last_dj_text", "last_text", "last_stt_text"):
        value = getattr(runtime, key, None)
        if value not in (None, ""):
            return str(value)
    return None


def _runtime_last_track_value(runtime: Any) -> str | None:
    playback = getattr(runtime, "last_playback", None) or {}
    if isinstance(playback, dict):
        for key in ("track_name", "title", "name", "track"):
            value = playback.get(key)
            if value not in (None, ""):
                return str(value)
        response = playback.get("device_response") or {}
        if isinstance(response, dict):
            current = response.get("playback") or response
            if isinstance(current, dict):
                for key in ("track_name", "title", "name", "track"):
                    value = current.get(key)
                    if value not in (None, ""):
                        return str(value)
    resolved = getattr(runtime, "last_resolved_media", None) or {}
    if isinstance(resolved, dict):
        for key in ("track_name", "title", "name", "artist", "artist_name"):
            value = resolved.get(key)
            if value not in (None, ""):
                return str(value)
    return None


def _cache_runtime_last_values(runtime: Any) -> None:
    """Mirror non-empty runtime command/playback values into cached device status."""
    status = getattr(runtime, "device_status", None)
    if not isinstance(status, dict):
        return
    last_command = _runtime_last_command_value(runtime)
    if last_command:
        status["last_command"] = last_command
    last_dj_text = getattr(runtime, "last_dj_text", None)
    if last_dj_text not in (None, ""):
        status["last_dj_text"] = str(last_dj_text)
    last_track = _runtime_last_track_value(runtime)
    if last_track:
        status["last_track"] = last_track


@dataclass
class DJConnectRuntime:
    entry: ConfigEntry
    last_text: str | None = None
    last_intent: dict[str, Any] | None = None
    last_dj_text: str | None = None
    last_dj_spoken: bool | None = None
    last_dj_displayed: bool | None = None
    last_dj_response_at: float | None = None
    last_error: str | None = None
    last_playback: dict[str, Any] | None = None
    device_status: dict[str, Any] = field(default_factory=dict)
    device_token: str | None = None
    pairing_code: str | None = None
    pairing_device_id: str | None = None
    ota_in_progress: bool = False
    ota_last_error: str | None = None
    latest_spotify_refresh_token: str | None = None
    listeners: list = field(default_factory=list)

    @property
    def config(self) -> dict[str, Any]:
        data = dict(self.entry.data)
        data.update(dict(self.entry.options))
        return data

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        _cache_runtime_last_values(self)
        for listener in list(self.listeners):
            listener()

    def ensure_device_token(self) -> str:
        if not self.device_token:
            self.device_token = secrets.token_urlsafe(32)
        return self.device_token

    async def async_device_local_url(self, hass: HomeAssistant) -> str | None:
        """Return the best known device base URL."""
        local_url = (
            self.device_status.get("local_url")
            or self.device_status.get("ota_url")
            or self.config.get(CONF_LOCAL_URL)
        )
        if local_url:
            local_url = str(local_url)
            if not _is_pair_code_mdns_url(local_url):
                return local_url
            _LOGGER.debug("DJConnect ignoring pair-code based mDNS URL: %s", local_url)
        discovered_url = await async_discover_device_url(hass, self)
        if discovered_url:
            self.device_status["local_url"] = discovered_url
            return discovered_url
        device_id = self.device_status.get("device_id") or self.pairing_device_id
        device_id = device_id or self.config.get(CONF_DEVICE_ID)
        return _device_id_mdns_fallback_url(device_id)

    def device_headers(self, *, include_device_id: bool = True) -> dict[str, str]:
        """Build headers for authenticated ESP requests."""
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"
        if include_device_id and self.device_status.get("device_id"):
            headers["X-DJConnect-Device-ID"] = self.device_status["device_id"]
        return headers

    def authorize_device_request(
        self,
        headers: Any,
        body_device_id: str | None = None,
        client_type: str | None = None,
    ) -> bool:
        auth = str(headers.get("Authorization", "") or "").strip()
        token = auth.removeprefix("Bearer ").strip()
        header_device = str(headers.get("X-DJConnect-Device-ID") or "").strip()
        body_device = str(body_device_id or "").strip()
        token_match = bool(self.device_token and token == self.device_token)
        expected_present = bool(self.device_token)
        device_id = header_device or body_device or None
        _LOGGER.debug(
            "DJConnect device auth: device_id=%s auth=%s token_match=%s "
            "expected_token_present=%s entry_id=%s",
            device_id,
            "present" if auth else "missing",
            token_match,
            expected_present,
            getattr(self.entry, "entry_id", None),
        )
        if not token_match:
            self._log_device_auth_failure(
                "missing_device_token" if not token else "invalid_device_token",
                header_device,
                body_device,
                client_type,
                bool(token),
            )
            return False
        known_device = self.device_status.get("device_id") or self.pairing_device_id
        if known_device and header_device and not _device_id_matches(known_device, header_device):
            self._log_device_auth_failure(
                "header_device_id_mismatch",
                header_device,
                body_device,
                client_type,
                bool(token),
            )
            return False
        if known_device and body_device and not _device_id_matches(known_device, body_device):
            self._log_device_auth_failure(
                "body_device_id_mismatch",
                header_device,
                body_device,
                client_type,
                bool(token),
            )
            return False
        self._learn_device_id(header_device or body_device)
        return True

    def _log_device_auth_failure(
        self,
        reason: str,
        header_device_id: str,
        body_device_id: str,
        client_type: str | None,
        token_present: bool,
    ) -> None:
        known_device = self.device_status.get("device_id") or self.pairing_device_id
        received_device = header_device_id or body_device_id or ""
        _LOGGER.warning(
            "DJConnect ESP request rejected: reason=%s received_device_id=%s "
            "known_device_id=%s client_type=%s token_present=%s entry_id=%s",
            reason,
            received_device or "missing",
            known_device or "missing",
            str(client_type or "").strip() or "missing",
            token_present,
            getattr(self.entry, "entry_id", None),
        )

    def _learn_device_id(self, device_id: str | None) -> None:
        """Adopt the ESP's real device ID after setup-code based pairing."""
        if not device_id or not _is_real_djconnect_device_id(device_id):
            return
        known_device = self.device_status.get("device_id") or self.pairing_device_id
        if known_device == device_id:
            return
        if known_device and not (
            _is_setup_code_device_id(str(known_device))
            or _is_real_djconnect_device_id(str(known_device))
        ):
            return
        self.pairing_device_id = device_id
        self.device_status["device_id"] = device_id
        _LOGGER.debug(
            "DJConnect learned real device_id=%s for entry_id=%s",
            device_id,
            getattr(self.entry, "entry_id", None),
        )

    def get_current_spotify_credentials(self) -> dict[str, Any]:
        """Return canonical latest Spotify credentials for HA backend use."""
        conf = self.config
        client_id = str(conf.get(CONF_SPOTIFY_CLIENT_ID) or "").strip()
        refresh_token = str(
            self.latest_spotify_refresh_token
            or conf.get(CONF_SPOTIFY_REFRESH_TOKEN)
            or ""
        ).strip()
        if not client_id or not refresh_token:
            return {}
        scopes = str(conf.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES)).split()
        market = conf.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET)
        return {
            "client_id": client_id,
            "refresh_token": refresh_token,
            "spotify_client_id": client_id,
            "spotify_refresh_token": refresh_token,
            "spotify_market": market,
            "spotify_scopes": scopes,
            "market": market,
            "scopes": scopes,
        }

    def spotify_payload(self) -> dict[str, Any]:
        """Return Spotify credentials for HA backend compatibility helpers."""
        return self.get_current_spotify_credentials()

    def update_spotify_refresh_token(self, refresh_token: str | None) -> bool:
        """Update the in-memory latest Spotify refresh token if Spotify rotated it."""
        token = str(refresh_token or "").strip()
        if not token:
            return False
        current = str(
            self.latest_spotify_refresh_token
            or self.config.get(CONF_SPOTIFY_REFRESH_TOKEN)
            or ""
        )
        if token == current:
            return False
        self.latest_spotify_refresh_token = token
        return True

    def device_language(self) -> str:
        """Return the ESP UI language provisioned during pairing."""
        language = str(self.config.get(CONF_DEVICE_LANGUAGE) or DEFAULT_DEVICE_LANGUAGE)
        return "nl" if language.lower().startswith("nl") else "en"

    def client_type(self) -> str:
        """Return the paired DJConnect client type."""
        client_type = str(
            self.device_status.get(CONF_CLIENT_TYPE)
            or self.config.get(CONF_CLIENT_TYPE)
            or DEFAULT_CLIENT_TYPE
        ).strip()
        return client_type or DEFAULT_CLIENT_TYPE

    async def async_device_get(self, hass: HomeAssistant, path: str) -> dict[str, Any]:
        """Call an authenticated local ESP GET endpoint."""
        local_url = await self.async_device_local_url(hass)
        if not local_url:
            raise RuntimeError("DJConnect device local_url is unknown")
        session = async_get_clientsession(hass)
        async with session.get(
            local_url.rstrip("/") + path,
            headers=self.device_headers(),
            timeout=ClientTimeout(total=10),
        ) as resp:
            text = await resp.text()
            if resp.status in (401, 403, 404):
                self.update(last_error=f"DJConnect pairing is stale: HTTP {resp.status}")
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"ESP GET {path} failed HTTP {resp.status}: {text}")
            try:
                return json.loads(text) if text else {"success": True}
            except json.JSONDecodeError:
                return {"success": True, "response": text}

    async def async_device_post(
        self,
        hass: HomeAssistant,
        path: str,
        payload: dict[str, Any] | None = None,
        *,
        timeout: int = 15,
    ) -> dict[str, Any]:
        """Call an authenticated local ESP POST endpoint."""
        local_url = await self.async_device_local_url(hass)
        if not local_url:
            raise RuntimeError("DJConnect device local_url is unknown")
        session = async_get_clientsession(hass)
        async with session.post(
            local_url.rstrip("/") + path,
            json=payload or {},
            headers=self.device_headers(),
            timeout=ClientTimeout(total=timeout),
        ) as resp:
            text = await resp.text()
            if resp.status in (401, 403, 404):
                self.update(last_error=f"DJConnect pairing is stale: HTTP {resp.status}")
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"ESP POST {path} failed HTTP {resp.status}: {text}")
            try:
                return json.loads(text) if text else {"success": True}
            except json.JSONDecodeError:
                return {"success": True, "response": text}

    async def async_device_command(
        self,
        hass: HomeAssistant,
        command: str,
        **values: Any,
    ) -> dict[str, Any]:
        """Send a command to the ESP local command API."""
        payload = {"command": command}
        payload.update({key: value for key, value in values.items() if value is not None})
        result = await self.async_device_post(hass, "/api/device/command", payload)
        if isinstance(result, dict):
            status = result.get("status") or result.get("device_status")
            if isinstance(status, dict):
                _merge_cached_device_status(
                    self.device_status,
                    status,
                    source="ESP command status",
                )
            _merge_cached_device_status(
                self.device_status,
                {
                    key: result[key]
                    for key in ("spotify_status", "ha_pairing_status", "sound_output")
                    if key in result
                },
                source="ESP command response",
            )
        self.update(last_error=None)
        return result

    async def async_refresh_device_info(self, hass: HomeAssistant) -> dict[str, Any]:
        """Refresh local ESP device info through the local API."""
        data = await self.async_device_get(hass, "/api/device/info")
        status = data.get("status") if isinstance(data, dict) else None
        if isinstance(status, dict):
            _merge_cached_device_status(
                self.device_status,
                status,
                source="ESP device info status",
            )
        if isinstance(data, dict):
            _merge_cached_device_status(
                self.device_status,
                {
                    key: value
                    for key, value in data.items()
                    if key not in STATUS_SECRET_KEYS
                },
                source="ESP device info",
            )
        self.update(last_error=None)
        return data

    async def start_ota(self, hass: HomeAssistant, release: Any) -> None:
        local_url = await self.async_device_local_url(hass)
        if not local_url:
            raise RuntimeError(
                "DJConnect device local_url is unknown; send a /status update first"
            )
        url = local_url.rstrip("/") + "/api/device/ota"
        payload = {
            "version": release.version,
            "url": release.firmware_url,
            "sha256": release.sha256,
            "device": release.device,
            "asset": release.firmware_asset,
        }
        self.ota_in_progress = True
        self.ota_last_error = None
        self.update()
        session = async_get_clientsession(hass)
        try:
            async with session.post(
                url,
                json=payload,
                headers=self.device_headers(),
                timeout=ClientTimeout(total=30),
            ) as resp:
                text = await resp.text()
                if resp.status < 200 or resp.status >= 300:
                    raise RuntimeError(
                        f"ESP OTA request failed HTTP {resp.status}: {text}"
                    )
                _LOGGER.info("DJConnect OTA accepted by device: %s", text)
        except Exception as exc:  # noqa: BLE001
            self.ota_in_progress = False
            self.ota_last_error = str(exc)
            self.update()
            raise

    async def pair_device(self, hass: HomeAssistant) -> dict[str, Any]:
        conf = self.config
        local_url = await self.async_device_local_url(hass)
        if not local_url:
            raise RuntimeError("DJConnect device local_url is unknown")
        session = async_get_clientsession(hass)
        pairing_info: dict[str, Any] = {}
        try:
            async with session.get(
                local_url.rstrip("/") + "/api/device/pairing-info",
                timeout=ClientTimeout(total=10),
            ) as resp:
                text = await resp.text()
                if resp.status < 200 or resp.status >= 300:
                    raise RuntimeError(
                        f"ESP pairing info failed HTTP {resp.status}: {text}"
                    )
                pairing_info = json.loads(text) if text else {}
        except json.JSONDecodeError as exc:
            raise RuntimeError("ESP pairing info returned invalid JSON") from exc

        expected_pair_code = str(conf.get(CONF_PAIR_CODE) or "").strip()
        reported_pair_code = str(pairing_info.get("pair_code") or "").strip()
        if expected_pair_code and reported_pair_code and expected_pair_code != reported_pair_code:
            raise RuntimeError("ESP pairing code does not match this setup")
        reported_device_id = str(pairing_info.get("device_id") or "").strip()
        if reported_device_id:
            self._learn_device_id(reported_device_id)
        reported_local_url = str(pairing_info.get("local_url") or "").strip()
        if reported_local_url:
            self.device_status["local_url"] = reported_local_url
        token = self.ensure_device_token()
        url = local_url.rstrip("/") + "/api/device/pair"
        payload = {
            "pair_code": conf.get(CONF_PAIR_CODE),
            "device_id": reported_device_id or conf.get(CONF_DEVICE_ID),
            "device_name": conf.get(CONF_DEVICE_NAME, "DJConnect"),
            "client_type": self.client_type(),
            "device_language": self.device_language(),
            "language": self.device_language(),
            "device_token": token,
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
        }
        payload.update(await async_ha_url_payload(hass, conf))
        if not payload.get("ha_local_url") and not payload.get("ha_remote_url"):
            raise RuntimeError("Home Assistant local or remote URL is required for pairing")
        async with session.post(
            url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"ESP pairing failed HTTP {resp.status}: {text}")
            return json.loads(text) if text else {"success": True}

async def async_discover_device_url(
    hass: HomeAssistant,
    runtime: DJConnectRuntime,
) -> str | None:
    """Resolve the DJConnect device URL from the `_djconnect._tcp` mDNS service."""
    try:
        from homeassistant.components import zeroconf

        zc = await zeroconf.async_get_async_instance(hass)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect mDNS discovery unavailable", exc_info=True)
        return None

    for service_name in _mdns_service_name_candidates(runtime):
        info = await _async_get_mdns_service_info(zc, service_name)
        url = _url_from_service_info(info, runtime)
        if url:
            _LOGGER.debug("DJConnect discovered device URL via mDNS: %s", url)
            return url
    url = await _async_discover_single_mdns_service_url(zc)
    if url:
        _LOGGER.debug("DJConnect discovered single visible device URL via mDNS: %s", url)
        return url
    return None


async def _async_get_mdns_service_info(async_zc: Any, service_name: str) -> Any:
    """Read one mDNS service record using HA's AsyncZeroconf wrapper."""
    getter = getattr(async_zc, "async_get_service_info", None)
    if getter is None:
        return None
    try:
        return await getter(MDNS_SERVICE_TYPE, service_name)
    except Exception:  # noqa: BLE001
        _LOGGER.debug(
            "DJConnect mDNS lookup failed for %s",
            service_name,
            exc_info=True,
        )
        return None


async def _async_discover_single_mdns_service_url(async_zc: Any) -> str | None:
    """Browse `_djconnect._tcp` and return the only visible DJConnect device URL."""
    try:
        from zeroconf import ServiceStateChange
        from zeroconf.asyncio import AsyncServiceBrowser
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect mDNS browse fallback unavailable", exc_info=True)
        return None

    service_names: set[str] = set()

    def _on_service_state_change(
        zeroconf: Any,
        service_type: str,
        name: str,
        state_change: Any,
    ) -> None:
        if state_change == ServiceStateChange.Added:
            service_names.add(name)

    browser = None
    try:
        zc = getattr(async_zc, "zeroconf", async_zc)
        browser = AsyncServiceBrowser(
            zc,
            MDNS_SERVICE_TYPE,
            handlers=[_on_service_state_change],
        )
        await asyncio.sleep(2)
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect mDNS browse fallback failed", exc_info=True)
        return None
    finally:
        if browser is not None:
            cancel = getattr(browser, "async_cancel", None)
            if cancel is not None:
                result = cancel()
                if hasattr(result, "__await__"):
                    await result

    infos = [
        await _async_get_mdns_service_info(async_zc, service_name)
        for service_name in sorted(service_names)
    ]
    urls = [url for info in infos if (url := _url_from_service_info_unmatched(info))]
    unique_urls = list(dict.fromkeys(urls))
    if len(unique_urls) == 1:
        return unique_urls[0]
    if len(unique_urls) > 1:
        _LOGGER.warning(
            "DJConnect found multiple mDNS devices; set the manual device URL in options"
        )
    return None


def _mdns_service_name_candidates(runtime: DJConnectRuntime) -> list[str]:
    """Build likely `_djconnect._tcp` instance names for the paired device."""
    device_id = _runtime_device_id(runtime)
    if not device_id:
        return []
    names = [
        f"{device_id}.{MDNS_SERVICE_TYPE}",
        f"{device_id.upper()}.{MDNS_SERVICE_TYPE}",
    ]
    if device_id.startswith("djconnect-"):
        suffix = device_id.removeprefix("djconnect-")
        names.extend(
            [
                f"DJConnect {suffix}.{MDNS_SERVICE_TYPE}",
                f"DJConnect {suffix.upper()}.{MDNS_SERVICE_TYPE}",
            ]
        )
    return list(dict.fromkeys(names))


def _runtime_device_id(runtime: DJConnectRuntime) -> str:
    """Return the known DJConnect device identifier, when available."""
    return str(
        runtime.device_status.get("device_id")
        or runtime.pairing_device_id
        or runtime.config.get(CONF_DEVICE_ID)
        or ""
    ).strip()


def _device_id_mdns_fallback_url(device_id: Any) -> str | None:
    """Return a fallback URL only for real DJConnect device IDs."""
    normalized = str(device_id or "").strip()
    if _is_real_djconnect_device_id(normalized):
        return f"http://{normalized}.local"
    return None


def _is_real_djconnect_device_id(device_id: str) -> bool:
    return bool(REAL_DJCONNECT_DEVICE_ID_PATTERN.fullmatch(str(device_id or "").strip()))


def _is_setup_code_device_id(device_id: str) -> bool:
    return bool(re.fullmatch(r"djconnect-\d{6}", str(device_id or "").strip()))


def _device_id_matches(known_device: str, request_device: str) -> bool:
    """Allow the ESP real ID to replace a temporary setup-code ID."""
    known = str(known_device or "").strip()
    requested = str(request_device or "").strip()
    if not known or not requested or known == requested:
        return True
    if _is_setup_code_device_id(known) and _is_real_djconnect_device_id(requested):
        return True
    return _is_real_djconnect_device_id(known) and _is_real_djconnect_device_id(requested)


def _is_pair_code_mdns_url(value: str) -> bool:
    """Detect obsolete fallback URLs created from short setup pair codes."""
    return bool(re.fullmatch(r"https?://djconnect-\d{6}\.local/?", value.strip()))


def _url_from_service_info(info: Any, runtime: DJConnectRuntime) -> str | None:
    if info is None:
        return None
    name = str(getattr(info, "name", "") or "").lower()
    device_id = _runtime_device_id(runtime)
    if device_id and not _mdns_name_matches_device(name, device_id):
        return None
    host = (
        getattr(info, "server", None)
        or getattr(info, "host", None)
        or getattr(info, "hostname", None)
    )
    port = int(getattr(info, "port", 80) or 80)
    if not host:
        return None
    host = str(host).rstrip(".")
    return f"http://{host}:{port}" if port != 80 else f"http://{host}"


def _url_from_service_info_unmatched(info: Any) -> str | None:
    """Build a URL from an mDNS service record without device-id filtering."""
    if info is None:
        return None
    host = (
        getattr(info, "server", None)
        or getattr(info, "host", None)
        or getattr(info, "hostname", None)
    )
    port = int(getattr(info, "port", 80) or 80)
    if not host:
        return None
    host = str(host).rstrip(".")
    return f"http://{host}:{port}" if port != 80 else f"http://{host}"


def _mdns_name_matches_device(name: str, device_id: str) -> bool:
    """Match full device IDs and friendly `DJConnect xxxx` mDNS names."""
    normalized_name = name.lower()
    normalized_id = device_id.lower()
    if normalized_id in normalized_name:
        return True
    if normalized_id.startswith("djconnect-"):
        suffix = normalized_id.removeprefix("djconnect-")
        return f"djconnect {suffix}" in normalized_name
    return False


def _service_text(call: ServiceCall, default: str, *aliases: str) -> str:
    """Return normalized service text while keeping developer actions forgiving."""
    for key in ("text", *aliases):
        value = call.data.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return str(default).strip()


async def async_speak_dj_test(
    hass: HomeAssistant,
    runtime: DJConnectRuntime,
    text: str,
) -> dict[str, Any]:
    """Send a DJ test response to the DJConnect device display/speaker."""
    _LOGGER.debug("DJConnect test_tts sending DJ response to device")
    result = await async_send_dj_response(hass, runtime, text)
    return {"text": text, **result}


def register_http_views(hass: HomeAssistant) -> None:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("http_registered"):
        for view in [
            DJConnectVoiceView(hass),
            DJConnectCommandView(hass),
            DJConnectPairView(hass),
            DJConnectStatusView(hass),
            DJConnectEventView(hass),
            DJConnectTtsView(hass),
            DJConnectVoiceDebugView(hass),
            DJConnectSpotifyCallbackView(hass),
        ]:
            hass.http.register_view(view)
        hass.data[DOMAIN]["http_registered"] = True

        _LOGGER.info(
            "DJConnect HTTP endpoints registered: %s, %s, %s, %s, %s, %s, %s",
            API_VOICE,
            API_COMMAND,
            API_PAIR,
            API_STATUS,
            API_EVENT,
            API_TTS,
            API_SPOTIFY_CALLBACK,
        )


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    register_http_views(hass)
    return True


def _restore_runtime(hass: HomeAssistant, entry: ConfigEntry) -> DJConnectRuntime:
    runtime = DJConnectRuntime(entry=entry)
    cached_status = entry.data.get(CONF_LAST_DEVICE_STATUS)
    if isinstance(cached_status, dict):
        _merge_cached_device_status(
            runtime.device_status,
            cached_status,
            source="persisted device status",
        )
    if entry.data.get(CONF_SPOTIFY_REFRESH_TOKEN):
        runtime.latest_spotify_refresh_token = entry.data[CONF_SPOTIFY_REFRESH_TOKEN]
    if entry.data.get(CONF_DEVICE_TOKEN):
        runtime.device_token = entry.data[CONF_DEVICE_TOKEN]
        _LOGGER.debug(
            "DJConnect restored existing device token for entry %s",
            entry.entry_id,
        )
    if entry.data.get(CONF_DEVICE_ID):
        runtime.pairing_device_id = str(entry.data[CONF_DEVICE_ID])
        runtime.device_status["device_id"] = str(entry.data[CONF_DEVICE_ID])
    if entry.data.get(CONF_PAIR_CODE):
        runtime.pairing_code = str(entry.data[CONF_PAIR_CODE])
    local_url = str(entry.data.get(CONF_LOCAL_URL) or "").strip()
    if local_url and not _is_pair_code_mdns_url(local_url):
        runtime.device_status["local_url"] = local_url
    hass.data[DOMAIN][entry.entry_id] = runtime
    hass.data[DOMAIN]["runtime"] = runtime
    _LOGGER.debug("DJConnect runtime restored for entry %s", entry.entry_id)
    return runtime


def _setup_device_coordinator(hass: HomeAssistant, runtime: DJConnectRuntime) -> None:
    """Create a coordinator for explicit local device-info refreshes."""
    try:
        from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
    except Exception:  # noqa: BLE001
        _LOGGER.debug("DJConnect DataUpdateCoordinator unavailable", exc_info=True)
        return

    async def _async_update_data() -> dict[str, Any]:
        if not runtime.device_token:
            return {}
        return await runtime.async_refresh_device_info(hass)

    hass.data[DOMAIN][f"{runtime.entry.entry_id}_coordinator"] = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name="DJConnect local device API",
        update_method=_async_update_data,
    )


async def _try_initial_device_provisioning(
    hass: HomeAssistant,
    runtime: DJConnectRuntime,
) -> None:
    """Pair opportunistically without blocking HA startup when ESP is offline."""
    try:
        if not _should_startup_pair_device(runtime):
            _LOGGER.debug(
                "DJConnect startup direct pairing skipped; token is already stored"
            )
        else:
            await runtime.pair_device(hass)
        runtime.update(last_error=None)
    except Exception as exc:  # noqa: BLE001
        if _is_deferred_provisioning_error(exc):
            _LOGGER.info(
                "DJConnect device pairing deferred until device is reachable: %s",
                _format_exception(exc),
            )
            return
        message = _format_exception(exc)
        runtime.update(last_error=f"DJConnect device pairing failed: {message}")
        _LOGGER.warning("DJConnect device pairing deferred/failed: %s", message)


def _should_startup_pair_device(runtime: DJConnectRuntime) -> bool:
    """Return true only when startup has no stored ESP token yet."""
    if getattr(runtime, "device_token", None):
        return False
    status = getattr(runtime, "device_status", {}) or {}
    return status.get("ha_pairing_status") not in {"paired", "pending"}


def _is_deferred_provisioning_error(exc: Exception) -> bool:
    """Return true for expected startup-only ESP reachability failures."""
    message = str(exc)
    return any(
        marker in message
        for marker in (
            "local_url is unknown",
            "Cannot connect to host",
            "MDNS lookup failed",
            "Timeout while contacting DNS servers",
        )
    )


def _format_exception(exc: Exception) -> str:
    """Return useful text even when Home Assistant exceptions stringify empty."""
    text = str(exc).strip()
    if text:
        return text
    return f"{type(exc).__name__}: {exc!r}"


def _register_developer_services(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: DJConnectRuntime,
) -> None:
    """Register Home Assistant developer actions for parser, TTS and provisioning."""

    async def handle_test_parse(call: ServiceCall) -> dict[str, Any] | None:
        text = _service_text(call, DEFAULT_TEST_COMMAND, "command_text")
        _LOGGER.debug("DJConnect developer action test_parse: %s", text)
        result = await process_text_command(hass, runtime, text, play=False)
        _LOGGER.debug("DJConnect test_parse: %s", result)
        return result

    async def handle_test_tts(call: ServiceCall) -> dict[str, Any]:
        text = _service_text(call, DEFAULT_TEST_TTS_TEXT, "dj_response_text")
        _LOGGER.debug("DJConnect developer action test_tts: %s", text)
        result = await async_speak_dj_test(hass, runtime, text)
        _LOGGER.debug("DJConnect test_tts sent DJ response to device: %s", text)
        return result

    async def handle_test_command(call: ServiceCall) -> dict[str, Any] | None:
        text = _service_text(call, DEFAULT_TEST_COMMAND, "command_text")
        play = bool(call.data.get("play", True))
        _LOGGER.debug(
            "DJConnect developer action test_command play=%s: %s",
            play,
            text,
        )
        result = await process_text_command(hass, runtime, text, play=play)
        result["dj_response"] = await async_send_dj_response_best_effort(
            hass,
            runtime,
            result.get("dj_text") or "",
        )
        dj_response = result.get("dj_response") or {}
        _LOGGER.debug(
            "DJConnect test_command result intent=%s playback=%s dj_text=%s audio_url=%s audio_type=%s",
            result.get("intent"),
            bool(result.get("playback")),
            bool(result.get("dj_text")),
            bool(dj_response.get("audio_url")),
            dj_response.get("audio_type"),
        )
        return result

    async def handle_start_spotify_oauth(call: ServiceCall) -> dict[str, Any]:
        client_id = (
            call.data.get("client_id")
            or runtime.config.get(CONF_SPOTIFY_CLIENT_ID)
            or ""
        ).strip()
        if not client_id:
            raise RuntimeError(
                "Provide spotify_client_id or configure it in DJConnect options"
            )
        base_url = (
            call.data.get("ha_base_url")
            or runtime.config.get(CONF_HA_EXTERNAL_URL)
            or "http://homeassistant.local:8123"
        ).strip()
        scopes = ensure_spotify_scopes(
            call.data.get("scopes")
            or runtime.config.get(CONF_SPOTIFY_SCOPES)
            or DEFAULT_SPOTIFY_SCOPES
        )
        market = (
            call.data.get("market")
            or runtime.config.get(CONF_SPOTIFY_MARKET)
            or DEFAULT_SPOTIFY_MARKET
        ).strip()
        verifier = create_code_verifier()
        state = secrets.token_urlsafe(24)
        redirect_uri = build_redirect_uri(base_url)
        _LOGGER.debug(
            "DJConnect developer action start_spotify_oauth redirect_uri=%s market=%s",
            redirect_uri,
            market,
        )
        pending = hass.data.setdefault(DOMAIN, {}).setdefault(
            "spotify_oauth_pending",
            {},
        )
        pending[state] = {
            "entry_id": entry.entry_id,
            "client_id": client_id,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "market": market,
        }
        auth_url = build_authorize_url(
            client_id,
            redirect_uri,
            scopes,
            state,
            verifier,
        )
        return {"auth_url": auth_url, "redirect_uri": redirect_uri, "scopes": scopes}

    async def handle_device_command(call: ServiceCall) -> dict[str, Any]:
        command = str(call.data.get("command") or "").strip()
        if not command:
            raise RuntimeError("Provide a DJConnect device command")
        payload = dict(call.data.get("payload") or {})
        _LOGGER.debug("DJConnect developer action device_command: %s", command)
        return await runtime.async_device_command(hass, command, **payload)

    async def handle_refresh_device_info(call: ServiceCall) -> dict[str, Any]:
        _LOGGER.debug("DJConnect developer action refresh_device_info started")
        return await runtime.async_refresh_device_info(hass)

    async def handle_reboot_device(call: ServiceCall) -> dict[str, Any]:
        _LOGGER.debug("DJConnect developer action reboot_device started")
        return await runtime.async_device_post(hass, "/api/device/reboot")

    async def handle_forget_device(call: ServiceCall) -> dict[str, Any]:
        _LOGGER.debug("DJConnect developer action forget_device started")
        return await runtime.async_device_post(hass, "/api/device/forget")

    service_handlers = {
        "test_parse": (handle_test_parse, "optional"),
        "test_tts": (handle_test_tts, "optional"),
        "test_command": (handle_test_command, "optional"),
        "start_spotify_oauth": (handle_start_spotify_oauth, "only"),
        "device_command": (handle_device_command, "optional"),
        "refresh_device_info": (handle_refresh_device_info, "optional"),
        "reboot_device": (handle_reboot_device, "optional"),
        "forget_device": (handle_forget_device, "optional"),
    }
    for service_name, (handler, response_mode) in service_handlers.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            supports_response=response_mode,
        )
        _LOGGER.debug(
            "DJConnect registered developer action %s with response mode %s",
            service_name,
            response_mode,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    runtime = _restore_runtime(hass, entry)
    _setup_device_coordinator(hass, runtime)
    stt_info = detect_stt_support(hass, runtime.config)
    _LOGGER.info(
        "DJConnect STT route: ha_version=%s pipeline_id=%s pipeline_name=%s "
        "language=%s stt_engine=%s stt_available=%s audio_format=%s configured=%s",
        stt_info.get("ha_version"),
        stt_info.get("pipeline_id"),
        stt_info.get("pipeline_name"),
        stt_info.get("language"),
        stt_info.get("stt_engine"),
        bool(stt_info.get("stt_engine")),
        stt_info.get("audio_format"),
        stt_info.get("configured"),
    )
    await async_create_fixable_issues(hass, entry)
    await _try_initial_device_provisioning(hass, runtime)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_developer_services(hass, entry, runtime)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("DJConnect v%s loaded", VERSION)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        runtime = hass.data[DOMAIN].get("runtime")
        if runtime and runtime.entry.entry_id == entry.entry_id:
            hass.data[DOMAIN].pop("runtime", None)
    return unloaded


async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
