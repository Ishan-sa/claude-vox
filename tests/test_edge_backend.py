"""Drive backends/edge-tts.sh with a stub synthesiser and a stub player.

The script is shell, so these tests run it for real and assert on what it
invoked -- stubs record their argv to a log rather than making sound. That
covers the parts most likely to break silently in a hook: whether a line was
cached, whether the fallback fired, and whether the prosody flags kept the
single-token form edge-tts requires.
"""

import os
import shutil
import subprocess
import sys
import tempfile
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BACKEND = os.path.join(REPO, "backends", "edge-tts.sh")

STUB_EDGE = """#!/bin/sh
echo "$@" >> "$STUB_LOG/edge.log"
out=""
while [ $# -gt 0 ]; do
    case "$1" in --write-media) out="$2" ;; esac
    shift
done
[ "${STUB_EDGE_FAIL:-0}" = "1" ] && exit 1
printf 'ID3stub-audio-bytes' > "$out"
exit 0
"""

STUB_RECORDER = """#!/bin/sh
echo "$@" >> "$STUB_LOG/%s.log"
exit 0
"""


class EdgeBackend(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.dir, True)
        self.vox_home = os.path.join(self.dir, "vox")
        self.stub_bin = os.path.join(self.dir, "bin")
        self.log = os.path.join(self.dir, "log")
        os.makedirs(self.stub_bin)
        os.makedirs(self.log)
        # The script prefers the venv's edge-tts over anything on PATH.
        venv_bin = os.path.join(self.vox_home, "venv", "bin")
        os.makedirs(venv_bin)
        self._write(os.path.join(venv_bin, "edge-tts"), STUB_EDGE)
        # Shadow the real players and offline voices so nothing makes noise.
        for name in ("afplay", "mpv", "ffplay", "mpg123", "cvlc",
                     "say", "espeak-ng", "espeak", "spd-say"):
            self._write(os.path.join(self.stub_bin, name), STUB_RECORDER % name)

    def _write(self, path, body):
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(body)
        os.chmod(path, 0o755)

    def _run(self, *args, **kwargs):
        env = dict(os.environ)
        env["CLAUDE_VOX_HOME"] = self.vox_home
        env["STUB_LOG"] = self.log
        env["PATH"] = self.stub_bin + os.pathsep + "/usr/bin" + os.pathsep + "/bin"
        env.update(kwargs.pop("env", {}))
        return subprocess.run([BACKEND] + list(args), env=env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    def _log(self, name):
        try:
            with open(os.path.join(self.log, name + ".log"), encoding="utf-8") as fh:
                return [line for line in fh.read().splitlines() if line]
        except IOError:
            return []

    def _cached(self):
        cache = os.path.join(self.vox_home, "cache")
        return [n for n in os.listdir(cache) if n.endswith(".mp3")] \
            if os.path.isdir(cache) else []


class Caching(EdgeBackend):
    def test_a_short_line_is_synthesised_once_and_replayed_from_cache(self):
        for _ in range(3):
            self._run("en-GB-RyanNeural", "On it, Sir.")
        self.assertEqual(len(self._log("edge")), 1, "should synthesise only once")
        self.assertEqual(len(self._log("afplay")), 3, "should play every time")
        self.assertEqual(len(self._cached()), 1)

    def test_changing_the_voice_re_renders_rather_than_replaying_the_old_one(self):
        self._run("en-GB-RyanNeural", "On it, Sir.")
        self._run("en-GB-ThomasNeural", "On it, Sir.")
        self.assertEqual(len(self._log("edge")), 2)
        self.assertEqual(len(self._cached()), 2)

    def test_changing_the_prosody_re_renders_too(self):
        self._run("en-GB-RyanNeural", "On it, Sir.")
        self._run("en-GB-RyanNeural", "On it, Sir.", env={"VOX_RATE": "-20%"})
        self.assertEqual(len(self._log("edge")), 2)

    def test_a_long_line_is_never_cached(self):
        self._run("en-GB-RyanNeural", "word " * 60)
        self.assertEqual(self._cached(), [])
        self.assertEqual(len(self._log("afplay")), 1)

    def test_a_long_line_leaves_no_temp_file_behind(self):
        tmp = os.path.join(self.dir, "tmp")
        os.makedirs(tmp)
        self._run("en-GB-RyanNeural", "word " * 60, env={"TMPDIR": tmp})
        self.assertEqual(os.listdir(tmp), [])

    def test_a_failed_synthesis_leaves_no_partial_file_to_be_cached(self):
        self._run("en-GB-RyanNeural", "On it, Sir.", env={"STUB_EDGE_FAIL": "1"})
        self.assertEqual(self._cached(), [])

    def test_the_cache_is_pruned_once_it_outgrows_the_limit(self):
        for i in range(8):
            self._run("en-GB-RyanNeural", "line number %d" % i,
                      env={"VOX_CACHE_KEEP": "5"})
        self.assertLessEqual(len(self._cached()), 5)


class Prosody(EdgeBackend):
    def test_rate_and_pitch_are_passed_as_single_tokens(self):
        # `--rate -4%` makes argparse read the value as a flag and edge-tts
        # exits with a usage error the hook would swallow into silence.
        self._run("en-GB-RyanNeural", "On it, Sir.")
        call = self._log("edge")[0]
        self.assertIn("--rate=-4%", call)
        self.assertIn("--pitch=-4Hz", call)
        self.assertNotIn("--rate -4%", call)

    def test_prosody_is_overridable_from_the_environment(self):
        self._run("en-GB-RyanNeural", "On it, Sir.",
                  env={"VOX_RATE": "+10%", "VOX_PITCH": "+2Hz"})
        call = self._log("edge")[0]
        self.assertIn("--rate=+10%", call)
        self.assertIn("--pitch=+2Hz", call)


class Fallback(EdgeBackend):
    def test_a_failed_synthesis_speaks_through_the_offline_voice(self):
        self._run("en-GB-RyanNeural", "On it, Sir.", env={"STUB_EDGE_FAIL": "1"})
        self.assertEqual(len(self._log("say")), 1)
        self.assertEqual(self._log("afplay"), [])

    def test_a_missing_synthesiser_speaks_through_the_offline_voice(self):
        os.remove(os.path.join(self.vox_home, "venv", "bin", "edge-tts"))
        self._run("en-GB-RyanNeural", "On it, Sir.")
        self.assertEqual(len(self._log("say")), 1)

    def test_failure_still_exits_zero_so_a_hook_never_wedges(self):
        result = self._run("en-GB-RyanNeural", "On it, Sir.",
                           env={"STUB_EDGE_FAIL": "1"})
        self.assertEqual(result.returncode, 0)

    def test_empty_text_is_a_silent_no_op(self):
        result = self._run("en-GB-RyanNeural", "   ")
        self.assertEqual(result.returncode, 0)
        self.assertEqual(self._log("edge"), [])
        self.assertEqual(self._log("say"), [])


class Prewarm(EdgeBackend):
    def test_prewarm_synthesises_without_playing(self):
        self._run("--prewarm", "en-GB-RyanNeural", "On it, Sir.")
        self.assertEqual(len(self._log("edge")), 1)
        self.assertEqual(self._log("afplay"), [])
        self.assertEqual(len(self._cached()), 1)

    def test_a_prewarmed_line_plays_from_cache_without_re_synthesising(self):
        self._run("--prewarm", "en-GB-RyanNeural", "On it, Sir.")
        self._run("en-GB-RyanNeural", "On it, Sir.")
        self.assertEqual(len(self._log("edge")), 1)
        self.assertEqual(len(self._log("afplay")), 1)

    def test_prewarm_does_not_fall_back_to_the_offline_voice(self):
        # Warming is a background nicety; making the speakers talk during it
        # would be a surprise.
        self._run("--prewarm", "en-GB-RyanNeural", "On it, Sir.",
                  env={"STUB_EDGE_FAIL": "1"})
        self.assertEqual(self._log("say"), [])


if __name__ == "__main__":
    unittest.main()
