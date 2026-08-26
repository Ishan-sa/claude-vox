import json
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import install  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def load_json(*parts):
    with open(os.path.join(REPO, *parts), encoding="utf-8") as fh:
        return json.load(fh)


class PluginManifest(unittest.TestCase):
    def test_plugin_json_names_the_plugin(self):
        self.assertEqual(load_json(".claude-plugin", "plugin.json")["name"],
                         "claude-vox")

    def test_marketplace_lists_the_plugin(self):
        mp = load_json(".claude-plugin", "marketplace.json")
        self.assertIn("claude-vox", [p["name"] for p in mp["plugins"]])

    def test_marketplace_entries_have_a_source(self):
        mp = load_json(".claude-plugin", "marketplace.json")
        for plugin in mp["plugins"]:
            self.assertTrue(plugin.get("source"), plugin.get("name"))


class PluginHooks(unittest.TestCase):
    def setUp(self):
        self.hooks = load_json("hooks", "hooks.json")["hooks"]

    def _commands(self, event):
        return [h["command"]
                for matcher in self.hooks.get(event, [])
                for h in matcher["hooks"]]

    def test_declares_exactly_the_events_the_clone_install_uses(self):
        # If a hook event is added or renamed for one install path, the other
        # must not silently drift.
        self.assertEqual(set(self.hooks), set(install.EVENTS))

    def test_each_event_runs_its_matching_subcommand(self):
        for event, subcommand in install.EVENTS.items():
            commands = self._commands(event)
            self.assertTrue(
                any(c.endswith("vox.py " + subcommand) for c in commands),
                "%s should run '%s'" % (event, subcommand))

    def test_hooks_locate_vox_through_the_plugin_root(self):
        for event in install.EVENTS:
            for command in self._commands(event):
                self.assertIn("${CLAUDE_PLUGIN_ROOT}", command)


if __name__ == "__main__":
    unittest.main()
