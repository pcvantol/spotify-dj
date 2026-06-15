# DJConnect Product Roadmap Ideas

This document collects product ideas, production-readiness must-haves and
possible premium features. It is intentionally product-focused; implementation
tasks should still be tracked in `TODO.md` or `ISSUES.md`.

Current proposition:

> DJConnect. Muziekbediening met karakter.

## Production Release Must-Haves

- Reliable PTT voice flow from every supported client: ESP32, iOS, macOS and Raspberry Pi where voice is supported.
- Stable Spotify OAuth refresh-token rotation without user-visible repair loops during normal playback.
- Clear first-run setup path: HACS install, Spotify Premium check, Assist STT/TTS setup, Spotify OAuth and client pairing.
- Robust mDNS pairing and manual Client API URL fallback for networks where Bonjour is filtered or stale.
- Major/minor protocol guardrails with clear `426 version_mismatch` errors and no token wipe.
- Stable entity model per client type:
  - ESP32: hardware settings, OTA, reboot, battery/WiFi/screen/LED state.
  - iOS/macOS/Raspberry Pi: client/runtime and backend/playback entities only.
- Queue/up-next support with artwork, max 100 returned items and no artificial duplicate padding.
- Last STT text, Spotify search result, DJ announcement and last track visible as entities/attributes for debugging.
- DJ announcement prompt is configurable, multiline, and never leaks into Spotify search or device lookup prompts.
- Local fallback DJ announcement is clean, short and never exposes raw Spotify/HTTP/JSON errors to the user.
- Dutch and English translations complete for config flow, options flow, entities, repairs and common errors.
- HACS presentation polished: icon, description, website link, README rendering and restart/repair text.
- Diagnostics redact all tokens, passwords, secrets and temporary audio URLs.
- End-to-end tests for pairing, voice, Spotify search, queue, refresh-token rotation, mDNS discovery and non-ESP entity filtering.
- Release hygiene: docs, changelog, handoff, sync prompts, technical design decisions and tests reviewed before every release.

## Killer Feature Candidates

- Natural music requests that understand artist, track, album, playlist, mood and intent:
  - “Ik heb zin in Nirvana.”
  - “Speel Black van Pearl Jam.”
  - “Zet mijn relax playlist op.”
  - “Doe iets rustigs voor vanavond.”
- Generative DJ announcements based on the resolved Spotify artist/track metadata and the user’s custom DJ prompt.
- Smart queue view across all clients with album art, current context, quick play, refresh and skip controls.
- Wake word flow with “Okay Nabu” on supported hardware, using the same PTT/STT/TTS backend.
- Multi-client handoff: start a request on ESP, view queue on iOS/macOS, control playback from Raspberry Pi.
- Household-friendly remote mode with a simple physical button and screen instead of opening the Spotify app.
- “Personal DJ memory”: remember preferred genres, disliked artists, common playlists and announcement style.
- Context-aware requests:
  - “Speel iets voor koken.”
  - “Meer zoals dit.”
  - “Maak het wat rustiger.”
  - “Ga verder met mijn avond playlist.”
- Party mode with shared queue voting, guest requests and host moderation.
- Voice debug mode that lets users replay the received WAV/STT result inside Home Assistant.
- Setup health check screen: Spotify Premium, OAuth, STT, TTS, playback device, mDNS and client reachability in one place.

## New Feature Ideas

### Voice And Intent

- Expand local fallback parsing for Dutch and English artist, track, album and playlist commands.
- Add confidence/debug attributes for parsed intent: detected media type, query, artist, title, playlist and Spotify result.
- Support correction commands:
  - “Nee, de live versie.”
  - “Niet deze, de originele.”
  - “Andere playlist.”
- Support follow-up commands using current context:
  - “Nog zo een.”
  - “Meer van deze artiest.”
  - “Speel het album hiervan.”
- Support “do not play yet” preview mode for developer/testing actions.
- Add STT language auto-detection only if HA exposes a reliable provider path.

### Spotify Playback

