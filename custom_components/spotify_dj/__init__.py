from __future__ import annotations

import json
import logging
import secrets
from dataclasses import dataclass, field
from typing import Any

from aiohttp import ClientTimeout
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.typing import ConfigType

from .const import (
    API_EVENT,
    API_PAIR,
    API_SPOTIFY_CALLBACK,
    API_STATUS,
    API_VOICE,
    CONF_ASSIST_PIPELINE_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_HA_EXTERNAL_URL,
    CONF_LOCAL_URL,
    CONF_MQTT_HOST,
    CONF_MQTT_PASSWORD,
    CONF_MQTT_PORT,
    CONF_MQTT_USERNAME,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    DEFAULT_MQTT_PORT,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DOMAIN,
    PLATFORMS,
    VERSION,
)
from .http import (
    SpotifyDJEventView,
    SpotifyDJPairView,
    SpotifyDJSpotifyCallbackView,
    SpotifyDJStatusView,
    SpotifyDJVoiceView,
)
from .processor import process_text_command
from .spotify_oauth import build_authorize_url, build_redirect_uri, create_code_verifier

_LOGGER = logging.getLogger(__name__)

DEFAULT_TEST_COMMAND = "Ik wil het nieuwste album van Pearl Jam horen"
DEFAULT_TEST_TTS_TEXT = (
    "Daar gaan we. SpotifyDJ is gekoppeld, de stem werkt, "
    "en ik sta klaar voor je volgende plaat."
)


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

    def device_local_url(self) -> str | None:
        """Return the best known device base URL."""
        local_url = (
            self.device_status.get("local_url")
            or self.device_status.get("ota_url")
            or self.config.get(CONF_LOCAL_URL)
        )
        if local_url:
            return str(local_url)
        device_id = self.device_status.get("device_id") or self.pairing_device_id
        device_id = device_id or self.config.get(CONF_DEVICE_ID)
        return f"http://{device_id}.local" if device_id else None

    def device_headers(self, *, include_device_id: bool = True) -> dict[str, str]:
        """Build headers for authenticated ESP requests."""
        headers = {"Content-Type": "application/json"}
        if self.device_token:
            headers["Authorization"] = f"Bearer {self.device_token}"
        if include_device_id and self.device_status.get("device_id"):
            headers["X-SpotifyDJ-Device-ID"] = self.device_status["device_id"]
        return headers

    def authorize_device_request(
        self,
        headers: Any,
        body_device_id: str | None = None,
    ) -> bool:
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

    def mqtt_payload(self) -> dict[str, Any]:
        """Return MQTT settings for ESP provisioning when a broker is configured."""
        conf = self.config
        host = str(conf.get(CONF_MQTT_HOST) or "").strip()
        if not host:
            return {}
        return {
            "host": host,
            "port": int(conf.get(CONF_MQTT_PORT, DEFAULT_MQTT_PORT)),
            "username": str(conf.get(CONF_MQTT_USERNAME) or ""),
            "password": str(conf.get(CONF_MQTT_PASSWORD) or ""),
        }

    async def start_ota(self, hass: HomeAssistant, release: Any) -> None:
        local_url = self.device_local_url()
        if not local_url:
            raise RuntimeError(
                "SpotifyDJ device local_url is unknown; send a /status update first"
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
                _LOGGER.info("SpotifyDJ OTA accepted by device: %s", text)
        except Exception as exc:  # noqa: BLE001
            self.ota_in_progress = False
            self.ota_last_error = str(exc)
            self.update()
            raise

    async def pair_device(self, hass: HomeAssistant) -> dict[str, Any]:
        conf = self.config
        local_url = self.device_local_url()
        if not local_url:
            raise RuntimeError("SpotifyDJ device local_url is unknown")
        token = self.ensure_device_token()
        url = local_url.rstrip("/") + "/api/device/pair"
        payload = {
            "pair_code": conf.get(CONF_PAIR_CODE),
            "device_id": conf.get(CONF_DEVICE_ID),
            "device_name": conf.get(CONF_DEVICE_NAME, "SpotifyDJ"),
            "device_token": token,
            "ha_url": conf.get(CONF_HA_EXTERNAL_URL),
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "mqtt": self.mqtt_payload(),
        }
        session = async_get_clientsession(hass)
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

    async def provision_spotify_credentials(self, hass: HomeAssistant) -> dict[str, Any]:
        conf = self.config
        if not conf.get(CONF_SPOTIFY_CLIENT_ID) or not conf.get(
            CONF_SPOTIFY_REFRESH_TOKEN
        ):
            raise RuntimeError("Spotify OAuth is nog niet geconfigureerd in SpotifyDJ")
        local_url = self.device_local_url()
        if not local_url:
            raise RuntimeError(
                "SpotifyDJ device local_url is onbekend; pair eerst of stuur /status"
            )
        url = local_url.rstrip("/") + "/api/device/provision_spotify"
        payload = {
            "spotify_client_id": conf.get(CONF_SPOTIFY_CLIENT_ID),
            "spotify_refresh_token": conf.get(CONF_SPOTIFY_REFRESH_TOKEN),
            "spotify_market": conf.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET),
            "spotify_scopes": str(
                conf.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES)
            ).split(),
            "assist_pipeline_id": conf.get(CONF_ASSIST_PIPELINE_ID, ""),
            "ha_url": conf.get(CONF_HA_EXTERNAL_URL),
            "device_token": self.device_token,
            "mqtt": self.mqtt_payload(),
        }
        session = async_get_clientsession(hass)
        async with session.post(
            url,
            json=payload,
            headers=self.device_headers(),
            timeout=ClientTimeout(total=30),
        ) as resp:
            text = await resp.text()
            if resp.status < 200 or resp.status >= 300:
                raise RuntimeError(
                    f"ESP Spotify provisioning failed HTTP {resp.status}: {text}"
                )
            try:
                return json.loads(text) if text else {"success": True}
            except json.JSONDecodeError:
                return {"success": True, "response": text}


