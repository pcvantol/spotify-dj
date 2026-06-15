# DJConnect Technical Design Decisions

This document records code-level design decisions, implementation patterns,
coding conventions and third-party dependencies for the DJConnect Home Assistant
integration.

Sources used for this document:

- Local source tree under `custom_components/djconnect/`.
- Home Assistant integration metadata in `custom_components/djconnect/manifest.json`.
- HACS metadata in `hacs.json`.
- Existing architecture and release notes in `README.md`, `AGENTS.md`,
  `HANDOFF.md`, `SYNC_PROMPTS.md` and `THIRD_PARTY_NOTICES.md`.
- Unit tests under `tests/`.

When a runtime dependency is provided by Home Assistant rather than pinned by
this repository, the version is documented as the minimum component/runtime
contract that this repo declares.

## Scope

This repository contains the free MIT-licensed Home Assistant custom
integration for DJConnect. It does not contain proprietary DJConnect firmware
source. Firmware binaries and firmware release assets are covered separately by
`FIRMWARE-LICENSE.md`.

The integration domain is `djconnect`. The current implementation targets
DJConnect protocol line `3.1.x`.

## Python Design Decisions

### Home Assistant Runtime As The Composition Root

Pattern:

- Home Assistant owns setup, config entries, platform loading, HTTP view
  registration, services, diagnostics and repairs.
- DJConnect stores one `DJConnectRuntime` object per config entry in
  `hass.data[DOMAIN][entry.entry_id]`.
- Entity platforms read and observe that runtime instead of duplicating state.

Primary source files:

- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/sensor.py`
- `custom_components/djconnect/button.py`
- `custom_components/djconnect/number.py`
- `custom_components/djconnect/select.py`
- `custom_components/djconnect/switch.py`
- `custom_components/djconnect/update.py`
- `custom_components/djconnect/media_player.py`

Why:

- Matches Home Assistant's custom integration lifecycle.
- Keeps one in-memory authority for device state, Spotify state and voice
  debug data.
- Lets non-polling entities update immediately through runtime listeners.

### Runtime State Object With Listener Fan-Out

Pattern:

- `DJConnectRuntime` is a dataclass with transient fields such as
  `last_text`, `last_dj_text`, `last_playback`, `device_status`,
  `device_token`, `pairing_device_id`, OTA state and latest Spotify token
  metadata.
- Entities append callbacks to `runtime.listeners`.
- `runtime.update(...)` writes fields, mirrors last-known values into
  `device_status`, then notifies listeners.

Primary source files:

- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/sensor.py`

Why:

- Avoids Home Assistant polling for frequent local status changes.
- Keeps `last_command`, `last_track` and DJ announcement debug values stable
  across sparse payloads.
- Makes tests lightweight because runtime can be represented by simple stubs.

### Merge-Only Device Status Cache

Pattern:

- Device status updates merge known fields into `runtime.device_status`.
- Sparse command, voice or playback payloads must not replace the whole status
  snapshot with empty/default values.
- `ha_pairing_status` does not silently fall back to `pending` when a payload
  omits it.

Primary source files:

- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/http.py`
- `custom_components/djconnect/sensor.py`

Why:

- ESP/app clients frequently send partial command or voice payloads.
- Home Assistant sensors should preserve last-known useful values while a
  device or backend is temporarily unavailable.

### Explicit Client-Type Branching

Pattern:

- `client_type` is the canonical runtime discriminator.
- Current values are `esp32`, `ios`, `macos` and `raspberry_pi`.
- ESP32 gets hardware-specific entities such as battery, WiFi RSSI, screen,
  LED, OTA and reboot controls.
- iOS, macOS and Raspberry Pi clients keep backend/playback/client entities
  only.

Primary source files:

- `custom_components/djconnect/const.py`
- `custom_components/djconnect/config_flow.py`
- `custom_components/djconnect/sensor.py`
- `custom_components/djconnect/button.py`
- `custom_components/djconnect/number.py`
- `custom_components/djconnect/update.py`

Why:

- Prevents app-like clients from showing ESP-only controls.
- Keeps one integration contract while supporting multiple client runtimes.

### Local HTTP Views For Protocol Boundaries

Pattern:

- Home Assistant registers explicit HTTP views for DJConnect protocol routes:
  pairing, status, command, voice, event, TTS and Spotify callback.
- Each route owns its input parsing, auth checks and response shape.

Primary source files:

- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/http.py`

Why:

- Keeps device/app protocol contracts isolated from Home Assistant entity code.
- Lets tests exercise routes without a full Home Assistant runtime.

### Bearer-Token Pairing And Auth

Pattern:

- Pairing creates and stores a per-device bearer token.
- Device/app calls authenticate with `Authorization: Bearer <device_token>`.
- Device ID and `client_type` are validated against known model/client ID
  shapes.
