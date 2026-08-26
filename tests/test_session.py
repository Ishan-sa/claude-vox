import contextlib
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import cli, config  # noqa: E402


class Defaults(unittest.TestCase):
    def test_assistant_is_the_default_mode(self):
        self.assertEqual(config.DEFAULTS["speech_mode"], "assistant")

    def test_live_intro_defaults_on(self):
        self.assertTrue(config.DEFAULTS["live_intro"])


class SessionStartInjection(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir

    def tearDown(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def _run(self, **over):
        cfg = config.load()
        cfg["enabled"] = True
        cfg.update(over)
        config.save(cfg)
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cli.cmd_session_start([])
        return buf.getvalue()

    def test_assistant_mode_injects_the_summary_instruction(self):
        out = self._run(speech_mode="assistant")
        payload = json.loads(out)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn(config.DEFAULTS["marker"], context)
        self.assertIn("summar", context.lower())

    def test_marker_mode_still_injects(self):
        out = self._run(speech_mode="marker")
        self.assertIn("additionalContext", out)

    def test_bookends_mode_injects_nothing(self):
        self.assertEqual(self._run(speech_mode="bookends"), "")

    def test_disabled_injects_nothing(self):
        self.assertEqual(self._run(speech_mode="assistant", enabled=False), "")


if __name__ == "__main__":
    unittest.main()
