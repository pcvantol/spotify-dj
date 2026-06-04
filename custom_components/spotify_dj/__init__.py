from __future__ import annotations

import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientTimeout
import json
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    DOMAIN, VERSION, API_VOICE, API_PAIR, API_STATUS, API_EVENT, API_SPOTIFY_CALLBACK, PLATFORMS,
    CONF_SPOTIFY_CLIENT_ID, CONF_SPOTIFY_REFRESH_TOKEN, CONF_SPOTIFY_MARKET, CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET, DEFAULT_SPOTIFY_SCOPES,
)
from .http import SpotifyDJPairView, SpotifyDJVoiceView, SpotifyDJStatusView, SpotifyDJEventView, SpotifyDJSpotifyCallbackView
from .processor import process_text_command
from .tts import create_openai_tts_wav
from .spotify_oauth import build_authorize_url, build_redirect_uri, create_code_verifier

_LOGGER = logging.getLogger(__name__)

@dataclass
class SpotifyDJRuntime:
    entry: ConfigEntry
    last_text: str | None = None
    last_intent: dict[str, Any] | None = None
    last_dj_text: str | None = None
    last_error: str | None = None
    last_playback: dict[str, Any] | None = None
    device_status: dict[str, Any] = field(default_factory=dict)
    device_token: str | None = None
    pairing_code: str | None = None
    pairing_device_id: str | None = None
    ota_in_progress: bool = False
    ota_last_error: str | None = None
    listeners: list = field(default_factory=list)

    @property
    def config(self) -> dict[str, Any]:
        data = dict(self.entry.data)
        data.update(dict(self.entry.options))
        return data

    def update(self, **kwargs: Any) -> None:
        for key, value in kwargs.items():
            setattr(self, key, value)
        for listener in list(self.listeners):
            listener()

    def ensure_device_token(self) -> str:
        if not self.device_token:
            self.device_token = secrets.token_urlsafe(32)
        return self.device_token

    def authorize_device_request(self, headers: Any, body_device_id: str | None = None) -> bool:
        auth = headers.get("Authorization", "")
        token = auth.removeprefix("Bearer ").strip()
        if not self.device_token or token != self.device_token:
            return False
        header_device = headers.get("X-SpotifyDJ-Device-ID")
        known_device = self.device_status.get("device_id") or self.pairing_device_id
        if known_device and header_device and header_device != known_device:
            return False
        if known_device and body_device_id and body_device_id != known_device:
            return False
        return True

    async def start_ota(self, hass: HomeAssistant, release: Any) -> None:
        local_url = self.device_status.get("local_url") or self.device_status.get("ota_url")
        if not local_url:
            device_id = self.device_status.get("device_id") or self.pairing_device_id
            if device_id:
                local_url = f"http://{device_id}.local"
        if not local_url:
            raise RuntimeError("SpotifyDJ device local_url is unknown; send a /status update first")
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
            headers = {"Content-Type": "application/json"}
            if self.device_token:
                headers["Authorization"] = f"Bearer {self.device_token}"
            if self.device_status.get("device_id"):
                headers["X-SpotifyDJ-Device-ID"] = self.device_status["device_id"]
            async with session.post(url, json=payload, headers=headers, timeout=ClientTimeout(total=30)) as resp:
                text = await resp.text()
                if resp.status < 200 or resp.status >= 300:
                    raise RuntimeError(f"ESP OTA request failed HTTP {resp.status}: {text}")
                _LOGGER.info("SpotifyDJ OTA accepted by device: %s", text)
        except Exception as exc:  # noqa: BLE001
            self.ota_in_progress = False
            self.ota_last_error = str(exc)
            self.update()
            raise


    async def provision_spotify_credentials(self, hass: HomeAssistant) -> dict[str, Any]:
        conf = self.config
        if not conf.get(CONF_SPOTIFY_CLIENT_ID) or not conf.get(CONF_SPOTIFY_REFRESH_TOKEN):
            raise RuntimeError("Spotify OAuth is nog niet geconfigureerd in SpotifyDJ")
        local_url = self.device_status.get("local_url")
        if not local_url:
            device_id = self.device_status.get("device_id") or self.pairing_device_id
            if device_id:
                local_url = f"http://{device_id}.local"
        if not local_url:
            raise RuntimeError("SpotifyDJ device local_url is onbekend; pair eerst of stuur /status")
        url = local_url.rstrip("/") + "/api/device/provision_spotify"
        payload = {
            "spotify_client_id": conf.get(CONF_SPOTIFY_CLIENT_ID),
            "spotify_refresh_token": conf.get(CONF_SPOTIFY_REFRESH_TOKEN),
            "spotify_market": conf.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET),
            "spotify_scopes": str(conf.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES)).split(),
        }
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"
        if self.device_status.get("device_id"):
            headers["X-SpotifyDJ-Device-ID"] = self.device_status["device_id"]
        session = async_get_clientsession(hass)
        async with session.post(url, json=payload, headers=headers, timeout=ClientTimeout(total=30)) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(f"ESP Spotify provisioning failed HTTP {resp.status}: {text}")
            try:
                return json.loads(text) if text else {"success": True}
            except json.JSONDecodeError:
                return {"success": True, "response": text}
            