- Search result disambiguation when Spotify returns weak matches.
- Artist radio fallback when a direct artist start is unavailable.
- Playlist name search across user playlists first, then Spotify public playlists.
- Default playlist shortcuts, such as “favorieten”, “standaard playlist” and “mijn DJConnect playlist”.
- Better active device selection and repair hints when Spotify has no active playback device.
- Optional market override per request or per household profile.

### Client Experience

- Client capability reporting for every platform, so HA only creates relevant controls.
- Per-client display profile: compact, kiosk, hardware remote or debug.
- Local demo mode metadata that clearly stays client-local and does not create HA devices.
- Client-side “copy diagnostics” with redaction and direct issue template links.
- Client API URL health check and “can Home Assistant reach me?” indicator.

### Home Assistant Integration

- Device health dashboard entity/diagnostic view.
- Repair issues for missing STT provider, missing TTS provider, missing Spotify Premium/device and invalid Client API URL.
- Built-in test wizard: STT test, TTS test, Spotify play test, DJ announcement test and pairing callback test.
- Separate debug switches for voice audio, parser, Spotify search and device delivery.
- Optional persistent debug history with last N requests, redacted by default.
- More granular sensors for backend health, client health and Spotify auth state.

### Firmware / Hardware

- Wake word indicator and cancel flow polish.
- LED ring modes for listening, thinking, speaking, playback and errors.
- Offline-friendly setup screen with QR/deeplink to HA integration instructions.
- On-device “pairing reset” explanation that clearly shows code and Client API URL where relevant.
- Better battery/charging/OTA safety telemetry for ESP32 devices.

### Website / Onboarding

- A “How to start” wizard with exact HACS repository URL, Spotify Premium requirement and HA Assist setup.
- Compatibility matrix for ESP32, iOS, macOS and Raspberry Pi.
- Troubleshooting pages for Spotify OAuth, STT failed, TTS failed, mDNS discovery and Client API URL.
- Product screenshots/videos showing PTT, queue, DJ announcement and Home Assistant entities.

## Premium Feature Ideas

Premium ideas should be optional and must not remove the core local/Home
Assistant integration value.

- Advanced DJ persona packs with multiple announcement styles and custom prompt presets.
- Household profiles with per-user music preferences, language and announcement tone.
- Party mode:
  - guest request page;
  - voting;
  - host approval;
  - no-explicit filter hooks where backend supports it.
- Smart music memory:
  - favorite artists by room/time;
  - request history;
  - automatic “more like this” suggestions.
- Advanced queue tools:
  - save current queue as playlist;
  - reorder from app clients;
  - pin next track;
  - block artists temporarily.
- Cloud-assisted diagnostics bundle:
  - redacted logs;
  - setup health report;
  - guided troubleshooting checklist.
- Multi-room scene presets:
  - “cooking”;
  - “dinner”;
  - “party”;
  - “focus”;
  - “sleep”.
- Premium hardware themes: LED/screen themes, animated idle screens and seasonal packs.
- Extended client apps:
  - iOS widgets;
  - macOS menu bar mini remote;
  - Apple Watch request/cancel controls.
- Family-safe controls:
  - allowed playlists;
  - blocked artists;
  - time windows;
  - guest/kid mode.

## Paid Feature Boundaries

- Core pairing, local control, Spotify OAuth through HA, basic PTT, basic DJ announcement and essential entities should remain free.
- Premium should focus on personalization, convenience, advanced UI, history and multi-user experiences.
- No Spotify credentials should ever move out of Home Assistant for premium features.
- Any cloud-backed premium feature must be explicit, optional and clearly documented.

## Parking Lot

- Support future backends beyond Spotify through the existing generic playback command proxy.
- Local non-cloud LLM/DJ announcement generation if HA exposes a reliable local model path.
- Hardware bundle SKU planning.
- White-label hardware provisioning process.
- Signed firmware manifests.
- Optional Home Assistant dashboard cards for queue, current playback and DJ debug state.
