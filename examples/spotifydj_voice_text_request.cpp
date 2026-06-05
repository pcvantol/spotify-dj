// Minimal SpotifyDJ device-side voice text request example.
// ESP firmware should run Home Assistant Assist websocket STT first, then send
// the recognized text to the SpotifyDJ Home Assistant integration.

#include <HTTPClient.h>
#include <ArduinoJson.h>

static const char* HA_VOICE_URL = "http://homeassistant.local:8123/api/spotify_dj/voice";
static const char* HA_TOKEN = "YOUR_HOME_ASSISTANT_LONG_LIVED_ACCESS_TOKEN";
static const char* DEVICE_TOKEN = "DEVICE_TOKEN_FROM_PAIRING";
static const char* DEVICE_ID = "spotifydj-90B70990A994";

bool sendRecognizedTextToSpotifyDJ(const String& recognizedText) {
  WiFiClient client;
  HTTPClient http;

  http.begin(client, HA_VOICE_URL);
  http.addHeader("Authorization", String("Bearer ") + HA_TOKEN);
  http.addHeader("X-SpotifyDJ-Device-Token", DEVICE_TOKEN);
  http.addHeader("X-SpotifyDJ-Device-ID", DEVICE_ID);
  http.addHeader("X-SpotifyDJ-Text", recognizedText);
  http.addHeader("Content-Type", "application/json");

  JsonDocument doc;
  doc["text"] = recognizedText;
  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  if (code < 200 || code >= 300) {
    Serial.printf("SpotifyDJ voice text request failed: HTTP %d\n", code);
    http.end();
    return false;
  }

  String response = http.getString();
  Serial.println(response);
  http.end();
  return true;
}
