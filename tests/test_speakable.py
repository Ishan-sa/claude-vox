import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import transcript  # noqa: E402


class Speakable(unittest.TestCase):
    def spoken(self, text):
        return transcript.speakable(text)

    def test_plain_prose_survives_intact(self):
        line = "Fixed the timezone dropdown, Sir."
        self.assertEqual(self.spoken(line), line)

    def test_drops_fenced_code(self):
        text = "Here is the fix:\n```python\nprint('hi')\n```\nAll done."
        out = self.spoken(text)
        self.assertNotIn("print", out)
        self.assertIn("Here is the fix", out)
        self.assertIn("All done", out)

    def test_drops_urls(self):
        out = self.spoken("Refresh http://localhost:3000/settings to confirm.")
        self.assertNotIn("localhost", out)
        self.assertNotIn("http", out)
        self.assertIn("Refresh", out)
        self.assertIn("to confirm", out)

    def test_inline_code_simple_word_is_kept_spoken(self):
        out = self.spoken("It now renders the raw `list` key.")
        self.assertIn("list", out)
        self.assertNotIn("`", out)

    def test_inline_code_command_is_dropped(self):
        out = self.spoken("I ran `npx tsc --noEmit` and it was clean.")
        self.assertNotIn("tsc", out)
        self.assertNotIn("noEmit", out)
        self.assertIn("I ran", out)
        self.assertIn("clean", out)

    def test_drops_file_paths(self):
        out = self.spoken("Fixed in src/utils/optionKeys.ts across the repo.")
        self.assertNotIn("optionKeys", out)
        self.assertNotIn("src", out)
        self.assertIn("Fixed in", out)
        self.assertIn("across the repo", out)

    def test_drops_filenames_by_extension(self):
        out = self.spoken("The cell lives in TimezonePicker.tsx now.")
        self.assertNotIn("TimezonePicker", out)
        self.assertNotIn(".tsx", out)
        self.assertIn("The cell lives in", out)

    def test_drops_bare_flags(self):
        out = self.spoken("Run it with --noEmit set.")
        self.assertNotIn("noEmit", out)

    def test_drops_host_port(self):
        out = self.spoken("It is serving on localhost:3000 right now.")
        self.assertNotIn("3000", out)
        self.assertNotIn("localhost", out)

    def test_keeps_decimal_numbers(self):
        out = self.spoken("Coverage climbed to 3.5 percent.")
        self.assertIn("3.5", out)

    def test_sentence_period_after_word_is_not_a_filename(self):
        out = self.spoken("All good, Sir. Verified across every screen.")
        self.assertIn("Sir", out)
        self.assertIn("Verified across every screen", out)

    def test_no_double_spaces_left_behind(self):
        out = self.spoken("Fixed in src/utils/optionKeys.ts today.")
        self.assertNotIn("  ", out)

    def test_empty_or_symbol_only_returns_empty(self):
        self.assertEqual(self.spoken(""), "")
        self.assertEqual(self.spoken("```\ncode only\n```"), "")


if __name__ == "__main__":
    unittest.main()
