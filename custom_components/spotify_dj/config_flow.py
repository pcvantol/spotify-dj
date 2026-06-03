from __future__ import annotations

import secrets
import voluptuous as vol
from homeassistant import config_entries
from homeassistant.helpers import selector

from .const import (
    DOMAIN,
    CONF_DEVICE_ID,
    CONF_DEVICE_NAME,
    CONF_DEVICE_TOKEN,
    CONF_LOCAL_URL,
    CONF_SPOTIFY_CLIENT_ID,
    CONF_SPOTIFY_MARKET,
    CONF_ASSIST_PIPELINE_ID,
    CONF_TTS_ENGINE,
    CONF_TTS_LANGUAGE,
    CONF_TTS_VOICE,
    CONF_DJ_PROFILE,
    CONF_SPOTIFY_PLAYER,
    CONF_SPOTIFY_SOURCE,
    CONF_LIKED_PROXY,
    CONF_MAX_AUDIO_BYTES,
    CONF_FIRMWARE_REPO,
    CONF_FIRMWARE_ASSET_PREFIX,
    CONF_FIRMWARE_DEVICE,
    CONF_FIRMWARE_CHANNEL,
    CONF_ALLOW_OTA_ON_BATTERY,
    CONF_MIN_BATTERY_FOR_OTA,
    DEFAULT_DEVICE_NAME,
    DEFAULT_SPOTIFY_MARKET,
    DEFAULT_DJ_PROFILE,
    DEFAULT_TTS_LANGUAGE,
    DEFAULT_MAX_AUDIO_BYTES,
    DEFAULT_FIRMWARE_REPO,
    DEFAULT_FIRMWARE_ASSET_PREFIX,
    DEFAULT_FIRMWARE_DEVICE,
    DEFAULT_FIRMWARE_CHANNEL,
    DEFAULT_MIN_BATTERY_FOR_OTA,
)


class SpotifyDJConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    VERSION = 1

    def __init__(self) -> None:
        self._pairing: dict = {}
        self._spotify: dict = {}
        self._voice: dict = {}

    async def async_step_user(self, user_input=None):
        errors = {}
        if user_input is not None:
            pair_code = str(user_input.get("pair_code", "")).strip()
            if len(pair_code) != 6 or not pair_code.isdigit():
                errors["pair_code"] = "invalid_pair_code"
            else:
                # In production this is validated against the pending pair registry.
                device_id = f"spotifydj-{pair_code}"
                await self.async_set_unique_id(device_id)
                self._abort_if_unique_id_configured()
                self._pairing = {
                    CONF_DEVICE_ID: device_id,
                    CONF_DEVICE_NAME: user_input.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME),
                    CONF_DEVICE_TOKEN: secrets.token_urlsafe(32),
                    CONF_LOCAL_URL: user_input.get(CONF_LOCAL_URL, ""),
                }
                return await self.async_step_spotify()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({
                vol.Required("pair_code"): str,
                vol.Optional(CONF_DEVICE_NAME, default=DEFAULT_DEVICE_NAME): str,
                vol.Optional(CONF_LOCAL_URL, default=""): str,
            }),
            errors=errors,
        )

    async def async_step_spotify(self, user_input=None):
        if user_input is not None:
            self._spotify = dict(user_input)
            # OAuth/PKCE browser step placeholder: use async_external_step in a hardened implementation.
            return await self.async_step_voice()

        return self.async_show_form(
            step_id="spotify",
            description_placeholders={
                "note": "Gebruik je eigen Spotify Developer App Client ID. PKCE heeft geen client secret nodig."
            },
            data_schema=vol.Schema({
                vol.Required(CONF_SPOTIFY_CLIENT_ID): str,
                vol.Optional(CONF_SPOTIFY_MARKET, default=DEFAULT_SPOTIFY_MARKET): str,
            }),
        )

    async def async_step_voice(self, user_input=None):
        if user_input is not None:
            self._voice = dict(user_input)
            data = {**self._pairing, **self._spotify, **self._voice}
            return self.async_create_entry(title=data.get(CONF_DEVICE_NAME, DEFAULT_DEVICE_NAME), data=data)

        return self.async_show_form(
            step_id="voice",
            data_schema=vol.Schema({
                vol.Optional(CONF_ASSIST_PIPELINE_ID, default=""): str,
                vol.Optional(CONF_TTS_ENGINE, default=""): str,
                vol.Optional(CONF_TTS_LANGUAGE, default=DEFAULT_TTS_LANGUAGE): str,
                vol.Optional(CONF_TTS_VOICE, default=""): str,
                vol.Optional(CONF_DJ_PROFILE, default=DEFAULT_DJ_PROFILE): selector.SelectSelector(selector.SelectSelectorConfig(
                    options=["classic_dutch_radio", "calm_evening", "festival", "minimal"],
                    mode=selector.SelectSelectorMode.DROPDOWN,
                )),
            }),
        )

    @staticmethod
    def async_get_options_flow(config_entry):
        return SpotifyDJOptionsFlow(config_entry)


