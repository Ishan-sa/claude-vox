"""Command line entrypoint: hook handlers plus the /vox controls.

Hook subcommands read Claude Code's JSON event on stdin and always exit 0 - a
hook that fails loudly would wedge the session it is decorating.
"""

import json
import os
import random
import subprocess
import sys
import time

from . import config, speak, transcript

INSTRUCTION = (
    "Voice mode (claude-vox) is ON. End every response to the user with a "
    "final line that starts with the {marker} marker, holding one short "
    "spoken-English sentence summarising what you just did or found - this is "
    "read aloud through the speakers, so write it to be heard, not read: no "
    "code, no paths, no markdown, no lists. Example:\n"
    "{marker} Fixed the failing auth test and pushed the branch.\n"
    "Omit the line entirely when a response needs no announcement."
)

# Assistant mode wants a summary of the WHOLE turn, not just the last thing
# done - the point a colleague would say out loud - written so it survives
# being spoken, since the middle of a response is where the real news usually
# is and bookends miss it.
ASSISTANT_INSTRUCTION = (
    "Voice mode (claude-vox) is ON: your replies are read aloud. End every "
    "response with a final line beginning with the {marker} marker - one or "
    "two natural spoken-English sentences summarising the whole response, the "
    "part a colleague would want said out loud, not just the last step. Write "
    "it to be heard: no code, paths, URLs, flags, filenames, markdown, or "
    "lists. Example:\n"
    "{marker} Fixed the timezone dropdown - it was matching on the wrong "
    "key, so the saved value showed blank. Verified across every screen that uses it.\n"
    "Omit the line only for a bare acknowledgement that needs nothing spoken."
)


def _instruction_for(cfg):
    """The context to inject for the current mode, or None if none applies."""
    mode = cfg.get("speech_mode")
    marker = cfg.get("marker", transcript.DEFAULT_MARKER)
    if mode == "assistant":
        return ASSISTANT_INSTRUCTION.format(marker=marker)
    if mode == "marker":
        return INSTRUCTION.format(marker=marker)
    return None


def _event():
    """Decode the hook event Claude Code sends on stdin."""
    try:
        return json.loads(sys.stdin.read() or "{}")
    except ValueError:
        return {}


LAST_SPOKEN = "last_spoken"


def _last_spoken_path():
    return os.path.join(config.home(), LAST_SPOKEN)


def _read_last_spoken():
    try:
        with open(_last_spoken_path(), "r", encoding="utf-8") as fh:
            return fh.read().strip() or None
    except (IOError, OSError):
        return None


def _write_last_spoken(uuid):
    try:
        os.makedirs(config.home(), exist_ok=True)
        with open(_last_spoken_path(), "w", encoding="utf-8") as fh:
            fh.write(uuid or "")
    except (IOError, OSError):
        pass


def _wait_for_new(path, before, wait=20.0, interval=0.2):
    """Wait until the transcript gains an assistant message newer than `before`.

    `before` is the newest uuid at the moment the Stop hook fired. Claude Code
    writes the finished response to the transcript AFTER the hook returns, so a
    caller inside the hook never sees it - only a process that outlives the
    hook does. This waits for that write, then returns it. `before` may be None
    on the first turn of a session, in which case any first message counts.
    """
    deadline = time.monotonic() + wait
    while True:
        uuid, text = transcript.last_assistant_entry(path)
        if uuid is not None and uuid != before:
            return uuid, text
        if time.monotonic() >= deadline:
            return None, None
        time.sleep(interval)


def _wait_for_working_intro(path, before, wait=30.0, interval=0.3):
    """Wait for the line Claude says as it starts working, past `before`.

    Polls the transcript until a first text block is followed by a tool call
    (see transcript.first_working_intro). A text-only reply never starts a
    tool, so this simply times out to (None, None) and the Stop summary speaks
    instead.
    """
    deadline = time.monotonic() + wait
    while True:
        uuid, text = transcript.first_working_intro(path, before)
        if uuid is not None:
            return uuid, text
        if time.monotonic() >= deadline:
            return None, None
        time.sleep(interval)


