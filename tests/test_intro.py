import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import cli, config, speak  # noqa: E402


def write_transcript(entries):
    handle, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return path


def append(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


def entry(uuid, blocks):
    return {"type": "assistant", "isSidechain": False, "uuid": uuid,
            "message": {"role": "assistant", "content": blocks}}


def text_block(text):
    return {"type": "text", "text": text}


def tool_block():
    return {"type": "tool_use", "name": "Bash", "input": {}}


class WaitForWorkingIntro(unittest.TestCase):
    def test_present_intro_returns_at_once(self):
        path = write_transcript([entry("x", [text_block("Digging in.")]),
                                 entry("t", [tool_block()])])
        self.assertEqual(cli._wait_for_working_intro(path, None, wait=0.05),
                         ("x", "Digging in."))

    def test_times_out_on_text_only(self):
        path = write_transcript([entry("z", [text_block("Voice is on, Sir.")])])
        self.assertEqual(cli._wait_for_working_intro(path, None, wait=0.05),
                         (None, None))

    def test_waits_for_the_tool_call_to_land(self):
        path = write_transcript([entry("x", [text_block("Digging in.")])])

        def work_starts():
            time.sleep(0.1)
            append(path, entry("t", [tool_block()]))

        threading.Thread(target=work_starts, daemon=True).start()
        self.assertEqual(cli._wait_for_working_intro(path, None, wait=2.0,
                                                     interval=0.05),
                         ("x", "Digging in."))


class CmdSpeakIntro(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.mkdtemp()
        self._saved = os.environ.get("CLAUDE_VOX_HOME")
        os.environ["CLAUDE_VOX_HOME"] = self.dir
        self.spoken = []
        self._real_speak = speak.speak
        speak.speak = lambda text, cfg, **kw: self.spoken.append(text) or True

    def tearDown(self):
        speak.speak = self._real_speak
        if self._saved is None:
            os.environ.pop("CLAUDE_VOX_HOME", None)
        else:
            os.environ["CLAUDE_VOX_HOME"] = self._saved

    def _configure(self, **over):
        cfg = config.load()
        cfg["enabled"] = True
        cfg["speech_mode"] = "assistant"
        cfg["live_intro"] = True
        cfg.update(over)
        config.save(cfg)

    def _working_transcript(self, intro="I'll dig into the dropdown."):
        return write_transcript([entry("x", [text_block(intro)]),
                                 entry("t", [tool_block()])])

    def test_speaks_the_groomed_intro(self):
        self._configure()
        path = self._working_transcript("I'll check `useThing.tsx` now.")
        cli.cmd_speak_intro([path, ""])
        self.assertEqual(len(self.spoken), 1)
        self.assertNotIn("useThing", self.spoken[0])
        self.assertIn("I'll check", self.spoken[0])

    def test_records_last_spoken(self):
        self._configure()
        cli.cmd_speak_intro([self._working_transcript(), ""])
        self.assertEqual(cli._read_last_spoken(), "x")

    def test_silent_when_mode_is_not_assistant(self):
        self._configure(speech_mode="bookends")
        cli.cmd_speak_intro([self._working_transcript(), ""])
        self.assertEqual(self.spoken, [])

    def test_silent_when_live_intro_off(self):
        self._configure(live_intro=False)
        cli.cmd_speak_intro([self._working_transcript(), ""])
        self.assertEqual(self.spoken, [])

    def test_silent_when_disabled(self):
        self._configure(enabled=False)
        cli.cmd_speak_intro([self._working_transcript(), ""])
        self.assertEqual(self.spoken, [])

    def test_does_not_respeak_the_same_uuid(self):
        self._configure()
        cli._write_last_spoken("x")
        cli.cmd_speak_intro([self._working_transcript(), ""])
        self.assertEqual(self.spoken, [])


if __name__ == "__main__":
    unittest.main()
