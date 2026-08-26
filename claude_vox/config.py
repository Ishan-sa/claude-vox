"""Config loading and first-run backend detection.

Config lives at ~/.claude/vox/config.json (override with CLAUDE_VOX_HOME).
Everything is stdlib and every field has a working default, so a missing or
partial config file still produces a usable setup.
"""

import copy
import json
import os
import shutil

DEFAULTS = {
    "enabled": False,
    "marker": "\U0001f50a",
    "backend": "command",
    "max_chars": 400,
    "timeout": 8,
    "http": {
        "url": "http://127.0.0.1:5050/speak",
        # A male British voice for the Jarvis feel. Any key the server accepts
        # can live in the body; harmless if the server ignores "voice".
        "body": {"text": "{text}", "voice": "en-GB-RyanNeural"},
        "headers": {"Content-Type": "application/json"},
        # Field in the JSON reply holding a playable URL. Set to null when the
        # server returns raw audio bytes instead (e.g. OpenAI /v1/audio/speech).
        "audio_url_field": "url",
        # Servers often advertise a LAN address other devices use; play
        # from the host we actually reached instead.
        "rewrite_audio_host": True,
        "play_command": ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", "{audio}"],
    },
    "command": {
        # {text} is replaced with the spoken line.
        "argv": ["espeak-ng", "{text}"],
    },
}


def home():
    """Directory holding vox state and config."""
    override = os.environ.get("CLAUDE_VOX_HOME")
    if override:
        return override
    return os.path.join(os.path.expanduser("~"), ".claude", "vox")


def config_path():
    return os.path.join(home(), "config.json")


def merge(base, override):
    """Recursively overlay override onto base without mutating either."""
    result = copy.deepcopy(base)
    for key, value in (override or {}).items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = merge(result[key], value)
        else:
            result[key] = value
    return result


def load():
    """Return the effective config: defaults with the user's file overlaid."""
    try:
        with open(config_path(), "r", encoding="utf-8") as fh:
            user = json.load(fh)
    except (IOError, OSError, ValueError):
        user = {}
    return merge(DEFAULTS, user)


def save(cfg):
    os.makedirs(home(), exist_ok=True)
    tmp = config_path() + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    os.replace(tmp, config_path())


def set_enabled(value):
    cfg = load()
    cfg["enabled"] = bool(value)
    save(cfg)
    return cfg


def detect_backend():
    """Pick the best backend available on this machine.

    Preference order: a local TTS HTTP server if one answers, then the platform
    speech command, then any installed CLI synthesiser.
    """
    if _http_server_alive(DEFAULTS["http"]["url"]):
        return "http", None
    for argv in (["say", "{text}"],
                 ["espeak-ng", "{text}"],
                 ["espeak", "{text}"],
                 ["spd-say", "-w", "{text}"]):
        if shutil.which(argv[0]):
            return "command", argv
    return "command", None


def _http_server_alive(url):
    """True if something accepts a speech POST at url."""
    import urllib.error
    import urllib.request
    payload = json.dumps({"text": "."}).encode("utf-8")
    request = urllib.request.Request(
        url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(request, timeout=2) as response:
            return 200 <= response.status < 300
    except (urllib.error.URLError, OSError, ValueError):
        return False


def bootstrap():
    """Write a config tuned to this machine if none exists yet.

    Returns (path, created) so the installer can report what it did.
    """
    if os.path.exists(config_path()):
        return config_path(), False
    cfg = copy.deepcopy(DEFAULTS)
    backend, argv = detect_backend()
    cfg["backend"] = backend
    if argv:
        cfg["command"]["argv"] = argv
    save(cfg)
    return config_path(), True
