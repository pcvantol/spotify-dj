# Changelog

## 3.0.7

- Add a Dutch/English product website with browser-language detection, manual language toggle and localized hero device artwork.
- Add a My Home Assistant HACS repository deeplink for `pcvantol/djconnect` to the website quick-start flow.
- Remove the Pong FAQ item while keeping the broader bonus-games website copy.
- Improve Spotify setup and OAuth success copy so user-facing screens avoid PKCE, redirect URI and refresh-token jargon.
- Show the DJConnect app icon instead of the wide banner on the standalone Spotify OAuth callback page.
- Add explicit titles to Spotify OAuth external steps where Home Assistant supports them.
- Make DJ style choices affect the HA Assist prompt with concrete tone guidance for Classic Dutch radio, Calm evening, Festival and Minimal.
- Reduce noisy firmware update entity refreshes by only writing update state when firmware/OTA-relevant runtime values change.
- Fetch ESP `/api/device/pairing-info` before pairing, verify the reported setup code and learn the real `djconnect-lilygo-XXXXXXXXXXXX` device ID before posting `/api/device/pair`.
- Keep tests updated for website-related helpers, OAuth copy, DJ style prompt behavior, firmware update throttling and pairing-info based pairing.
