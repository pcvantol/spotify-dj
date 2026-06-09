# Third-Party Notices

DJConnect includes a Home Assistant custom integration and is designed to work
with DJConnect devices. This file summarizes third-party projects, APIs and
trademarks that may be referenced by the integration.

## Home Assistant

The DJConnect Home Assistant integration uses Home Assistant custom integration
APIs, including config entries, diagnostics, HTTP views, services, entities,
Assist/conversation integration points, TTS helpers, Bluetooth discovery and
zeroconf/mDNS discovery.

Home Assistant and its components are open-source software. Their licenses and
copyrights remain with their respective authors and contributors.

## Python Packages And Home Assistant Dependencies

The integration manifest may request or use these runtime packages/components:

- `aiohttp` for HTTP client/server helpers used through Home Assistant.
- `awesomeversion` for firmware version comparisons.
- `voluptuous` for Home Assistant config-flow schemas.
- `zeroconf` / Home Assistant zeroconf support for local device discovery.
- Home Assistant `bluetooth` and `bluetooth_adapters` integrations for BLE WiFi
  provisioning.
- Home Assistant `conversation` and `assist_pipeline` integrations for HA-native
  Assist command processing.
- Home Assistant `tts` integration for generating temporary DJ response audio.

If `async_timeout` is present in the Home Assistant runtime environment, its
license remains with its respective authors. DJConnect does not claim ownership
over third-party Python packages or Home Assistant components.

## Spotify API And Trademark Notice

DJConnect may reference Spotify APIs and Spotify playback concepts to provision
and control user-authorized Spotify playback.

Spotify is a trademark of Spotify AB. DJConnect is not affiliated with,
endorsed by, or sponsored by Spotify AB. References to Spotify APIs are API
usage only and do not imply endorsement, sponsorship, partnership or official
support by Spotify AB.

## DJConnect Firmware And Devices

Copyright (c) 2026 Peter van Tol. All rights reserved.

DJConnect firmware is proprietary closed-source software. Firmware binaries and
device firmware release assets are covered separately by `FIRMWARE-LICENSE.md`.
The Home Assistant integration may be distributed separately for use with
DJConnect devices under the terms of `LICENSE`.