def register_http_views(hass: HomeAssistant) -> None:
    hass.data.setdefault(DOMAIN, {})
    if not hass.data[DOMAIN].get("http_registered"):
        for view in [
            SpotifyDJVoiceView(hass),
            SpotifyDJPairView(hass),
            SpotifyDJStatusView(hass),
            SpotifyDJEventView(hass),
            SpotifyDJSpotifyCallbackView(hass),
        ]:
            hass.http.register_view(view)
        hass.data[DOMAIN]["http_registered"] = True

        _LOGGER.info(
            "SpotifyDJ HTTP endpoints registered: %s, %s, %s, %s, %s",
            API_VOICE,
            API_PAIR,
            API_STATUS,
            API_EVENT,
            API_SPOTIFY_CALLBACK,
        )

async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    register_http_views(hass)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    runtime = SpotifyDJRuntime(entry=entry)
    # Restore device token from config entry data when present.
    if entry.data.get("device_token"):
        runtime.device_token = entry.data["device_token"]
    hass.data[DOMAIN][entry.entry_id] = runtime
    hass.data[DOMAIN]["runtime"] = runtime

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    async def handle_test_parse(call: ServiceCall) -> dict[str, Any] | None:
        text = call.data.get("text", "Ik wil het nieuwste album van Pearl Jam horen")
        result = await process_text_command(hass, runtime, text, play=False)
        _LOGGER.warning("SpotifyDJ test_parse: %s", result)
        return result

    async def handle_test_tts(call: ServiceCall) -> None:
        text = call.data.get("text", "Daar gaan we hoor. Pearl Jam, nieuw spul, oude klasse.")
        wav = await create_openai_tts_wav(hass, text, runtime.config)
        runtime.update(last_dj_text=text, last_error=None)
        _LOGGER.warning("SpotifyDJ test_tts generated %d wav bytes", len(wav))

    async def handle_test_command(call: ServiceCall) -> dict[str, Any] | None:
        text = call.data.get("text", "Ik wil het nieuwste album van Pearl Jam horen")
        result = await process_text_command(hass, runtime, text, play=True)
        _LOGGER.warning("SpotifyDJ test_command: %s", result)
        return result


    async def handle_start_spotify_oauth(call: ServiceCall) -> dict[str, Any]:
        client_id = (call.data.get("client_id") or runtime.config.get(CONF_SPOTIFY_CLIENT_ID) or "").strip()
        if not client_id:
            raise RuntimeError("Geef spotify_client_id mee of configureer die in SpotifyDJ options")
        base_url = (call.data.get("ha_base_url") or "http://homeassistant.local:8123").strip()
        scopes = (call.data.get("scopes") or runtime.config.get(CONF_SPOTIFY_SCOPES) or DEFAULT_SPOTIFY_SCOPES).strip()
        market = (call.data.get("market") or runtime.config.get(CONF_SPOTIFY_MARKET) or DEFAULT_SPOTIFY_MARKET).strip()
        verifier = create_code_verifier()
        state = secrets.token_urlsafe(24)
        redirect_uri = build_redirect_uri(base_url)
        hass.data.setdefault(DOMAIN, {}).setdefault("spotify_oauth_pending", {})[state] = {
            "entry_id": entry.entry_id,
            "client_id": client_id,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
            "scopes": scopes,
            "market": market,
        }
        auth_url = build_authorize_url(client_id, redirect_uri, scopes, state, verifier)
        return {"auth_url": auth_url, "redirect_uri": redirect_uri, "scopes": scopes}

    async def handle_provision_spotify(call: ServiceCall) -> dict[str, Any]:
        result = await runtime.provision_spotify_credentials(hass)
        runtime.device_status["spotify_configured"] = True
        runtime.update(last_error=None)
        return result

    hass.services.async_register(DOMAIN, "test_parse", handle_test_parse, supports_response="optional")
    hass.services.async_register(DOMAIN, "test_tts", handle_test_tts)
    hass.services.async_register(DOMAIN, "test_command", handle_test_command, supports_response="optional")
    hass.services.async_register(DOMAIN, "start_spotify_oauth", handle_start_spotify_oauth, supports_response="only")
    hass.services.async_register(DOMAIN, "provision_spotify_credentials", handle_provision_spotify, supports_response="optional")

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("SpotifyDJ v%s loaded", VERSION)
    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        hass.data[DOMAIN].pop(entry.entry_id, None)
        if hass.data[DOMAIN].get("runtime") and hass.data[DOMAIN]["runtime"].entry.entry_id == entry.entry_id:
            hass.data[DOMAIN].pop("runtime", None)
    return unloaded

async def _async_update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
