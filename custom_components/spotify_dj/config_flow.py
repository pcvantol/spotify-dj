from __future__ import annotations

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_SOURCE,
    CONF_OPENAI_API_KEY,
    CONF_OPENAI_CHAT_MODEL,
    CONF_OPENAI_STT_MODEL,
    CONF_OPENAI_TTS_MODEL,
    CONF_OPENAI_TTS_VOICE,
    CONF_DJ_STYLE,
    CONF_LIKED_PROXY,
    CONF_MAX_AUDIO_BYTES,
    DEFAULT_CHAT_MODEL,
    DEFAULT_STT_MODEL,
    DEFAULT_TTS_MODEL,
    DEFAULT_TTS_VOICE,
    DEFAULT_DJ_STYLE,
    DEFAULT_MAX_AUDIO_BYTES,
    CONF_FIRMWARE_REPO,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_DEVICE,
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_MIN_BATTERY_FOR_OTA,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_MIN_BATTERY_FOR_OTA,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_REFRESH_TOKEN,
    CONF_SPOTIFY_MARKET,
    CONF_SPOTIFY_SCOPES,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_SPOTIFY_SCOPES,
)

class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            await self.async_set_unique_id("spotifydj_main")
            self._abort_if_unique_id_configured()
            return self.async_create_entry(title="SpotifyDJ", data=user_input)
        return self.async_show_form(step_id="user", data_schema=_schema(), errors=errors)

    @staticmethod
    def async_get_options_flow(config_entry):
        return SpotifyDJOptionsFlow(config_entry)

class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        merged = dict(self.config_entry.data)
        merged.update(dict(self.config_entry.options))
        return self.async_show_form(step_id="init", data_schema=_schema(merged))

def _schema(defaults: dict | None = None):
    defaults = defaults or {}
    return vol.Schema({
        vol.Required(CONF_OPENAI_API_KEY, default=defaults.get(CONF_OPENAI_API_KEY, "")): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Required(CONF_SPOTIFY_PLAYER, default=defaults.get(CONF_SPOTIFY_PLAYER, "media_player.spotify")): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
        vol.Optional(CONF_SPOTIFY_SOURCE, default=defaults.get(CONF_SPOTIFY_SOURCE, "")): str,
        vol.Optional(CONF_LIKED_PROXY, default=defaults.get(CONF_LIKED_PROXY, "")): str,
        vol.Optional(CONF_SPOTIFY_CLIENT_ID, default=defaults.get(CONF_SPOTIFY_CLIENT_ID, "")): str,
        vol.Optional(CONF_SPOTIFY_REFRESH_TOKEN, default=defaults.get(CONF_SPOTIFY_REFRESH_TOKEN, "")): selector.TextSelector(selector.TextSelectorConfig(type=selector.TextSelectorType.PASSWORD)),
        vol.Optional(CONF_SPOTIFY_MARKET, default=defaults.get(CONF_SPOTIFY_MARKET, DEFAULT_SPOTIFY_MARKET)): str,
        vol.Optional(CONF_SPOTIFY_SCOPES, default=defaults.get(CONF_SPOTIFY_SCOPES, DEFAULT_SPOTIFY_SCOPES)): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Optional(CONF_OPENAI_CHAT_MODEL, default=defaults.get(CONF_OPENAI_CHAT_MODEL, DEFAULT_CHAT_MODEL)): str,
        vol.Optional(CONF_OPENAI_STT_MODEL, default=defaults.get(CONF_OPENAI_STT_MODEL, DEFAULT_STT_MODEL)): str,
        vol.Optional(CONF_OPENAI_TTS_MODEL, default=defaults.get(CONF_OPENAI_TTS_MODEL, DEFAULT_TTS_MODEL)): str,
        vol.Optional(CONF_OPENAI_TTS_VOICE, default=defaults.get(CONF_OPENAI_TTS_VOICE, DEFAULT_TTS_VOICE)): str,
        vol.Optional(CONF_DJ_STYLE, default=defaults.get(CONF_DJ_STYLE, DEFAULT_DJ_STYLE)): selector.TextSelector(selector.TextSelectorConfig(multiline=True)),
        vol.Optional(CONF_MAX_AUDIO_BYTES, default=defaults.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES)): int,
        vol.Optional(CONF_FIRMWARE_REPO, default=defaults.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO)): str,
        vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=defaults.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)): str,
        vol.Optional(CONF_FIRMWARE_DEVICE, default=defaults.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)): str,
        vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=defaults.get(CONF_ALLOW_OTA_ON_BATTERY, False)): bool,
        vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=defaults.get(CONF_MIN_BATTERY_FOR_OTA, DEFAULT_MIN_BATTERY_FOR_OTA)): int,
    })
