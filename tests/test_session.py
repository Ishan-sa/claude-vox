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


class SessionStartBootstrap(unittest.TestCase):
    """A plugin install runs no install.sh, so SessionStart writes the config."""

    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir
        self._real_detect = config.detect_backend
        config.detect_backend = lambda: ("command", ["true", "{text}"])

    def tearDown(self):
        config.detect_backend = self._real_detect
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def test_creates_config_on_first_session(self):
        self.assertFalse(os.path.exists(config.config_path()))
        cli.cmd_session_start([])
        self.assertTrue(os.path.exists(config.config_path()))

    def test_writes_the_detected_backend(self):
        cli.cmd_session_start([])
        cfg = config.load()
        self.assertEqual(cfg["command"]["argv"], ["true", "{text}"])

    def test_does_not_clobber_an_existing_config(self):
        config.save({"enabled": True, "speech_mode": "marker", "marker": "@@"})
        with contextlib.redirect_stdout(io.StringIO()):
            cli.cmd_session_start([])
        self.assertEqual(config.load().get("marker"), "@@")


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
