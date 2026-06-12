from __future__ import annotations

import importlib
import types
import unittest

from tests.test_config_flow_helpers import install_homeassistant_stubs


class DiscoveryHelperTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        install_homeassistant_stubs()
        cls.discovery = importlib.import_module("custom_components.djconnect.discovery")

    def _info(self, *, props, server="djconnect.local.", port=60955, addresses=None):
        class Info:
            name = "DJConnect._djconnect._tcp.local."

            def __init__(self):
                self.properties = props
                self.server = server
                self.port = port

            def parsed_addresses(self):
                return addresses or []

        return Info()

    def test_ios_txt_with_valid_device_id_is_accepted(self) -> None:
        client = self.discovery._client_from_service_info(
            self._info(
                props={
                    b"device_id": b"djconnect-ios-9F8FA6931AA3",
                    b"client_type": b"ios",
                    b"device_name": b"DJConnect iPhone",
                    b"version": b"3.1.19",
                    b"paired": b"false",
                    b"api": b"/api/device",
                },
                addresses=["192.168.1.42"],
                port=51193,
            )
        )

        self.assertIsNotNone(client)
        self.assertEqual(client.local_url, "http://192.168.1.42:51193")
        self.assertEqual(client.client_type, "ios")
        self.assertEqual(client.device_name, "DJConnect iPhone")
        self.assertFalse(client.paired)

    def test_macos_txt_with_valid_device_id_is_accepted(self) -> None:
        client = self.discovery._client_from_service_info(
            self._info(
                props={
                    "device_id": "djconnect-macos-68B74487726D",
                    "client_type": "macos",
                    "name": "DJConnect Mac",
                },
                server="djconnect-mac.local.",
            )
        )

        self.assertIsNotNone(client)
        self.assertEqual(client.local_url, "http://djconnect-mac.local:60955")
        self.assertEqual(client.client_type, "macos")

    def test_client_type_device_id_mismatch_is_ignored(self) -> None:
        client = self.discovery._client_from_service_info(
            self._info(
                props={
                    "device_id": "djconnect-ios-9F8FA6931AA3",
                    "client_type": "macos",
                }
            )
        )

        self.assertIsNone(client)

    def test_esp32_txt_still_validates(self) -> None:
        client = self.discovery._client_from_service_info(
            self._info(
                props={
                    "device_id": "djconnect-lilygo-t-embed-s3-90B70990A994",
                    "client_type": "esp32",
                    "device_name": "DJConnect ESP",
                }
            )
        )

        self.assertIsNotNone(client)
        self.assertEqual(client.client_type, "esp32")

    def test_pairing_info_overrides_txt_metadata(self) -> None:
        base = self.discovery.DiscoveredClient(
            local_url="http://djconnect.local:60955",
            device_id="djconnect-ios-9F8FA6931AA3",
            client_type="ios",
            device_name="TXT Name",
        )

        client = self.discovery._client_with_pairing_info(
            base,
            {
                "local_url": "http://192.168.1.42:51193",
                "device_id": "djconnect-ios-111122223333",
                "client_type": "ios",
                "device_name": "Pairing Info Name",
                "pair_code": "123456",
                "app_version": "3.1.20",
            },
        )

        self.assertEqual(client.local_url, "http://192.168.1.42:51193")
        self.assertEqual(client.device_id, "djconnect-ios-111122223333")
        self.assertEqual(client.device_name, "Pairing Info Name")
        self.assertEqual(client.pair_code, "123456")
        self.assertEqual(client.version, "3.1.20")


if __name__ == "__main__":
    unittest.main()
