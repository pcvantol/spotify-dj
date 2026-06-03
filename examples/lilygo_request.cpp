#include <HTTPClient.h>

static const char* HA_URL = "http://homeassistant.local:8123/api/spotify_dj/voice";
static const char* HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN";

bool sendWavToSpotifyDJ(const uint8_t* wav, size_t wavLen) {
  WiFiClient client;
  HTTPClient http;

  http.begin(client, HA_URL);
  http.addHeader("Authorization", String("Bearer ") + HA_TOKEN);
  http.addHeader("Content-Type", "audio/wav");

  // Optional dev shortcut:
  // http.addHeader("X-SpotifyDJ-Text", "ik wil het nieuwste album van Pearl Jam horen");

  int code = http.POST((uint8_t*)wav, wavLen);
  if (code != 200) {
    Serial.printf("SpotifyDJ HTTP error: %d
", code);
    http.end();
    return false;
  }

  WiFiClient* stream = http.getStreamPtr();

  // Response is WAV. Skip RIFF header for a simple 16-bit PCM I2S playback path,
  // or parse it properly if you support variable sample rates/formats.
  uint8_t header[44];
  if (stream->readBytes(header, 44) != 44) {
    http.end();
    return false;
  }

  uint8_t buf[1024];
  while (http.connected()) {
    int available = stream->available();
    if (available <= 0) { delay(1); continue; }
    int n = stream->readBytes(buf, min(available, (int)sizeof(buf)));
    if (n <= 0) break;
    // TODO: i2s_channel_write(txChan, buf, n, &written, portMAX_DELAY);
  }

  http.end();
  return true;
}
