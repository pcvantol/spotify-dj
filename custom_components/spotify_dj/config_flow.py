"""Config flow for SpotifyDJ.

This version keeps the working v1.3 flow structure and adds Spotify PKCE OAuth
using a direct HTTPS Home Assistant callback, such as a Nabu Casa URL:
https://<id>.ui.nabu.casa/api/spotify_dj/spotify/callback
"""
from __future__ import annotations

import logging
import secrets
from typing import Any
from urllib.parse import parse_qs, urlparse

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.data_entry_flow import FlowResult

from .const import (
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_ASSIST_PIPELINE_ID,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_DJ_PROFILE,
    CONF_DJ_STYLE,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_CHANNEL,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_REPO,
    CONF_HA_EXTERNAL_URL,
    CONF_LIKED_PROXY,
    CONF_LOCAL_URL,
    CONF_MAX_AUDIO_BYTES,
    CONF_MIN_BATTERY_FOR_OTA,
    CONF_PAIR_CODE,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_SCOPES,
    CONF_SPOTIFY_SOURCE,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    DEFAULT_ASSIST_PIPELINE_ID,
    DEFAULT_DEVICE_NAME,
    DEFAULT_DJ_STYLE,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
    DEFAULT_TTS_ENGINE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_TTS_VOICE,
    DJ_STYLE_NAMES,
    DJ_STYLES,
    DOMAIN,
)
from .spotify_oauth import (
    build_authorize_url,
    build_redirect_uri,
    create_code_verifier,
    exchange_code_for_refresh_token,
)

_LOGGER = logging.getLogger(__name__)


def _clean(value: Any, default: Any = "") -> Any:
    """Normalize empty form values."""
    if value is None:
        return default
    if isinstance(value, str) and value.strip() == "":
        return default
    return value


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    return bool(value)


def _int(value: Any, default: int) -> int:
    try:
        return int(_clean(value, default))
    except (TypeError, ValueError):
        return default


def _extract_query_value(value: str, key: str) -> str:
    value = (value or "").strip()
    if not value:
        return ""
    if value.startswith("http://") or value.startswith("https://"):
        parsed = urlparse(value)
        qs = parse_qs(parsed.query)
        if qs.get(key):
            return qs[key][0]
    return ""


def _voice_defaults(data: dict[str, Any] | None = None) -> dict[str, Any]:
    """Return voice/options config with safe defaults."""
    source = data or {}
    dj_style = _clean(source.get(CONF_DJ_STYLE) or source.get(CONF_DJ_PROFILE), DEFAULT_DJ_STYLE)
    if dj_style not in DJ_STYLES:
        dj_style = DEFAULT_DJ_STYLE
    return {
        CONF_ASSIST_PIPELINE_ID: _clean(source.get(CONF_ASSIST_PIPELINE_ID), DEFAULT_ASSIST_PIPELINE_ID),
        CONF_TTS_ENGINE: _clean(source.get(CONF_TTS_ENGINE), DEFAULT_TTS_ENGINE),
        CONF_TTS_LANGUAGE: _clean(source.get(CONF_TTS_LANGUAGE), DEFAULT_TTS_LANGUAGE),
        CONF_TTS_VOICE: _clean(source.get(CONF_TTS_VOICE), DEFAULT_TTS_VOICE),
        CONF_DJ_STYLE: dj_style,
        CONF_DJ_PROFILE: dj_style,
        CONF_FIRMWARE_REPO: _clean(source.get(CONF_FIRMWARE_REPO), DEFAULT_FIRMWARE_REPO),
        CONF_FIRMWARE_ASSET_PREFIX: _clean(source.get(CONF_FIRMWARE_ASSET_PREFIX), DEFAULT_FIRMWARE_ASSET_PREFIX),
        CONF_FIRMWARE_DEVICE: _clean(source.get(CONF_FIRMWARE_DEVICE), DEFAULT_FIRMWARE_DEVICE),
        CONF_FIRMWARE_CHANNEL: _clean(source.get(CONF_FIRMWARE_CHANNEL), DEFAULT_FIRMWARE_CHANNEL),
        CONF_MAX_AUDIO_BYTES: _int(source.get(CONF_MAX_AUDIO_BYTES), DEFAULT_MAX_AUDIO_BYTES),
        CONF_ALLOW_OTA_ON_BATTERY: _bool(source.get(CONF_ALLOW_OTA_ON_BATTERY), False),
        CONF_MIN_BATTERY_FOR_OTA: _int(source.get(CONF_MIN_BATTERY_FOR_OTA), DEFAULT_MIN_BATTERY_FOR_OTA),
        CONF_SPOTIFY_PLAYER: _clean(source.get(CONF_SPOTIFY_PLAYER), ""),
        CONF_SPOTIFY_SOURCE: _clean(source.get(CONF_SPOTIFY_SOURCE), ""),
        CONF_LIKED_PROXY: _clean(source.get(CONF_LIKED_PROXY), ""),
    }