def cmd_speak_intro(args):
    """Detached worker: speak Claude's opening line the moment work begins."""
    if not args:
        return 0
    path = args[0]
    before = args[1] if len(args) > 1 and args[1] else None
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    if cfg.get("speech_mode") != "assistant" or not cfg.get("live_intro", True):
        return 0
    uuid, text = _wait_for_working_intro(path, before)
    if not text:
        return 0
    if uuid == _read_last_spoken():
        return 0
    line = transcript.speakable(text, cfg.get("segment_chars", 280))
    if line:
        _write_last_spoken(uuid)
        speak.speak(line, cfg)
    return 0


def cmd_stop(_args):
    """Stop hook: hand speaking to a detached child that outlives the hook.

    Capturing the newest uuid now, before the finished message is flushed,
    gives the child a baseline: it speaks the next message that appears past
    that point, which is the response this hook belongs to.
    """
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    path = _event().get("transcript_path")
    if not path:
        return 0
    before, _ = transcript.last_assistant_entry(path)
    script = os.path.abspath(sys.argv[0])
    subprocess.Popen(
        [sys.executable, script, "speak-latest", path, before or ""],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True)
    return 0


def cmd_speak_latest(args):
    """Detached worker: wait for the finished response, then speak it once."""
    if not args:
        return 0
    path = args[0]
    before = args[1] if len(args) > 1 and args[1] else None
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    uuid, text = _wait_for_new(path, before)
    if text is None:
        return 0
    if uuid == _read_last_spoken():  # an overlapping worker already spoke it
        return 0
    line = transcript.spoken_from_response(
        text,
        mode=cfg.get("speech_mode", "bookends"),
        marker=cfg.get("marker", transcript.DEFAULT_MARKER),
        limit=cfg.get("segment_chars", 280))
    if line:
        _write_last_spoken(uuid)
        speak.speak(line, cfg)
    return 0

def cmd_hush(_args):
    """UserPromptSubmit hook: cut off old speech, then start listening for work.

    Two detached children may be launched, both so submitting a prompt is never
    blocked on synthesis: the optional canned opener, and - in assistant mode -
    the live-intro watcher, which waits for Claude's first working line and
    speaks it seconds in rather than at the end of the turn. The event is read
    for its transcript_path so the watcher knows which file to tail and what
    the newest message was before this turn began.
    """
    speak.stop_playback()
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    event = _event()
    script = os.path.abspath(sys.argv[0])
    if cfg.get("opener", {}).get("enabled"):
        _spawn_hook(script, "speak-opener")
    if cfg.get("speech_mode") == "assistant" and cfg.get("live_intro", True):
        path = event.get("transcript_path")
        if path:
            before, _ = transcript.last_assistant_entry(path)
            _spawn_hook(script, "speak-intro", path, before or "")
    return 0


def _spawn_hook(script, *args):
    """Launch a vox subcommand detached, so the hook returns without waiting."""
    subprocess.Popen(
        [sys.executable, script, *args],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        stdin=subprocess.DEVNULL, start_new_session=True)


def pick_opener(cfg):
    """Choose an opener phrase, or None if openers are off / unset."""
    opener = cfg.get("opener", {})
    if not opener.get("enabled"):
        return None
    phrases = opener.get("phrases") or []
    if not phrases:
        return None
    return random.choice(phrases)


def cmd_speak_opener(_args):
    """Speak a cached opener line. Invoked detached by the hush hook."""
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    phrase = pick_opener(cfg)
    if phrase:
        speak.speak(phrase, cfg, cache=True)
    return 0


