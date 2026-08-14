import unittest

from config import DEFAULT_USER_SETTINGS, normalized_settings


class SettingsTests(unittest.TestCase):
    def test_invalid_values_return_safe_defaults(self):
        settings = normalized_settings(
            {"duration": "999", "aspect_ratio": "freeform", "resolution": "8k", "model": "ignored"}
        )
        self.assertEqual(settings, DEFAULT_USER_SETTINGS)

    def test_photo_route_adapts_incompatible_settings(self):
        settings = normalized_settings(
            {"duration": "6", "aspect_ratio": "1:1", "resolution": "480p"}, route="kling"
        )
        self.assertEqual(
            settings,
            {"duration": "5", "aspect_ratio": "9:16", "resolution": "720p"},
        )

    def test_text_route_preserves_supported_settings(self):
        settings = normalized_settings(
            {"duration": "10", "aspect_ratio": "1:1", "resolution": "1080p"}, route="grok"
        )
        self.assertEqual(settings["duration"], "10")
        self.assertEqual(settings["aspect_ratio"], "1:1")
        self.assertEqual(settings["resolution"], "1080p")


if __name__ == "__main__":
    unittest.main()