class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle the SpotifyDJ config flow."""

    VERSION = 1

    def __init__(self) -> None:
        self._pairing: dict[str, Any] = {}
        self._spotify: dict[str, Any] = {}
        self._oauth: dict[str, str] = {}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Pair the LilyGO device using the displayed pair code."""
        errors: dict[str, str] = {}

        if user_input is not None:
            pair_code = str(user_input.get(CONF_PAIR_CODE, "")).strip()
            if len(pair_code) != 6 or not pair_code.isdigit():
                errors[CONF_PAIR_CODE] = "invalid_pair_code"
            else:
                device_id = f"spotifydj-{pair_code}"
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                self._pairing = {
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: _clean(user_input.get(CONF_DEVICE_NAME), DEFAULT_DEVICE_NAME),
                    CONF_DEVICE_TOKEN: secrets.token_urlsafe(32),
                    CONF_LOCAL_URL: _clean(user_input.get(CONF_LOCAL_URL), ""),
                }
                return await self.async_step_spotify()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_PAIR_CODE): str,
                    vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
                    vol.Optional(CONF_LOCAL_URL, default=""): str,
                }
            ),
            errors=errors,
        )

    async def async_step_spotify(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect Spotify Client ID and HTTPS HA external URL."""
        errors: dict[str, str] = {}

        if user_input is not None:
            client_id = str(user_input.get(CONF_SPOTIFY_CLIENT_ID, "")).strip()
            external_url = str(user_input.get(CONF_HA_EXTERNAL_URL, "")).strip().rstrip("/")
            if not client_id:
                errors[CONF_SPOTIFY_CLIENT_ID] = "required"
            elif not external_url.startswith("https://"):
                errors[CONF_HA_EXTERNAL_URL] = "https_required"
            else:
                redirect_uri = build_redirect_uri(external_url)
                self._spotify = {
                    CONF_SPOTIFY_CLIENT_ID: client_id,
                    CONF_HA_EXTERNAL_URL: external_url,
                    CONF_SPOTIFY_MARKET: _clean(user_input.get(CONF_SPOTIFY_MARKET), DEFAULT_SPOTIFY_MARKET),
                    CONF_SPOTIFY_SCOPES: DEFAULT_SPOTIFY_SCOPES,
                }
                self._oauth = {
                    "state": secrets.token_urlsafe(24),
                    "code_verifier": create_code_verifier(),
                    "redirect_uri": redirect_uri,
                }
                authorize_url = build_authorize_url(
                    client_id,
                    redirect_uri,
                    DEFAULT_SPOTIFY_SCOPES,
                    self._oauth["state"],
                    self._oauth["code_verifier"],
                )
                pending = self.hass.data.setdefault(DOMAIN, {}).setdefault("config_flow_oauth_pending", {})
                pending[self._oauth["state"]] = {
                    "client_id": client_id,
                    "code_verifier": self._oauth["code_verifier"],
                    "redirect_uri": redirect_uri,
                    "market": self._spotify[CONF_SPOTIFY_MARKET],
                    "scopes": DEFAULT_SPOTIFY_SCOPES,
                }
                return await self.async_step_spotify_oauth({"authorize_url": authorize_url})

        return self.async_show_form(
            step_id="spotify",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_SPOTIFY_CLIENT_ID): str,
                    vol.Required(CONF_HA_EXTERNAL_URL): str,
                    vol.Optional(CONF_SPOTIFY_MARKET, default=DEFAULT_SPOTIFY_MARKET): str,
                }
            ),
            errors=errors,
            description_placeholders={
                "callback_path": "/api/spotify_dj/spotify/callback",
            },
        )

    async def async_step_spotify_oauth(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Finish Spotify OAuth.

        Open the authorize URL, approve Spotify, then the callback page will show a
        state value. Paste that state here. As a fallback, you can paste the full
        callback URL containing code/state.
        """
        errors: dict[str, str] = {}
        authorize_url = (user_input or {}).get("authorize_url") or self._oauth.get("authorize_url", "")
        if authorize_url:
            self._oauth["authorize_url"] = authorize_url

        if user_input is not None and "oauth_result" in user_input:
            raw = str(user_input.get("oauth_result", "")).strip()
            state = raw
            code = ""
            if raw.startswith("http://") or raw.startswith("https://"):
                state = _extract_query_value(raw, "state")
                code = _extract_query_value(raw, "code")

            try:
                if code and state:
                    await self._exchange_code_direct(code, state)
                elif state:
                    result = self.hass.data.get(DOMAIN, {}).get("config_flow_oauth_results", {}).pop(state, None)
                    if not result:
                        errors["oauth_result"] = "oauth_not_completed"
                    else:
                        self._spotify[CONF_SPOTIFY_REFRESH_TOKEN] = result[CONF_SPOTIFY_REFRESH_TOKEN]
                        self._spotify[CONF_SPOTIFY_MARKET] = result.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET)
                        self._spotify[CONF_SPOTIFY_SCOPES] = result.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES)
                else:
                    errors["oauth_result"] = "required"
            except Exception as exc:  # noqa: BLE001
                _LOGGER.exception("Spotify OAuth failed")
                errors["base"] = "oauth_failed"

            if not errors:
                return await self.async_step_voice()

        return self.async_show_form(
            step_id="spotify_oauth",
            data_schema=vol.Schema({vol.Required("oauth_result"): str}),
            errors=errors,
            description_placeholders={
                "authorize_url": self._oauth.get("authorize_url", authorize_url or ""),
                "redirect_uri": self._oauth.get("redirect_uri", ""),
            },
        )

    async def _exchange_code_direct(self, code: str, state: str) -> None:
        if state != self._oauth.get("state"):
            raise RuntimeError("Spotify OAuth state mismatch")
        token = await exchange_code_for_refresh_token(
            self.hass,
            client_id=self._spotify[CONF_SPOTIFY_CLIENT_ID],
            code=code,
            code_verifier=self._oauth["code_verifier"],
            redirect_uri=self._oauth["redirect_uri"],
        )
        self._spotify[CONF_SPOTIFY_REFRESH_TOKEN] = token["refresh_token"]

    async def async_step_voice(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        """Collect optional voice settings. Empty fields are allowed."""
        if user_input is not None:
            data: dict[str, Any] = {}
            data.update(self._pairing)
            data.update(self._spotify)
            data.update(_voice_defaults(user_input))
            return self.async_create_entry(
                title=data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                data=data,
            )

        return self.async_show_form(
            step_id="voice",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ASSIST_PIPELINE_ID, default=""): str,
                    vol.Optional(CONF_TTS_ENGINE, default=DEFAULT_TTS_ENGINE): str,
                    vol.Optional(CONF_TTS_LANGUAGE, default=DEFAULT_TTS_LANGUAGE): str,
                    vol.Optional(CONF_TTS_VOICE, default=""): str,
                    vol.Optional(CONF_DJ_STYLE, default=DEFAULT_DJ_STYLE): vol.In(DJ_STYLE_NAMES),
                    vol.Optional(CONF_SPOTIFY_PLAYER, default=""): str,
                    vol.Optional(CONF_SPOTIFY_SOURCE, default=""): str,
                    vol.Optional(CONF_LIKED_PROXY, default=""): str,
                    vol.Optional(CONF_FIRMWARE_REPO, default=DEFAULT_FIRMWARE_REPO): str,
                    vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=DEFAULT_FIRMWARE_ASSET_PREFIX): str,
                    vol.Optional(CONF_FIRMWARE_DEVICE, default=DEFAULT_FIRMWARE_DEVICE): str,
                    vol.Optional(CONF_FIRMWARE_CHANNEL, default=DEFAULT_FIRMWARE_CHANNEL): str,
                    vol.Optional(CONF_MAX_AUDIO_BYTES, default=DEFAULT_MAX_AUDIO_BYTES): int,
                    vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=False): bool,
                    vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=DEFAULT_MIN_BATTERY_FOR_OTA): int,
                }
            ),
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> "SpotifyDJOptionsFlow":
        """Create options flow."""
        return SpotifyDJOptionsFlow(config_entry)


