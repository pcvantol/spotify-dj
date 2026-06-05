// Minimal SpotifyDJ device-side raw WAV voice request example.
// ESP firmware records microphone audio as WAV and uploads it to the SpotifyDJ
// Home Assistant integration. The integration runs HA Assist/STT internally.

#include <HTTPClient.h>

static const char* HA_VOICE_URL = "http://homeassistant.local:8123/api/spotify_dj/voice";
static const char* DEVICE_TOKEN = "DEVICE_TOKEN_FROM_PAIRING";
static const char* DEVICE_ID = "spotifydj-90B70990A994";

bool uploadWavToSpotifyDJ(const uint8_t* wav, size_t wavLen) {
  WiFiClient client;
  HTTPClient http;

  http.begin(client, HA_VOICE_URL);
  http.addHeader("Authorization", String("Bearer ") + DEVICE_TOKEN);
  http.addHeader("X-SpotifyDJ-Device-ID", DEVICE_ID);
  http.addHeader("Content-Type", "audio/wav");

  int code = http.POST((uint8_t*)wav, wavLen);
  if (code < 200 || code >= 300) {
    Serial.printf("SpotifyDJ WAV upload failed: HTTP %d\n", code);
    Serial.println(http.getString());
    http.end();
    return false;
  }

  // Response JSON contains text/dj_text and optionally audio_url/audio_type.
  // The device should display text and play audio_url when present.
  String response = http.getString();
  Serial.println(response);
  http.end();
  return true;
}
