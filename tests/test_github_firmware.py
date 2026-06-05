from __future__ import annotations

import importlib
import asyncio
import json
from pathlib import Path
import sys
import types
import unittest


ROOT = Path(__file__).resolve().parents[1]


def install_github_stubs() -> None:
    aiohttp = sys.modules.setdefault("aiohttp", types.ModuleType("aiohttp"))

    class ClientTimeout:
        def __init__(self, *args, **kwargs):
            self.args = args
            self.kwargs = kwargs

    aiohttp.ClientTimeout = ClientTimeout

    sys.modules.setdefault("homeassistant", types.ModuleType("homeassistant"))
    core = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    helpers = sys.modules.setdefault(
        "homeassistant.helpers",
        types.ModuleType("homeassistant.helpers"),
    )
    aiohttp_client = sys.modules.setdefault(
        "homeassistant.helpers.aiohttp_client",
        types.ModuleType("homeassistant.helpers.aiohttp_client"),
    )
    awesomeversion = sys.modules.setdefault(
        "awesomeversion",
        types.ModuleType("awesomeversion"),
    )

    class AwesomeVersion:
        def __init__(self, value):
            self.parts = tuple(int(part) for part in str(value).split("."))

        def __gt__(self, other):
            return self.parts > other.parts

    core.HomeAssistant = object
    helpers.aiohttp_client = aiohttp_client
    aiohttp_client.async_get_clientsession = lambda hass: None
    awesomeversion.AwesomeVersion = AwesomeVersion

    package = types.ModuleType("custom_components.spotify_dj")
    package.__path__ = [str(ROOT / "custom_components" / "spotify_dj")]
    sys.modules["custom_components.spotify_dj"] = package


class GithubFirmwareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_github_stubs()
        cls.github = importlib.import_module("custom_components.spotify_dj.github")

    def test_select_release_assets_matches_spotifydj_device_binary(self) -> None:
        assets = self.github._select_release_assets(
            [
                {
                    "name": "spotifydj-device-v2.7.0.bin",
                    "browser_download_url": "https://example/firmware.bin",
                },
                {
                    "name": "firmware_manifest.json",
                    "browser_download_url": "https://example/manifest.json",
                },
            ],
            "spotifydj-device",
        )

        self.assertEqual(assets.firmware["name"], "spotifydj-device-v2.7.0.bin")
        self.assertEqual(assets.manifest["name"], "firmware_manifest.json")

    def test_firmware_release_uses_manifest_device_and_metadata(self) -> None:
        class Response:
            def __init__(self, payload):
                self.payload = payload
                self.status = 200
                self.ok = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def json(self):
                return self.payload

            async def text(self):
                return json.dumps(self.payload)

            def raise_for_status(self):
                return None

        class Session:
            def get(self, url, **kwargs):
                if url.endswith("/releases/latest"):
                    return Response(
                        {
                            "tag_name": "v2.7.0",
                            "name": "SpotifyDJ v2.7.0",
                            "assets": [
                                {
                                    "name": "spotifydj-device-v2.7.0.bin",
                                    "browser_download_url": "https://example/firmware.bin",
                                },
                                {
                                    "name": "firmware_manifest.json",
                                    "browser_download_url": "https://example/manifest.json",
                                },
                            ],
                        }
                    )
                return Response(
                    {
                        "version": "2.7.0",
                        "device": "lilygo-t-embed-s3",
                        "asset": "spotifydj-device-v2.7.0.bin",
                        "sha256": "a" * 64,
                        "size": 2113136,
                        "min_ha_integration": "1.0.0",
                    }
                )

        original_session = self.github.async_get_clientsession
        self.github.async_get_clientsession = lambda hass: Session()
        try:
            release = asyncio.run(
                self.github.fetch_latest_firmware_release(
                    object(),
                    {"firmware_repo": "pcvantol/spotify-dj-firmware"},
                )
            )
        finally:
            self.github.async_get_clientsession = original_session

        self.assertEqual(release.device, "lilygo-t-embed-s3")
        self.assertEqual(release.firmware_asset, "spotifydj-device-v2.7.0.bin")
        self.assertEqual(release.sha256, "a" * 64)
        self.assertEqual(release.size, 2113136)
        self.assertEqual(release.min_ha_integration, "1.0.0")

    def test_manifest_size_normalization(self) -> None:
        self.assertEqual(self.github._manifest_size("2113136"), 2113136)
        self.assertIsNone(self.github._manifest_size("not-a-number"))

    def test_fetch_manifest_parses_json_from_octet_stream_text(self) -> None:
        class Response:
            ok = True

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            async def text(self):
                return '{"device": "lilygo-t-embed-s3"}'

        class Session:
            def get(self, url, **kwargs):
                return Response()

        manifest = asyncio.run(
            self.github._fetch_manifest(
                Session(),
                {"browser_download_url": "https://example/firmware_manifest.json"},
            )
        )

        self.assertEqual(manifest["device"], "lilygo-t-embed-s3")

    def test_missing_manifest_device_falls_back_to_default_target(self) -> None:
        release = self.github.FirmwareRelease(
            version="2.7.0",
            title="SpotifyDJ v2.7.0",
            body=None,
            firmware_url="https://example/spotifydj-device-v2.7.0.bin",
            firmware_asset="spotifydj-device-v2.7.0.bin",
            device="lilygo-t-embed-s3",
        )

        self.assertEqual(release.device, "lilygo-t-embed-s3")

    def test_unsupported_manifest_device_warning_is_clear(self) -> None:
        with self.assertLogs(self.github._LOGGER, level="WARNING") as captured:
            self.github._LOGGER.warning(
                "SpotifyDJ firmware manifest for %s targets unsupported device %s",
                "2.7.0",
                "other-board",
            )

        self.assertIn("unsupported device other-board", captured.output[0])

if __name__ == "__main__":
    unittest.main()
