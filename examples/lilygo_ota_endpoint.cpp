// Minimal ESP32-side OTA endpoint sketch fragment for SpotifyDJ v0.6.0.
// Integrate this into your existing WebServer/AsyncWebServer stack.

#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <ArduinoJson.h>

String deviceToken;   // loaded from NVS after pairing
String deviceId;      // spotifydj-<chipid>
String firmwareVersion = "1.1.1";

bool authorizeSpotifyDJRequest(const String& authHeader, const String& headerDeviceId) {
  String expected = "Bearer " + deviceToken;
  return deviceToken.length() > 0 && authHeader == expected && headerDeviceId == deviceId;
}

// Pseudocode handler body:
void handleOtaRequest(const String& jsonBody) {
  JsonDocument doc;
  if (deserializeJson(doc, jsonBody)) {
    // return HTTP 400
    return;
  }

  String version = doc["version"].as<String>();
  String url = doc["url"].as<String>();
  String sha256 = doc["sha256"].as<String>();
  String device = doc["device"].as<String>();

  if (device != "lilygo-t-embed-s3") {
    // return HTTP 400 wrong device
    return;
  }

  // Recommended: require USB power or battery > 40%.
  // Recommended: verify SHA-256 before Update.end(true), or use esp_https_ota with validation.

  WiFiClientSecure client;
  client.setInsecure(); // Replace with CA certificate pinning for production.

  t_httpUpdate_return ret = httpUpdate.update(client, url);
  switch (ret) {
    case HTTP_UPDATE_OK:
      firmwareVersion = version;
      // Device reboots automatically in many httpUpdate flows.
      break;
    case HTTP_UPDATE_FAILED:
      // POST /api/spotify_dj/status with ota_state=failed and ota_error=httpUpdate.getLastErrorString()
      break;
    case HTTP_UPDATE_NO_UPDATES:
      break;
  }
}