def _service_text(call: ServiceCall, default: str) -> str:
    """Return normalized service text while keeping developer actions forgiving."""
    return str(call.data.get("text") or default).strip()


def _tts_service_data(runtime: SpotifyDJRuntime, text: str) -> dict[str, str]:
    """Build HA TTS service data from the current SpotifyDJ options."""
    conf = runtime.config
    player = conf.get(CONF_SPOTIFY_PLAYER)
    if not player:
        raise RuntimeError(
            "Configureer eerst een Spotify/media_player in SpotifyDJ options"
        )
    return {
        "entity_id": conf.get(CONF_TTS_ENGINE, DEFAULT_TTS_ENGINE),
        "media_player_entity_id": player,
        "message": text,
        "language": conf.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE),
    }


async def async_speak_dj_test(
    hass: HomeAssistant,
    runtime: SpotifyDJRuntime,
    text: str,
) -> dict[str, Any]:
    """Send a DJ test response through HA TTS and return user-visible details."""
    service_data = _tts_service_data(runtime, text)
    _LOGGER.debug(
        "SpotifyDJ test_tts using TTS engine %s and media player %s",
        service_data["entity_id"],
        service_data["media_player_entity_id"],
    )
    await hass.services.async_call("tts", "speak", service_data, blocking=True)
    runtime.update(last_dj_text=text, last_error=None)
    return {
        "success": True,
        "text": text,
        "tts_engine": service_data["entity_id"],
        "media_player": service_data["media_player_entity_id"],
    }


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


def _restore_runtime(hass: HomeAssistant, entry: ConfigEntry) -> SpotifyDJRuntime:
    runtime = SpotifyDJRuntime(entry=entry)
    if entry.data.get("device_token"):
        runtime.device_token = entry.data["device_token"]
        _LOGGER.debug(
            "SpotifyDJ restored existing device token for entry %s",
            entry.entry_id,
        )
    hass.data[DOMAIN][entry.entry_id] = runtime
    hass.data[DOMAIN]["runtime"] = runtime
    _LOGGER.debug("SpotifyDJ runtime restored for entry %s", entry.entry_id)
    return runtime


async def _try_initial_device_provisioning(
    hass: HomeAssistant,
    runtime: SpotifyDJRuntime,
) -> None:
    """Provision opportunistically without blocking HA startup when ESP is offline."""
    try:
        await runtime.pair_device(hass)
        await runtime.provision_spotify_credentials(hass)
        runtime.device_status["spotify_configured"] = True
        runtime.update(last_error=None)
        _LOGGER.info("SpotifyDJ Spotify credentials provisioned to device")
    except Exception as exc:  # noqa: BLE001
        runtime.update(last_error=f"Spotify provisioning failed: {exc}")
        _LOGGER.warning("SpotifyDJ Spotify provisioning deferred/failed: %s", exc)


