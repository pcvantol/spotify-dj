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

    class ClientResponseError(Exception):
        def __init__(self, *args, status=None, **kwargs):
            super().__init__("client response error")
            self.status = status

    aiohttp.ClientTimeout = ClientTimeout
    aiohttp.ClientResponseError = ClientResponseError

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

    package = types.ModuleType("custom_components.djconnect")
    package.__path__ = [str(ROOT / "custom_components" / "djconnect")]
    sys.modules["custom_components.djconnect"] = package


class GithubFirmwareTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_github_stubs()
        cls.github = importlib.import_module("custom_components.djconnect.github")

    def test_select_release_assets_matches_djconnect_device_binary(self) -> None:
        assets = self.github._select_release_assets(
            [
                {
                    "name": "djconnect-device-v3.0.4.bin",
                    "browser_download_url": "https://example/firmware.bin",
                },
                {
                    "name": "firmware_manifest.json",
                    "browser_download_url": "https://example/manifest.json",
                },
            ],
            "djconnect-device",
        )

        self.assertEqual(assets.firmware["name"], "djconnect-device-v3.0.4.bin")
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
                            "tag_name": "v3.0.4",
                            "name": "DJConnect v3.0.4",
                            "assets": [
                                {
                                    "name": "djconnect-device-v3.0.4.bin",
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
                        "version": "3.0.4",
                        "device": "lilygo-t-embed-s3",
                        "asset": "djconnect-device-v3.0.4.bin",
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
                    {"firmware_repo": "pcvantol/djconnect-firmware"},
                )
            )
        finally:
            self.github.async_get_clientsession = original_session

        self.assertEqual(release.device, "lilygo-t-embed-s3")
        self.assertEqual(release.firmware_asset, "djconnect-device-v3.0.4.bin")
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
            version="3.0.4",
            title="DJConnect v3.0.4",
            body=None,
            firmware_url="https://example/djconnect-device-v3.0.4.bin",
            firmware_asset="djconnect-device-v3.0.4.bin",
            device="lilygo-t-embed-s3",
        )

        self.assertEqual(release.device, "lilygo-t-embed-s3")

    def test_unsupported_manifest_device_warning_is_clear(self) -> None:
        with self.assertLogs(self.github._LOGGER, level="WARNING") as captured:
            self.github._LOGGER.warning(
                "DJConnect firmware manifest for %s targets unsupported device %s",
                "3.0.4",
                "other-board",
            )

        self.assertIn("unsupported device other-board", captured.output[0])

    def test_github_rate_limit_returns_no_release_without_crash(self) -> None:
        class ClientResponseError(Exception):
            def __init__(self, *args, status=None, **kwargs):
                super().__init__("rate limit exceeded")
                self.status = status

        class Response:
            status = 403

            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc, traceback):
                return None

            def raise_for_status(self):
                raise ClientResponseError(status=403)

        class Session:
            def get(self, url, **kwargs):
                return Response()

        original_error = self.github.ClientResponseError
        original_session = self.github.async_get_clientsession
        self.github.ClientResponseError = ClientResponseError
        self.github.async_get_clientsession = lambda hass: Session()
        try:
            release = asyncio.run(
                self.github.fetch_latest_firmware_release(
                    object(),
                    {"firmware_repo": "pcvantol/djconnect-firmware"},
                )
            )
        finally:
            self.github.ClientResponseError = original_error
            self.github.async_get_clientsession = original_session

        self.assertIsNone(release)

if __name__ == "__main__":
    unittest.main()
