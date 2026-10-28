"""The voice-health checks that turn a silent fallback into a warning.

The case that motivated them: Homebrew upgraded Python, deleted the version the
edge-tts venv was built on, and every line came out in the offline fallback
voice for weeks with nothing saying why.
"""

import contextlib
import io
import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import cli, config, health  # noqa: E402

EDGE_CFG = {
    "enabled": True,
    "speech_mode": "assistant",
    "backend": "command",
    "command": {"argv": ["/x/backends/edge-tts.sh", "en-GB-RyanNeural", "{text}"]},
}


class HealthCase(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir
        self.addCleanup(self._restore)
        self.bin = os.path.join(self.dir, "venv", "bin")

    def _restore(self):
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def healthy_venv(self):
        """A venv whose python3 is real and can import a stub edge_tts."""
        os.makedirs(self.bin)
        os.symlink(sys.executable, os.path.join(self.bin, "python3"))
        stub = os.path.join(self.dir, "stub")
        os.makedirs(stub)
        open(os.path.join(stub, "edge_tts.py"), "w").close()
        os.environ["PYTHONPATH"] = stub
        self.addCleanup(os.environ.pop, "PYTHONPATH", None)

    def dangling_venv(self):
        """A venv whose interpreter was deleted out from under it."""
        os.makedirs(self.bin)
        os.symlink(os.path.join(self.dir, "gone", "python3.14"),
                   os.path.join(self.bin, "python3"))

    def note_fallback(self, reason):
        with open(os.path.join(self.dir, health.FALLBACK_FILE), "w") as fh:
            fh.write("1700000000 %s\n" % reason)


class VenvProblem(HealthCase):
    def test_a_working_venv_is_fine(self):
        self.healthy_venv()
        self.assertIsNone(health.venv_problem())

    def test_a_deleted_interpreter_is_caught(self):
        self.dangling_venv()
        self.assertIn("Homebrew", health.venv_problem())

    def test_a_venv_without_edge_tts_is_caught(self):
        os.makedirs(self.bin)
        os.symlink(sys.executable, os.path.join(self.bin, "python3"))
        self.assertIn("missing", health.venv_problem())


class Problem(HealthCase):
    def test_other_backends_are_never_flagged(self):
        self.dangling_venv()
        cfg = dict(EDGE_CFG, command={"argv": ["say", "{text}"]})
        self.assertIsNone(health.problem(cfg))

    def test_a_recorded_fallback_is_reported_with_its_reason(self):
        self.healthy_venv()
        self.note_fallback("synthesis failed")
        self.assertIn("synthesis failed", health.problem(EDGE_CFG))

    def test_the_warning_names_the_voice_and_the_fix(self):
        self.dangling_venv()
        warning = health.warning(EDGE_CFG)
        self.assertIn("en-GB-RyanNeural", warning)
        self.assertIn("/vox repair", warning)

    def test_a_healthy_setup_has_no_warning(self):
        self.healthy_venv()
        self.assertIsNone(health.warning(EDGE_CFG))


class SessionStartWarning(HealthCase):
    def _session_start(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_session_start([])
        return json.loads(out.getvalue()) if out.getvalue() else {}

    def test_a_broken_voice_warns_the_user_directly(self):
        config.save(EDGE_CFG)
        self.dangling_venv()
        result = self._session_start()
        self.assertIn("/vox repair", result["systemMessage"])

    def test_claude_is_asked_to_mention_it_too(self):
        config.save(EDGE_CFG)
        self.dangling_venv()
        context = self._session_start()["hookSpecificOutput"]["additionalContext"]
        self.assertIn("Voice mode (claude-vox) is ON", context)
        self.assertIn("first reply", context)

    def test_a_mode_without_instructions_still_carries_the_warning(self):
        config.save(dict(EDGE_CFG, speech_mode="bookends"))
        self.dangling_venv()
        self.assertIn("systemMessage", self._session_start())

    def test_a_healthy_voice_adds_nothing(self):
        config.save(EDGE_CFG)
        self.healthy_venv()
        self.assertNotIn("systemMessage", self._session_start())

    def test_nothing_is_said_while_vox_is_off(self):
        config.save(dict(EDGE_CFG, enabled=False))
        self.dangling_venv()
        self.assertEqual(self._session_start(), {})


class Status(HealthCase):
    def _status(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            cli.cmd_status([])
        return out.getvalue()

    def test_status_flags_a_broken_voice(self):
        config.save(EDGE_CFG)
        self.dangling_venv()
        self.assertIn("voice:   BROKEN", self._status())

    def test_status_says_ok_when_healthy(self):
        config.save(EDGE_CFG)
        self.healthy_venv()
        self.assertIn("voice:   ok", self._status())


if __name__ == "__main__":
    unittest.main()
