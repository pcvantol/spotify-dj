// Minimal SpotifyDJ device-side Spotify provisioning endpoint example.
// Add this to the existing WebServer/AsyncWebServer stack.
// Endpoint: POST /api/device/provision_spotify

#include <ArduinoJson.h>
#include <Preferences.h>

extern String deviceToken;
extern String deviceId;

Preferences spotifyPrefs;

bool authorizeSpotifyDJRequest(const String& authHeader, const String& headerDeviceId) {
  String expected = "Bearer " + deviceToken;
  return deviceToken.length() > 0 && authHeader == expected && headerDeviceId == deviceId;
}

// Pseudocode handler body. Adapt to WebServer or AsyncWebServer.
void handleProvisionSpotify(const String& jsonBody) {
  JsonDocument doc;
  if (deserializeJson(doc, jsonBody)) {
    // HTTP 400 {"success":false,"error":"invalid_json"}
    return;
  }

  String clientId = doc["spotify_client_id"].as<String>();
  String refreshToken = doc["spotify_refresh_token"].as<String>();
  String market = doc["spotify_market"] | "NL";

  if (clientId.isEmpty() || refreshToken.isEmpty()) {
    // HTTP 400 {"success":false,"error":"missing_spotify_credentials"}
    return;
  }

  spotifyPrefs.begin("spotifydj", false);
  spotifyPrefs.putString("sp_client_id", clientId);
  spotifyPrefs.putString("sp_refresh", refreshToken);
  spotifyPrefs.putString("sp_market", market);
  spotifyPrefs.end();

  // Optional: immediately refresh access token once to validate credentials.
  // HTTP 200 {"success":true,"spotify_configured":true}
}
