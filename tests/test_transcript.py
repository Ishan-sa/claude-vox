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


def assistant(text, sidechain=False):
    return {"type": "assistant", "isSidechain": sidechain,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": text}]}}


class ExtractMarkedLine(unittest.TestCase):
    def test_returns_text_after_marker(self):
        body = "Some analysis here.\n\n%s Fixed the login bug." % MARKER
        self.assertEqual(transcript.extract_marked_line(body, MARKER),
                         "Fixed the login bug.")

    def test_returns_none_when_unmarked(self):
        self.assertIsNone(transcript.extract_marked_line("No marker at all", MARKER))

    def test_uses_last_marker_when_several_appear(self):
        body = "%s first\ntext\n%s second" % (MARKER, MARKER)
        self.assertEqual(transcript.extract_marked_line(body, MARKER), "second")

    def test_strips_markdown_from_spoken_text(self):
        body = "%s Ran `pytest` and **all 12** passed." % MARKER
        self.assertEqual(transcript.extract_marked_line(body, MARKER),
                         "Ran pytest and all 12 passed.")

    def test_drops_link_targets_but_keeps_labels(self):
        body = "%s Opened the [pull request](https://example.com/pr/1)." % MARKER
        self.assertEqual(transcript.extract_marked_line(body, MARKER),
                         "Opened the pull request.")

    def test_marker_mid_line_drops_the_prefix(self):
        body = "**%s** Deployed to staging." % MARKER
        self.assertEqual(transcript.extract_marked_line(body, MARKER),
                         "Deployed to staging.")

    def test_empty_after_marker_is_silent(self):
        self.assertIsNone(transcript.extract_marked_line("%s   " % MARKER, MARKER))


class LastAssistantText(unittest.TestCase):
    def test_picks_the_most_recent_assistant_entry(self):
        path = write_transcript([assistant("older"), {"type": "user"},
                                 assistant("newer")])
        self.addCleanup(os.remove, path)
        self.assertEqual(transcript.last_assistant_text(path), "newer")

    def test_ignores_subagent_sidechain_output(self):
        path = write_transcript([assistant("main agent"),
                                 assistant("subagent chatter", sidechain=True)])
        self.addCleanup(os.remove, path)
        self.assertEqual(transcript.last_assistant_text(path), "main agent")

    def test_skips_entries_whose_last_block_is_a_tool_call(self):
        path = write_transcript([
            assistant("spoken summary"),
            {"type": "assistant", "isSidechain": False,
             "message": {"role": "assistant",
                         "content": [{"type": "tool_use", "name": "Bash"}]}},
        ])
        self.addCleanup(os.remove, path)
        self.assertEqual(transcript.last_assistant_text(path), "spoken summary")

    def test_tolerates_a_half_written_final_line(self):
        path = write_transcript([assistant("complete entry")])
        with open(path, "a", encoding="utf-8") as fh:
            fh.write('{"type": "assistant", "mess')
        self.addCleanup(os.remove, path)
        self.assertEqual(transcript.last_assistant_text(path), "complete entry")

    def test_returns_none_for_a_transcript_with_no_assistant_text(self):
        path = write_transcript([{"type": "user"}])
        self.addCleanup(os.remove, path)
        self.assertIsNone(transcript.last_assistant_text(path))


class SpokenLine(unittest.TestCase):
    def test_end_to_end_from_transcript_to_spoken_text(self):
        path = write_transcript([assistant("Details.\n%s All tests pass." % MARKER)])
        self.addCleanup(os.remove, path)
        self.assertEqual(transcript.spoken_line(path, MARKER), "All tests pass.")

    def test_unmarked_response_stays_silent(self):
        path = write_transcript([assistant("Just prose, nothing to announce.")])
        self.addCleanup(os.remove, path)
        self.assertIsNone(transcript.spoken_line(path, MARKER))


if __name__ == "__main__":
    unittest.main()