class SpotifyDJOptionsFlow(config_entries.OptionsFlow):
    def __init__(self, config_entry):
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)

        defaults = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(step_id="init", data_schema=vol.Schema({
            vol.Optional(CONF_SPOTIFY_PLAYER, default=defaults.get(CONF_SPOTIFY_PLAYER, "media_player.spotify")): selector.EntitySelector(selector.EntitySelectorConfig(domain="media_player")),
            vol.Optional(CONF_SPOTIFY_SOURCE, default=defaults.get(CONF_SPOTIFY_SOURCE, "")): str,
            vol.Optional(CONF_LIKED_PROXY, default=defaults.get(CONF_LIKED_PROXY, "")): str,
            vol.Optional(CONF_ASSIST_PIPELINE_ID, default=defaults.get(CONF_ASSIST_PIPELINE_ID, "")): str,
            vol.Optional(CONF_TTS_ENGINE, default=defaults.get(CONF_TTS_ENGINE, "")): str,
            vol.Optional(CONF_TTS_LANGUAGE, default=defaults.get(CONF_TTS_LANGUAGE, DEFAULT_TTS_LANGUAGE)): str,
            vol.Optional(CONF_TTS_VOICE, default=defaults.get(CONF_TTS_VOICE, "")): str,
            vol.Optional(CONF_DJ_PROFILE, default=defaults.get(CONF_DJ_PROFILE, DEFAULT_DJ_PROFILE)): selector.SelectSelector(selector.SelectSelectorConfig(options=["classic_dutch_radio", "calm_evening", "festival", "minimal"])),
            vol.Optional(CONF_MAX_AUDIO_BYTES, default=defaults.get(CONF_MAX_AUDIO_BYTES, DEFAULT_MAX_AUDIO_BYTES)): int,
            vol.Optional(CONF_FIRMWARE_REPO, default=defaults.get(CONF_FIRMWARE_REPO, DEFAULT_FIRMWARE_REPO)): str,
            vol.Optional(CONF_FIRMWARE_ASSET_PREFIX, default=defaults.get(CONF_FIRMWARE_ASSET_PREFIX, DEFAULT_FIRMWARE_ASSET_PREFIX)): str,
            vol.Optional(CONF_FIRMWARE_DEVICE, default=defaults.get(CONF_FIRMWARE_DEVICE, DEFAULT_FIRMWARE_DEVICE)): str,
            vol.Optional(CONF_FIRMWARE_CHANNEL, default=defaults.get(CONF_FIRMWARE_CHANNEL, DEFAULT_FIRMWARE_CHANNEL)): selector.SelectSelector(selector.SelectSelectorConfig(options=["stable", "beta"])),
            vol.Optional(CONF_ALLOW_OTA_ON_BATTERY, default=defaults.get(CONF_ALLOW_OTA_ON_BATTERY, False)): bool,
            vol.Optional(CONF_MIN_BATTERY_FOR_OTA, default=defaults.get(CONF_MIN_BATTERY_FOR_OTA, DEFAULT_MIN_BATTERY_FOR_OTA)): int,
        }))
