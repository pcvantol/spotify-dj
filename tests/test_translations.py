from __future__ import annotations

import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
TRANSLATIONS = ROOT / "custom_components" / "spotify_dj" / "translations"

CONFIG_FLOW_ERROR_KEYS = {
    "missing_pair_code",
    "invalid_pair_code",
    "spotify_client_id_required",
    "external_url_required",
    "external_url_https_required",
    "external_url_invalid",
    "oauth_setup_failed",
    "oauth_not_completed",
    "oauth_failed",
}


class TranslationTest(unittest.TestCase):
    def test_config_flow_error_keys_are_translated(self) -> None:
        for language in ("en", "nl"):
            with self.subTest(language=language):
                data = json.loads((TRANSLATIONS / f"{language}.json").read_text())
                errors = data["config"]["error"]
                missing = CONFIG_FLOW_ERROR_KEYS - set(errors)
                self.assertFalse(missing, f"Missing {language} translations: {sorted(missing)}")


if __name__ == "__main__":
    unittest.main()
