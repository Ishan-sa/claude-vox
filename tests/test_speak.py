import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from claude_vox import speak  # noqa: E402

ENDPOINT = "http://127.0.0.1:5050/speak"


class RewriteHost(unittest.TestCase):
    def test_replaces_an_unreachable_lan_host_with_the_one_we_called(self):
        self.assertEqual(
            speak.rewrite_host("http://192.168.1.95:5050/audio/x.mp3", ENDPOINT),
            "http://127.0.0.1:5050/audio/x.mp3")

    def test_leaves_a_matching_host_alone(self):
        url = "http://127.0.0.1:5050/audio/x.mp3"
        self.assertEqual(speak.rewrite_host(url, ENDPOINT), url)

    def test_resolves_a_relative_reply_against_the_endpoint(self):
        self.assertEqual(speak.rewrite_host("/audio/x.mp3", ENDPOINT),
                         "http://127.0.0.1:5050/audio/x.mp3")

    def test_preserves_query_strings(self):
        self.assertEqual(
            speak.rewrite_host("http://lan.local/audio/x.mp3?token=abc", ENDPOINT),
            "http://127.0.0.1:5050/audio/x.mp3?token=abc")


class Fill(unittest.TestCase):
    def test_substitutes_text_into_every_token(self):
        self.assertEqual(speak._fill(["say", "-v", "Daniel", "{text}"], text="hi"),
                         ["say", "-v", "Daniel", "hi"])

    def test_substitutes_inside_a_shell_string(self):
        argv = speak._fill(["sh", "-c", "echo '{text}' | piper"], text="hello")
        self.assertEqual(argv[2], "echo 'hello' | piper")


class Inject(unittest.TestCase):
    def test_fills_nested_json_bodies(self):
        body = {"model": "tts", "input": "{text}", "opts": {"alt": ["{text}"]}}
        result = speak._inject(body, "spoken")
        self.assertEqual(result["input"], "spoken")
        self.assertEqual(result["opts"]["alt"], ["spoken"])
        self.assertEqual(result["model"], "tts")

    def test_leaves_non_strings_untouched(self):
        self.assertEqual(speak._inject({"speed": 1.5, "hd": True}, "x"),
                         {"speed": 1.5, "hd": True})

    def test_does_not_mutate_the_template(self):
        body = {"input": "{text}"}
        speak._inject(body, "spoken")
        self.assertEqual(body["input"], "{text}")


class Truncation(unittest.TestCase):
    def test_long_lines_are_cut_at_a_word_boundary(self):
        captured = []
        original = speak._spawn
        speak._spawn = lambda argv: captured.append(argv) or 1234
        self.addCleanup(setattr, speak, "_spawn", original)
        cfg = {"backend": "command", "max_chars": 20,
               "command": {"argv": ["echo", "{text}"]}}
        speak.speak("alpha bravo charlie delta echo foxtrot", cfg)
        spoken = captured[0][1]
        self.assertTrue(spoken.endswith("..."))
        self.assertLessEqual(len(spoken), 24)
        self.assertNotIn("charli.", spoken)  # cut on a space, not mid-word

    def test_empty_text_is_never_spoken(self):
        original = speak._spawn
        speak._spawn = lambda argv: self.fail("should not spawn")
        self.addCleanup(setattr, speak, "_spawn", original)
        self.assertFalse(speak.speak("   ", {"backend": "command",
                                             "command": {"argv": ["echo", "{text}"]}}))


if __name__ == "__main__":
    unittest.main()