def cmd_opener(args):
    """Turn the instant opener on or off, or report where it stands.

    It lives behind its own switch because it is the one part of vox that
    speaks without having anything to say -- welcome when you want to know the
    turn started, grating when you do not. Hand-editing config.json to silence
    it is a bad answer, and worse, `vox status` used to not even mention it, so
    a phrase you did not remember enabling looked like the tool misbehaving.
    """
    setting = (args[0] if args else "").lower()
    if setting in ("on", "off"):
        cfg = config.set_opener_enabled(setting == "on")
    elif setting:
        print("usage: vox opener [on|off]", file=sys.stderr)
        return 2
    else:
        cfg = config.load()
    opener = cfg.get("opener", {})
    phrases = opener.get("phrases") or []
    if not opener.get("enabled"):
        print("opener is OFF - nothing is spoken until the turn finishes.")
    elif phrases:
        print("opener is ON - one of %d phrases is spoken the moment you "
              "submit a prompt." % len(phrases))
    else:
        # Silently doing nothing would look like a broken switch.
        print("opener is ON, but no phrases are configured, so nothing will "
              "be spoken. Add your own to \"opener\": {\"phrases\": [...]} in")
        print("  %s" % config.config_path())
    return 0


def cmd_session_start(_args):
    """SessionStart hook: teach the model to write its own spoken summary line.

    Both assistant and marker mode ask the model for a marker line; the purely
    extractive modes (bookends/intro/summary) read prose as written and inject
    nothing.
    """
    cfg = config.load()
    if not cfg.get("enabled"):
        return 0
    context = _instruction_for(cfg)
    if not context:
        return 0
    json.dump({"hookSpecificOutput": {
        "hookEventName": "SessionStart",
        "additionalContext": context,
    }}, sys.stdout)
    return 0


def cmd_on(_args):
    cfg = config.set_enabled(True)
    instruction = _instruction_for(cfg)
    if instruction:
        print(instruction)
        print()
    print("claude-vox is ON - speaking mode '%s', backend '%s'."
          % (cfg.get("speech_mode"), cfg.get("backend")))
    return 0


def cmd_off(_args):
    config.set_enabled(False)
    speak.stop_playback()
    print("claude-vox is OFF. Stop appending the spoken marker line.")
    return 0


def cmd_status(_args):
    cfg = config.load()
    print("claude-vox: %s" % ("ON" if cfg.get("enabled") else "OFF"))
    print("  mode:    %s" % cfg.get("speech_mode"))
    if cfg.get("speech_mode") == "assistant":
        print("  intro:   %s (live)" % ("on" if cfg.get("live_intro", True)
                                        else "off"))
    print("  backend: %s" % cfg.get("backend"))
    if cfg.get("backend") == "http":
        print("  url:     %s" % cfg.get("http", {}).get("url"))
    else:
        print("  argv:    %s" % " ".join(cfg.get("command", {}).get("argv", [])))
    print("  opener:  %s" % ("on" if cfg.get("opener", {}).get("enabled")
                                else "off"))
    print("  marker:  %s" % cfg.get("marker"))
    print("  config:  %s" % config.config_path())
    return 0


def cmd_test(args):
    """Speak a line right now, bypassing the enabled flag."""
    text = " ".join(args) or "Voice check. Claude vox is online and speaking."
    ok = speak.speak(text, config.load())
    print("spoke: %s" % text if ok else "failed - check `vox status` and your backend")
    return 0 if ok else 1


COMMANDS = {
    "stop": cmd_stop,
    "speak-latest": cmd_speak_latest,
    "speak-intro": cmd_speak_intro,
    "hush": cmd_hush,
    "opener": cmd_opener,
    "speak-opener": cmd_speak_opener,
    "session-start": cmd_session_start,
    "on": cmd_on,
    "off": cmd_off,
    "status": cmd_status,
    "test": cmd_test,
}

HOOKS = {"stop", "speak-latest", "speak-intro", "hush", "session-start",
         "speak-opener"}


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    name = argv[0] if argv else "status"
    handler = COMMANDS.get(name)
    if handler is None:
        print("usage: vox {%s}" % "|".join(COMMANDS), file=sys.stderr)
        return 2
    try:
        return handler(argv[1:])
    except Exception as exc:  # a broken hook must not break the session
        if name in HOOKS:
            return 0
        print("vox: %s" % exc, file=sys.stderr)
        return 1
