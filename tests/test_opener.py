import contextlib
import io
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


class OpenerToggle(unittest.TestCase):
    """`vox opener on|off` -- the switch that used to require editing JSON."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def _run(self, *args):
        out = io.StringIO()
        # stderr too, so the usage-error case does not litter the test run.
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
            code = cli.cmd_opener(list(args))
        return code, out.getvalue()

    def test_on_then_off_round_trips(self):
        self._run("on")
        self.assertTrue(config.load()["opener"]["enabled"])
        self._run("off")
        self.assertFalse(config.load()["opener"]["enabled"])

    def test_off_keeps_whatever_phrases_the_user_wrote(self):
        cfg = config.load()
        cfg["opener"]["phrases"] = ["Righto."]
        config.save(cfg)
        self._run("on")
        self._run("off")
        self.assertEqual(config.load()["opener"]["phrases"], ["Righto."])

    def test_on_with_no_phrases_says_so_rather_than_looking_broken(self):
        code, out = self._run("on")
        self.assertEqual(code, 0)
        self.assertIn("no phrases", out)
        self.assertIn(config.config_path(), out)

    def test_with_no_argument_it_only_reports(self):
        config.set_opener_enabled(True)
        code, out = self._run()
        self.assertEqual(code, 0)
        self.assertIn("ON", out)
        self.assertTrue(config.load()["opener"]["enabled"], "must not toggle")

    def test_a_bad_argument_changes_nothing(self):
        config.set_opener_enabled(True)
        code, _ = self._run("maybe")
        self.assertEqual(code, 2)
        self.assertTrue(config.load()["opener"]["enabled"])

    def test_status_reports_the_opener_so_it_is_never_a_mystery_voice(self):
        config.set_opener_enabled(True)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_status([])
        self.assertIn("opener:", out.getvalue())
        self.assertIn("on", out.getvalue())


class OpenerWiring(unittest.TestCase):
    def test_the_hush_hook_worker_is_registered_and_treated_as_a_hook(self):
        # Renamed out of the way so plain `opener` could become the toggle;
        # both halves have to stay wired or the opener silently stops working.
        self.assertIn("speak-opener", cli.COMMANDS)
        self.assertIn("speak-opener", cli.HOOKS)
        self.assertIs(cli.COMMANDS["speak-opener"], cli.cmd_speak_opener)

    def test_the_toggle_is_not_treated_as_a_hook(self):
        # Hooks swallow errors and exit 0; a user-facing command must not.
        self.assertNotIn("opener", cli.HOOKS)


class OpenerDefaults(unittest.TestCase):
    def test_nothing_canned_ships(self):
        # A stock phrase nobody chose, announcing every turn, is the first
        # thing a user wants gone -- and the last thing they can find. Off is
        # not enough on its own: the phrases have to be absent too, or the
        # next person to flip the switch inherits someone else's words.
        opener = config.DEFAULTS["opener"]
        self.assertFalse(opener["enabled"])
        self.assertEqual(opener["phrases"], [])

    def test_an_enabled_opener_with_no_phrases_stays_silent(self):
        self.assertIsNone(cli.pick_opener(config.merge(
            config.DEFAULTS, {"opener": {"enabled": True}})))


if __name__ == "__main__":
    unittest.main()