def _register_developer_services(
    hass: HomeAssistant,
    entry: ConfigEntry,
    runtime: SpotifyDJRuntime,
) -> None:
    """Register Home Assistant developer actions for parser, TTS and provisioning."""

    async def handle_test_parse(call: ServiceCall) -> dict[str, Any] | None:
        text = _service_text(call, DEFAULT_TEST_COMMAND)
        _LOGGER.debug("SpotifyDJ developer action test_parse: %s", text)
        result = await process_text_command(hass, runtime, text, play=False)
        _LOGGER.warning("SpotifyDJ test_parse: %s", result)
        return result

    async def handle_test_tts(call: ServiceCall) -> dict[str, Any]:
        text = _service_text(call, DEFAULT_TEST_TTS_TEXT)
        _LOGGER.debug("SpotifyDJ developer action test_tts: %s", text)
        result = await async_speak_dj_test(hass, runtime, text)
        _LOGGER.warning("SpotifyDJ test_tts sent text to HA TTS: %s", text)
        return result

    async def handle_test_command(call: ServiceCall) -> dict[str, Any] | None:
        text = _service_text(call, DEFAULT_TEST_COMMAND)
        play = bool(call.data.get("play", True))
        _LOGGER.debug(
            "SpotifyDJ developer action test_command play=%s: %s",
            play,
            text,
        )
        result = await process_text_command(hass, runtime, text, play=play)
        _LOGGER.warning("SpotifyDJ test_command: %s", result)
        return result

    async def handle_start_spotify_oauth(call: ServiceCall) -> dict[str, Any]:
        client_id = (
            call.data.get("client_id")
            or runtime.config.get(CONF_SPOTIFY_CLIENT_ID)
            or ""
        ).strip()
        if not client_id:
            raise RuntimeError(
                "Geef spotify_client_id mee of configureer die in SpotifyDJ options"
            )
        base_url = (
            call.data.get("ha_base_url")
            or runtime.config.get(CONF_HA_EXTERNAL_URL)
            or "http://homeassistant.local:8123"
        ).strip()
        scopes = (
            call.data.get("scopes")
            or runtime.config.get(CONF_SPOTIFY_SCOPES)
            or DEFAULT_SPOTIFY_SCOPES
        ).strip()
        market = (
            call.data.get("market")
            or runtime.config.get(CONF_SPOTIFY_MARKET)
            or DEFAULT_SPOTIFY_MARKET
        ).strip()
        verifier = create_code_verifier()
        state = secrets.token_urlsafe(24)
        redirect_uri = build_redirect_uri(base_url)
        _LOGGER.debug(
            "SpotifyDJ developer action start_spotify_oauth redirect_uri=%s market=%s",
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

    async def handle_provision_spotify(call: ServiceCall) -> dict[str, Any]:
        _LOGGER.debug("SpotifyDJ developer action provision_spotify_credentials started")
        result = await runtime.provision_spotify_credentials(hass)
        runtime.device_status["spotify_configured"] = True
        runtime.update(last_error=None)
        _LOGGER.debug("SpotifyDJ developer action provision_spotify_credentials done")
        return result

    service_handlers = {
        "test_parse": (handle_test_parse, "optional"),
        "test_tts": (handle_test_tts, "optional"),
        "test_command": (handle_test_command, "optional"),
        "start_spotify_oauth": (handle_start_spotify_oauth, "only"),
        "provision_spotify_credentials": (handle_provision_spotify, "optional"),
    }
    for service_name, (handler, response_mode) in service_handlers.items():
        hass.services.async_register(
            DOMAIN,
            service_name,
            handler,
            supports_response=response_mode,
        )
        _LOGGER.debug(
            "SpotifyDJ registered developer action %s with response mode %s",
            service_name,
            response_mode,
        )


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    runtime = _restore_runtime(hass, entry)
    await _try_initial_device_provisioning(hass, runtime)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    _register_developer_services(hass, entry, runtime)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _LOGGER.info("SpotifyDJ v%s loaded", VERSION)
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