class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    """Handle SpotifyDJ options."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> FlowResult:
        current = {**self.config_entry.data, **self.config_entry.options}
        if user_input is not None:
            return self.async_create_entry(title="", data=_voice_defaults(user_input))

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(CONF_ASSIST_PIPELINE_ID, default=current.get(CONF_ASSIST_PIPELINE_ID, "")): str,
                    vol.Optional(CONF_TTS_ENGINE, default=current.get(CONF_TTS_ENGINE, DEFAULT_TTS_ENGINE)): str,
                    vol.Optional(CONF_TTS_LANGUAGE, default=current.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE)): str,
                    vol.Optional(CONF_TTS_VOICE, default=current.get(CONF_TTS_VOICE, "")): str,
                    vol.Optional(CONF_DJ_STYLE, default=current.get(CONF_DJ_STYLE, current.get(CONF_DJ_PROFILE, DEFAULT_DJ_STYLE))): vol.In(DJ_STYLE_NAMES),
                    vol.Optional(CONF_SPOTIFY_PLAYER, default=current.get(CONF_SPOTIFY_PLAYER, "")): str,
                    vol.Optional(CONF_SPOTIFY_SOURCE, default=current.get(CONF_SPOTIFY_SOURCE, "")): str,
                    vol.Optional(CONF_LIKED_PROXY, default=current.get(CONF_LIKED_PROXY, "")): str,
                    vol.Optional(CONF_FIRMWARE_REPO, default=current.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO)): str,
                    vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=current.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)): str,
                    vol.Optional(CONF_FIRMWARE_DEVICE, default=current.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)): str,
                    vol.Optional(CONF_FIRMWARE_CHANNEL, default=current.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL)): str,
                    vol.Optional(CONF_MAX_AUDIO_BYTES, default=current.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES)): int,
                    vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=current.get(CONF_ALLOW_OTA_ON_BATTERY, False)): bool,
                    vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=current.get(CONF_MIN_BATTERY_FOR_OTA, DEFAULT_MIN_BATTERY_FOR_OTA)): int,
                }
            ),
        )
