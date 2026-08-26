import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import transcript as t  # noqa: E402

MARKER = t.DEFAULT_MARKER

# The response from the screenshot that motivated natural mode.
SCREENSHOT = """Glad it's working, Sir -- and sorry it took that much digging. The hardware was fine the whole time; it was contention over `/dev/hidraw` and inconsistent mode metadata.

Where things stand:

- **http://127.0.0.1:7070** -- reopens on login
- **fanrgb blue** for scripting
- Both services enabled with linger on

Whenever you want it, the two loose ends are LAN access, and wiring it into ARIA. Both noted in memory, so just say the word."""


class ProseParagraphs(unittest.TestCase):
    def test_drops_lists_and_headers_keeps_prose(self):
        paras = t.prose_paragraphs(SCREENSHOT)
        self.assertEqual(len(paras), 2)
        self.assertTrue(paras[0].startswith("Glad it's working"))
        self.assertTrue(paras[1].startswith("Whenever you want it"))

    def test_removes_fenced_code_blocks(self):
        text = "Here is the fix.\n\n```python\nprint('secret')\n```\n\nAll done."
        paras = t.prose_paragraphs(text)
        self.assertNotIn("secret", " ".join(paras))
        self.assertEqual(paras, ["Here is the fix.", "All done."])

    def test_a_numbered_list_is_structural(self):
        text = "Steps:\n\n1. first\n2. second\n\nThat covers it."
        self.assertEqual(t.prose_paragraphs(text), ["That covers it."])


class NaturalSegments(unittest.TestCase):
    def test_returns_first_and_last_prose_paragraphs(self):
        intro, summary = t.natural_segments(SCREENSHOT)
        self.assertTrue(intro.startswith("Glad it's working"))
        self.assertTrue(summary.startswith("Whenever you want it"))
        self.assertIn("/dev/hidraw", intro)  # inline code survives as words

    def test_none_when_only_structure(self):
        intro, summary = t.natural_segments("- a\n- b\n\n# heading")
        self.assertIsNone(intro)
        self.assertIsNone(summary)


class Cap(unittest.TestCase):
    def test_short_text_is_untouched(self):
        self.assertEqual(t.cap("All tests pass.", 280), "All tests pass.")

    def test_cuts_on_a_sentence_boundary(self):
        text = "First sentence here. Second sentence runs well past the limit line."
        self.assertEqual(t.cap(text, 30), "First sentence here.")

    def test_falls_back_to_a_word_boundary_with_ellipsis(self):
        text = "aaaa bbbb cccc dddd eeee ffff gggg hhhh"
        capped = t.cap(text, 20)
        self.assertTrue(capped.endswith("..."))
        self.assertLessEqual(len(capped), 23)


class SpokenFromResponse(unittest.TestCase):
    def test_bookends_joins_intro_and_summary(self):
        spoken = t.spoken_from_response(SCREENSHOT, "bookends")
        self.assertIn("Glad it's working", spoken)
        self.assertIn("just say the word", spoken)
        self.assertIn(" ... ", spoken)

    def test_intro_mode_speaks_only_the_opening(self):
        spoken = t.spoken_from_response(SCREENSHOT, "intro")
        self.assertTrue(spoken.startswith("Glad it's working"))
        self.assertNotIn("just say the word", spoken)

    def test_summary_mode_speaks_only_the_closing(self):
        spoken = t.spoken_from_response(SCREENSHOT, "summary")
        self.assertTrue(spoken.startswith("Whenever you want it"))

    def test_a_marker_line_overrides_the_mode(self):
        text = "%s Precise spoken line.\n\nThen a long natural paragraph here." % MARKER
        self.assertEqual(t.spoken_from_response(text, "bookends"),
                         "Precise spoken line.")

    def test_marker_mode_stays_silent_without_a_marker(self):
        self.assertIsNone(t.spoken_from_response("Just prose.", "marker"))

    def test_single_paragraph_is_spoken_once_not_doubled(self):
        spoken = t.spoken_from_response("Only one thing to say here.", "bookends")
        self.assertEqual(spoken, "Only one thing to say here.")
        self.assertNotIn(" ... ", spoken)


if __name__ == "__main__":
    unittest.main()
