import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import install  # noqa: E402

CLAUDE_DIR = "/home/someone/.claude"


def other_hook():
    return {"matcher": "Bash", "hooks": [{"type": "command", "command": "audit.sh"}]}


class AddHooks(unittest.TestCase):
    def test_registers_all_three_events(self):
        result = install.add_hooks({}, CLAUDE_DIR)
        self.assertEqual(set(result["hooks"]), set(install.EVENTS))

    def test_preserves_unrelated_settings_and_hooks(self):
        settings = {"model": "opus", "hooks": {"PreToolUse": [other_hook()]}}
        result = install.add_hooks(settings, CLAUDE_DIR)
        self.assertEqual(result["model"], "opus")
        self.assertIn(other_hook(), result["hooks"]["PreToolUse"])

    def test_keeps_foreign_hooks_on_an_event_we_also_use(self):
        settings = {"hooks": {"Stop": [other_hook()]}}
        result = install.add_hooks(settings, CLAUDE_DIR)
        self.assertEqual(len(result["hooks"]["Stop"]), 2)
        self.assertIn(other_hook(), result["hooks"]["Stop"])

    def test_reinstalling_does_not_duplicate_entries(self):
        once = install.add_hooks({}, CLAUDE_DIR)
        twice = install.add_hooks(once, CLAUDE_DIR)
        self.assertEqual(len(twice["hooks"]["Stop"]), 1)
        self.assertEqual(once, twice)

    def test_does_not_mutate_the_input(self):
        settings = {"hooks": {}}
        install.add_hooks(settings, CLAUDE_DIR)
        self.assertEqual(settings, {"hooks": {}})


class RemoveHooks(unittest.TestCase):
    def test_removes_only_our_entries(self):
        settings = install.add_hooks({"hooks": {"Stop": [other_hook()]}}, CLAUDE_DIR)
        result = install.remove_hooks(settings, CLAUDE_DIR)
        self.assertEqual(result["hooks"]["Stop"], [other_hook()])
        self.assertNotIn("UserPromptSubmit", result["hooks"])

    def test_drops_the_hooks_key_when_nothing_is_left(self):
        settings = install.add_hooks({"model": "opus"}, CLAUDE_DIR)
        result = install.remove_hooks(settings, CLAUDE_DIR)
        self.assertNotIn("hooks", result)
        self.assertEqual(result["model"], "opus")

    def test_uninstall_after_install_restores_the_original(self):
        original = {"model": "opus", "hooks": {"PreToolUse": [other_hook()]}}
        roundtrip = install.remove_hooks(
            install.add_hooks(original, CLAUDE_DIR), CLAUDE_DIR)
        self.assertEqual(roundtrip, original)


if __name__ == "__main__":
    unittest.main()
