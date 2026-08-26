import json
import os
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import cli, transcript  # noqa: E402


def write_transcript(entries):
    handle, path = tempfile.mkstemp(suffix=".jsonl")
    with os.fdopen(handle, "w", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(json.dumps(entry) + "\n")
    return path


def assistant(text, uuid):
    return {"type": "assistant", "isSidechain": False, "uuid": uuid,
            "message": {"role": "assistant",
                        "content": [{"type": "text", "text": text}]}}


def append(path, entry):
    with open(path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry) + "\n")


class LastAssistantEntryTest(unittest.TestCase):
    def test_returns_uuid_with_text(self):
        path = write_transcript([assistant("first", "a"), assistant("second", "b")])
        self.assertEqual(transcript.last_assistant_entry(path), ("b", "second"))

    def test_skips_sidechain(self):
        sub = assistant("subagent", "s")
        sub["isSidechain"] = True
        path = write_transcript([assistant("main", "m"), sub])
        self.assertEqual(transcript.last_assistant_entry(path), ("m", "main"))

    def test_empty_transcript(self):
        path = write_transcript([])
        self.assertEqual(transcript.last_assistant_entry(path), (None, None))


class FreshEntryTest(unittest.TestCase):
    def test_new_entry_returned_immediately(self):
        path = write_transcript([assistant("old", "a"), assistant("new", "b")])
        self.assertEqual(cli._wait_for_new(path, "a", wait=0.05), ("b", "new"))

    def test_no_previous_state_returns_newest(self):
        path = write_transcript([assistant("only", "a")])
        self.assertEqual(cli._wait_for_new(path, None, wait=0.05), ("a", "only"))

    def test_stale_read_is_not_spoken_again(self):
        """The hook firing before the response is flushed must stay silent."""
        path = write_transcript([assistant("already said", "a")])
        self.assertEqual(cli._wait_for_new(path, "a", wait=0.05), (None, None))

    def test_waits_for_a_late_write(self):
        """A response flushed just after the hook fires is still spoken."""
        path = write_transcript([assistant("already said", "a")])

        def late():
            time.sleep(0.1)
            append(path, assistant("the real one", "b"))

        threading.Thread(target=late, daemon=True).start()
        self.assertEqual(cli._wait_for_new(path, "a", wait=2.0, interval=0.05),
                         ("b", "the real one"))


if __name__ == "__main__":
    unittest.main()