- Spotify credentials are never returned in pair/status responses.

Primary source files:

- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/http.py`
- `custom_components/djconnect/config_flow.py`

Why:

- Keeps Home Assistant as the trusted backend.
- Prevents DJConnect clients from storing Spotify OAuth or Home Assistant
  long-lived credentials.

### Discovery Strategy Object

Pattern:

- `DiscoveredClient` is a small dataclass that represents one mDNS-discovered
  DJConnect client.
- Discovery first parses TXT/service metadata, then probes
  `/api/device/pairing-info`.
- Pairing-info is authoritative over mDNS TXT data.
- Dedupe is by stable `device_id`.

Primary source files:

- `custom_components/djconnect/discovery.py`
- `custom_components/djconnect/config_flow.py`

Why:

- mDNS TXT data can be stale or incomplete.
- The local Client API URL can change for app-like clients.
- Pairing-info gives the best current device ID, client type, name, version,
  pairing code and local URL.

### Adapter Functions Around Home Assistant APIs

Pattern:

- Helper modules hide Home Assistant API variations and optional runtime
  capabilities.
- Examples include HA URL resolution, Assist/STT probing, TTS generation,
  firmware release fetching and BLE provisioning.

Primary source files:

- `custom_components/djconnect/ha_urls.py`
- `custom_components/djconnect/assist_stt.py`
- `custom_components/djconnect/tts.py`
- `custom_components/djconnect/github.py`
- `custom_components/djconnect/ble.py`

Why:

- Home Assistant helper APIs vary across releases.
- Small adapter modules keep fallback behavior testable and localized.

### Spotify Backend As An Internal Gateway

Pattern:

- `spotify_backend.py` is the only module that directly executes Spotify Web
  API playback commands.
- It maps generic DJConnect commands to Spotify API calls.
- Access tokens are cached until shortly before expiry.
- Spotify API `401` clears the access token and retries once.
- Refresh-token rotation is persisted immediately.
- If Spotify rejects one refresh token, the backend retries newer stored
  runtime/config-entry/config token sources before creating a Repair issue.

Primary source files:

- `custom_components/djconnect/spotify_backend.py`
- `custom_components/djconnect/spotify_oauth.py`
- `custom_components/djconnect/repairs.py`

Why:

- Devices/apps stay backend-agnostic and do not receive playback credentials.
- Spotify token expiry and token rotation should be invisible to clients.
- A user-facing Repair is only appropriate when Spotify rejects every known
  stored refresh token.

### Assist And TTS As Home Assistant-Native Gateways

Pattern:

- Raw WAV PTT uploads are processed by HA STT/Assist helpers.
- `pipeline.py` asks HA Assist for DJConnect intent data, but `spotify.py`
  keeps a deterministic local fallback parser for common Dutch/English PTT
  phrases. Generic music requests stay artist-first; explicit media words map
  to Spotify Search types (`track`, `album`, `playlist`) or the configured
  default playlist.
- DJ announcement text is generated through Home Assistant Assist where
  possible, then converted to a temporary WAV/MP3 URL through HA TTS.
- Local fallback text is deliberately neutral and not a hidden prompt-style
  generator.

Primary source files:

- `custom_components/djconnect/assist_stt.py`
- `custom_components/djconnect/pipeline.py`
- `custom_components/djconnect/processor.py`
- `custom_components/djconnect/spotify.py`
- `custom_components/djconnect/dj_response.py`
- `custom_components/djconnect/tts.py`
- `custom_components/djconnect/wav_util.py`

Why:

- Keeps active routes inside Home Assistant's configured Assist/TTS setup.
- Avoids direct external AI/STT/TTS dependencies in this integration.
- Prevents broad or ambiguous STT text from becoming arbitrary track/album
  searches while still supporting explicit user phrasing for tracks, albums and
  playlists.
- Keeps DJ response audio on the DJConnect device, not the Spotify playback
  device.

### Repair Flow For User-Actionable Failures

Pattern:

- Missing Spotify credentials, missing scopes and revoked refresh tokens create
  Home Assistant repair issues.
- The Spotify repair path opens OAuth and only closes after a new token is
  stored.

Primary source files:

- `custom_components/djconnect/repairs.py`
- `custom_components/djconnect/http.py`
- `custom_components/djconnect/spotify_backend.py`

Why:

- Access-token refresh is automatic, but OAuth reauthorization cannot be done
  silently when Spotify revokes the refresh token.
- Repairs keep unavoidable user action inside native Home Assistant UX.

### Defensive Diagnostics And Logging

Pattern:

- Diagnostics redact keys containing `token`, `password` or `secret`.
- Logs use metadata instead of raw secrets or full payload dumps.
- Spotify token logs include expiry timing, source names and rotation status,
  never token values.

Primary source files:

- `custom_components/djconnect/diagnostics.py`
- `custom_components/djconnect/__init__.py`
- `custom_components/djconnect/http.py`
- `custom_components/djconnect/spotify_backend.py`

Why:

- Pairing, BLE WiFi and Spotify OAuth all touch sensitive values.
- Debugging should not create accidental credential disclosure.

### Lightweight Unit Tests With Home Assistant Stubs

Pattern:

- Tests use Python `unittest`.
- Home Assistant modules/classes are stubbed where possible.
- Tests target helper logic, route parsing, entity behavior and protocol
  contracts without a full Home Assistant installation.

Primary source files:

- `tests/`

Why:

- Keeps the test suite fast enough for every release.
- Makes protocol regressions visible even outside a Home Assistant dev
  container.

## Python Coding Style Conventions

Observed conventions:

- `from __future__ import annotations` at the top of Python modules.
- Async Home Assistant naming: `async_setup_entry`, `async_unload_entry`,
  `async_*` helpers and non-blocking `aiohttp` client sessions.
- Constants are uppercase and centralized in `const.py`.
- Integration-wide logger names use `logging.getLogger(__name__)`.
- Dataclasses are used for structured internal records:
  `DJConnectRuntime`, `DiscoveredClient`, `FirmwareRelease`, `FirmwareAssets`,
  `TtsAudio` and similar small value objects.
- Home Assistant entity classes set `_attr_has_entity_name = True` and stable
  `_attr_translation_key` / `_attr_unique_id` values where applicable.
- Entity unique IDs are derived through `entry_unique_id(...)` so multiple
  DJConnect entries do not collide.
- User-facing strings live in Home Assistant translation files:
  `strings.json`, `translations/en.json`, `translations/nl.json` and
  `services.yaml`.
- Broad `except Exception` blocks are used only around optional Home Assistant
  APIs, third-party runtime helpers or best-effort cleanup, usually with debug
  logging.
- Secrets are never intentionally logged.

Sources:

- Home Assistant integration entry points and entity APIs in
  `custom_components/djconnect/*.py`.
- Translation files under `custom_components/djconnect/translations/` and
  `custom_components/djconnect/strings.json`.
- Service descriptions in `custom_components/djconnect/services.yaml`.

## JSON And YAML Design Decisions

### Home Assistant Manifest

Pattern:

- `custom_components/djconnect/manifest.json` declares the integration domain,
  version, Home Assistant dependencies, HACS-visible documentation URLs,
  Bluetooth discovery UUID and Python requirements.

Why:

- This is the canonical Home Assistant custom integration metadata contract.

### Translations

Pattern:

- English and Dutch translations are maintained in Home Assistant translation
  JSON files.
- Config-flow, options-flow, repair and entity labels should not rely on raw
  key names in the UI.

Why:

- DJConnect is used in both Dutch and English Home Assistant environments.
- Translation coverage is tested.

### Service Schema

Pattern:

- `services.yaml` documents developer/test services such as Spotify OAuth,
  command tests and TTS tests.

Why:

- Home Assistant's Developer Actions UI reads this metadata.

### Firmware Manifest Example

Pattern:

- `examples/firmware_manifest.json` documents the public firmware manifest
  shape expected by the OTA update entity.

Why:

- The HA integration consumes public firmware releases without bundling
  proprietary firmware source.

## Bash Design Decisions

### Release Script

Pattern:

- `release.sh` validates semantic versions, updates version metadata, stages,
  commits, tags, pushes and creates a GitHub release.
- `--dry-run` is available.

Why:

- Keeps HACS release mechanics repeatable.
- Reduces version drift between `manifest.json`, `const.py`, README examples
  and release tags.

### Cleanup Script

Pattern:

- `cleanup_old_releases.sh` removes old semver releases/tags while keeping the
  configured number of latest releases.

Why:

- The project intentionally keeps only the current GitHub release unless a
  release-retention exception is requested.

## Markdown Documentation Conventions

Pattern:

- `README.md` is user-facing installation and architecture documentation.
- `CHANGELOG.md` keeps a separate block per release; release notes are no
  longer consolidated into one current block.
- `AGENTS.md` is the canonical in-repo working agreement for future coding
  agents.
- `HANDOFF.md`, `TODO.md` and `ISSUES.md` track operational state and known
  validation points.
- `SYNC_PROMPTS.md` is the only cross-repo prompt/contract file.
- This file, `TECHNICAL_DESIGN_DECISIONS.md`, records implementation design
  patterns, conventions and dependency inventory.

Why:

- Separates user documentation, release notes, implementation contracts and
  agent handoff state.
- Makes release hygiene explicit.

## Third-Party Dependency Inventory

The table below lists direct runtime dependencies, Home Assistant component
dependencies and external APIs used by this repository. Transitive dependencies
of Home Assistant or its components are not individually pinned by this repo
unless imported or declared here.

| Dependency | Used From | Version In This Repo | License / Terms | Source URL |
| --- | --- | --- | --- | --- |
| Python | Runtime language, tests, scripts | Not pinned by repo; Home Assistant runtime provides Python | Python Software Foundation License | https://github.com/python/cpython |
| Python standard library | `asyncio`, `json`, `logging`, `secrets`, `dataclasses`, `hashlib`, `base64`, `urllib.parse`, `wave`, `unittest`, etc. | Same as Python runtime | Python Software Foundation License | https://github.com/python/cpython |
| Home Assistant Core | Custom integration APIs, config entries, HTTP views, entities, repairs, diagnostics, Assist/TTS/STT hooks | HACS minimum `2025.1.0` from `hacs.json`; actual runtime supplied by user | Apache License 2.0 | https://github.com/home-assistant/core |
| Home Assistant `http` component | HTTP view registration and local API routes | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `zeroconf` component | `_djconnect._tcp` mDNS discovery | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `bluetooth` component | BLE discovery for setup-mode devices | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `bluetooth_adapters` component | Bluetooth adapter/runtime support | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `conversation` component | Assist text command processing | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `assist_pipeline` component | Assist/STT pipeline selection and fallback | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| Home Assistant `tts` component | DJ announcement audio generation | Declared in `manifest.json` dependencies | Apache License 2.0 as part of Home Assistant Core | https://github.com/home-assistant/core |
| aiohttp | HTTP client timeouts/session usage and `aiohttp.web` helpers | `aiohttp>=3.9.0` in `manifest.json` | Apache License 2.0 | https://github.com/aio-libs/aiohttp |
| awesomeversion | Firmware semantic version comparison | `awesomeversion>=23.8.0` in `manifest.json` | MIT License | https://github.com/ludeeus/awesomeversion |
| voluptuous | Config-flow and repairs schema definitions | Provided by Home Assistant runtime; imported directly in `config_flow.py` and `repairs.py` | BSD-style license | https://github.com/alecthomas/voluptuous |
| zeroconf | Async mDNS service browser and service-state changes | Provided through Home Assistant zeroconf dependency; imported dynamically in `discovery.py` | LGPL-2.1-or-later | https://github.com/python-zeroconf/python-zeroconf |
| bleak | BLE GATT client for WiFi provisioning | Provided through Home Assistant Bluetooth stack; imported dynamically in `ble.py` | MIT License | https://github.com/hbldh/bleak |
| bleak-retry-connector | Robust BLE connection helper | Provided through Home Assistant Bluetooth stack; imported dynamically in `ble.py` | MIT License | https://github.com/Bluetooth-Devices/bleak-retry-connector |
| HACS | Distribution surface for this custom integration | HACS metadata in `hacs.json`; HACS version not pinned | MIT License | https://github.com/hacs/integration |
| Spotify Web API | User-authorized backend playback, OAuth token endpoint and search/playback endpoints | External API; no library is vendored | Spotify Developer Terms | https://developer.spotify.com/documentation/web-api |
| GitHub REST API | Firmware release and release-asset discovery | External API; no library is vendored | GitHub Terms of Service | https://docs.github.com/rest |
| Home Assistant Cloud / Nabu Casa URL | Preferred external HTTPS callback URL for Spotify OAuth | Optional user runtime service; no library is vendored | Nabu Casa service terms | https://www.nabucasa.com |

## Bundled Assets And Local Project Files

| Asset / File Type | Location | Ownership / License |
| --- | --- | --- |
| DJConnect brand images | `assets/`, `brands/`, `custom_components/djconnect/brand/` | DJConnect project assets; see repository license context and firmware/device copyright notices |
| Home Assistant integration source | `custom_components/djconnect/` | MIT License via `LICENSE` |
| Firmware binary/license references | `FIRMWARE-LICENSE.md`, examples and docs | Proprietary firmware binary terms; firmware source not included |
| Tests | `tests/` | MIT License via `LICENSE` |

## Dependency Update Rules

- Update this document whenever `manifest.json`, `hacs.json`, Home Assistant
  component dependencies, imported third-party modules, external APIs, or
  architecture patterns change.
- Do not invent exact runtime versions for dependencies managed by Home
  Assistant. Record the repository-declared lower bound or component contract.
- Keep license information aligned with upstream source URLs and
  `THIRD_PARTY_NOTICES.md`.
- Re-run `python3 -m unittest discover -s tests` after code or contract changes.
