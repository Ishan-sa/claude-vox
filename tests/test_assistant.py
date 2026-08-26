import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import transcript  # noqa: E402

MARKER = transcript.DEFAULT_MARKER


def write_transcript(entries):
    handle, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return path


def entry(uuid, blocks, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain, "uuid": uuid,
            "message": {"role": "assistant", "content": blocks}}


def text_block(text):
    return {"type": "text", "text": text}


def tool_block(name="Bash"):
    return {"type": "tool_use", "name": name, "input": {}}


def thinking_block():
    return {"type": "thinking", "thinking": "hmm"}


class AssistantModeSummary(unittest.TestCase):
    def spoken(self, text):
        return transcript.spoken_from_response(text, mode="assistant", marker=MARKER)

    def test_marker_line_becomes_the_summary(self):
        body = "Root cause analysis here.\n\n%s Fixed the dropdown, Sir." % MARKER
        self.assertEqual(self.spoken(body), "Fixed the dropdown, Sir.")

    def test_marker_summary_is_run_through_speakable(self):
        body = "%s Fixed in `TimezonePicker.tsx`, Sir." % MARKER
        out = self.spoken(body)
        self.assertNotIn("TimezonePicker", out)
        self.assertIn("Fixed in", out)
        self.assertIn("Sir", out)

    def test_falls_back_to_closing_prose_without_marker(self):
        body = ("Opening remark about the work.\n\n"
                "The closing thought that wraps it up.")
        self.assertEqual(self.spoken(body), "The closing thought that wraps it up.")

    def test_fallback_prose_is_also_speakable(self):
        body = "First line.\n\nWorth a look in src/app/main.tsx before shipping."
        out = self.spoken(body)
        self.assertNotIn("src/app", out)
        self.assertIn("Worth a look", out)


class FirstWorkingIntro(unittest.TestCase):
    def test_first_text_followed_by_tool_is_the_intro(self):
        path = write_transcript([
            entry("th", [thinking_block()]),
            entry("x", [text_block("I'll dig into the dropdown.")]),
            entry("t", [tool_block()]),
        ])
        self.assertEqual(transcript.first_working_intro(path, None),
                         ("x", "I'll dig into the dropdown."))

    def test_text_and_tool_in_one_message(self):
        path = write_transcript([
            entry("c", [text_block("Looking now."), tool_block()]),
        ])
        self.assertEqual(transcript.first_working_intro(path, None),
                         ("c", "Looking now."))

    def test_text_only_turn_has_no_live_intro(self):
        path = write_transcript([
            entry("z", [text_block("Voice is on, Sir.")]),
        ])
        self.assertEqual(transcript.first_working_intro(path, None), (None, None))

    def test_respects_the_baseline_uuid(self):
        path = write_transcript([
            entry("a", [text_block("previous answer")]),
            entry("b", [text_block("I'll look into it.")]),
            entry("t", [tool_block()]),
        ])
        self.assertEqual(transcript.first_working_intro(path, "a"),
                         ("b", "I'll look into it."))

    def test_ignores_sidechain_intro(self):
        path = write_transcript([
            entry("s", [text_block("subagent chatter")], sidechain=True),
            entry("s2", [tool_block()], sidechain=True),
            entry("x", [text_block("Main-agent intro.")]),
            entry("t", [tool_block()]),
        ])
        self.assertEqual(transcript.first_working_intro(path, None),
                         ("x", "Main-agent intro."))

    def test_none_until_the_tool_call_lands(self):
        # The intro text exists but no tool has appeared yet: stay silent so a
        # poller waits for work to actually start.
        path = write_transcript([
            entry("x", [text_block("I'll dig in.")]),
        ])
        self.assertEqual(transcript.first_working_intro(path, None), (None, None))


if __name__ == "__main__":
    unittest.main()
