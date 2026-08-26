import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import config  # noqa: E402


class ConfigHome(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved


class Load(ConfigHome):
    def test_missing_file_yields_defaults(self):
        cfg = config.load()
        self.assertFalse(cfg["enabled"])
        self.assertEqual(cfg["backend"], config.DEFAULTS["backend"])

    def test_partial_file_keeps_nested_defaults(self):
        with open(config.config_path(), "w", encoding="utf-8") as fh:
            json.dump({"backend": "http", "http": {"url": "http://x/speak"}}, fh)
        cfg = config.load()
        self.assertEqual(cfg["http"]["url"], "http://x/speak")
        # Untouched siblings survive the overlay.
        self.assertEqual(cfg["http"]["audio_url_field"], "url")
        self.assertIn("play_command", cfg["http"])

    def test_corrupt_file_falls_back_to_defaults(self):
        with open(config.config_path(), "w", encoding="utf-8") as fh:
            fh.write("{not json")
        self.assertEqual(config.load()["backend"], config.DEFAULTS["backend"])


class Toggle(ConfigHome):
    def test_enabling_persists_and_preserves_other_settings(self):
        config.save(config.merge(config.DEFAULTS, {"marker": "@@"}))
        config.set_enabled(True)
        cfg = config.load()
        self.assertTrue(cfg["enabled"])
        self.assertEqual(cfg["marker"], "@@")

    def test_disabling_persists(self):
        config.set_enabled(True)
        config.set_enabled(False)
        self.assertFalse(config.load()["enabled"])


class Merge(unittest.TestCase):
    def test_does_not_mutate_the_defaults(self):
        config.merge(config.DEFAULTS, {"http": {"url": "http://mutated"}})
        self.assertEqual(config.DEFAULTS["http"]["url"],
                         "http://127.0.0.1:5050/speak")


class Bootstrap(ConfigHome):
    def test_writes_a_config_once_then_leaves_it_alone(self):
        path, created = config.bootstrap()
        self.assertTrue(created)
        self.assertTrue(os.path.exists(path))
        with open(path, "r", encoding="utf-8") as fh:
            json.load(fh)  # must be valid JSON
        _, created_again = config.bootstrap()
        self.assertFalse(created_again)


if __name__ == "__main__":
    unittest.main()
