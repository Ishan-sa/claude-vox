import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import cli, config, speak  # noqa: E402


class PickOpener(unittest.TestCase):
    def test_returns_a_phrase_from_the_configured_list(self):
        cfg = {"opener": {"enabled": True, "phrases": ["On it.", "One moment."]}}
        self.assertIn(cli.pick_opener(cfg), cfg["opener"]["phrases"])

    def test_none_when_disabled(self):
        cfg = {"opener": {"enabled": False, "phrases": ["On it."]}}
        self.assertIsNone(cli.pick_opener(cfg))

    def test_none_when_no_phrases(self):
        self.assertIsNone(cli.pick_opener({"opener": {"enabled": True, "phrases": []}}))

    def test_none_when_section_missing(self):
        self.assertIsNone(cli.pick_opener({}))


class CachePath(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def _cfg(self, voice):
        return {"http": {"body": {"text": "{text}", "voice": voice}}}

    def test_same_text_and_voice_is_stable(self):
        a = speak.cache_path("On it.", self._cfg("ryan"))
        b = speak.cache_path("On it.", self._cfg("ryan"))
        self.assertEqual(a, b)

    def test_different_voice_gets_a_different_file(self):
        a = speak.cache_path("On it.", self._cfg("ryan"))
        b = speak.cache_path("On it.", self._cfg("guy"))
        self.assertNotEqual(a, b)

    def test_different_text_gets_a_different_file(self):
        a = speak.cache_path("On it.", self._cfg("ryan"))
        b = speak.cache_path("One moment.", self._cfg("ryan"))
        self.assertNotEqual(a, b)

    def test_lands_under_the_openers_cache_dir(self):
        path = speak.cache_path("On it.", self._cfg("ryan"))
        self.assertEqual(os.path.dirname(path),
                         os.path.join(self.dir, "openers"))
        self.assertTrue(path.endswith(".mp3"))


class OpenerDefaults(unittest.TestCase):
    def test_shipped_defaults_are_usable(self):
        # Off by default now that Claude's own intro fills the opener role,
        # but the phrases must stay valid for anyone who turns it back on.
        opener = config.DEFAULTS["opener"]
        self.assertFalse(opener["enabled"])
        self.assertTrue(all(isinstance(p, str) and p for p in opener["phrases"]))


if __name__ == "__main__":
    unittest.main()
