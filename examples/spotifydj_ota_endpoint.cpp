// Minimal SpotifyDJ device-side OTA endpoint sketch fragment.
// Integrate this into the existing WebServer/AsyncWebServer stack.
// Endpoint: POST /api/device/ota

#include <HTTPClient.h>
#include <HTTPUpdate.h>
#include <ArduinoJson.h>

String deviceToken;       // loaded from NVS after pairing
String deviceId;          // spotifydj-XXXXXXXXXXXX
String firmwareVersion;   // injected from firmware build metadata

static const char* OTA_TARGET_DEVICE = "lilygo-t-embed-s3";

bool authorizeSpotifyDJRequest(const String& authHeader, const String& headerDeviceId) {
  String expected = "Bearer " + deviceToken;
  return deviceToken.length() > 0 && authHeader == expected && headerDeviceId == deviceId;
}

// Pseudocode handler body. Adapt to WebServer or AsyncWebServer.
void handleOtaRequest(const String& jsonBody) {
  JsonDocument doc;
  if (deserializeJson(doc, jsonBody)) {
    // HTTP 400 {"success":false,"error":"invalid_json"}
    return;
  }

  String version = doc["version"].as<String>();
  String url = doc["url"].as<String>();
  String sha256 = doc["sha256"].as<String>();
  String device = doc["device"].as<String>();
  String asset = doc["asset"].as<String>();

  if (device != OTA_TARGET_DEVICE) {
    // HTTP 400 {"success":false,"error":"wrong_device_target","message":"Wrong device target"}
    return;
  }

  if (url.isEmpty() || sha256.isEmpty() || asset.isEmpty()) {
    // HTTP 400 {"success":false,"error":"missing_ota_fields"}
    return;
  }

  // Recommended: require USB power or enough battery before starting OTA.
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
