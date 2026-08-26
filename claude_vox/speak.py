"""Turn a line of text into sound, and stop it again on demand.

Two backends cover the field:

  command - hand the text to a CLI synthesiser (say, espeak-ng, piper, ...)
  http    - POST to a TTS server, then play what it returns

Playback runs detached and its pid is recorded so the hush hook can cut it off
the moment the user types again.
"""

import json
import os
import signal
import subprocess
import tempfile

from . import config

PID_FILE = "playing.pid"


def _pid_path():
    return os.path.join(config.home(), PID_FILE)


def _record(pid):
    os.makedirs(config.home(), exist_ok=True)
    with open(_pid_path(), "w", encoding="utf-8") as fh:
        fh.write(str(pid))


def stop_playback():
    """Kill any speech still playing. Returns True if something was stopped."""
    path = _pid_path()
    try:
        with open(path, "r", encoding="utf-8") as fh:
            pid = int(fh.read().strip())
    except (IOError, OSError, ValueError):
        return False
    stopped = False
    try:
        # Playback is started in its own process group so helpers spawned by
        # the player die with it.
        os.killpg(os.getpgid(pid), signal.SIGTERM)
        stopped = True
    except (OSError, ProcessLookupError):
        pass
    try:
        os.remove(path)
    except OSError:
        pass
    return stopped


def _spawn(argv):
    """Start argv detached, in its own process group, silenced."""
    with open(os.devnull, "wb") as devnull:
        process = subprocess.Popen(
            argv, stdout=devnull, stderr=devnull, stdin=subprocess.DEVNULL,
            start_new_session=True)
    _record(process.pid)
    return process.pid


def _fill(template, **values):
    """Substitute {placeholders} through a list of argv tokens."""
    filled = []
    for token in template:
        for key, value in values.items():
            token = token.replace("{" + key + "}", value)
        filled.append(token)
    return filled


def speak(text, cfg=None, cache=False):
    """Speak text using the configured backend.

    When cache is True the synthesised audio is kept and replayed on the next
    identical line - used for the short, repeated opener phrases so they play
    the instant a prompt is submitted instead of waiting on synthesis.

    Returns True if playback started. Every failure is reported as False rather
    than raised - a hook must never break the session over a missing speaker.
    """
    cfg = cfg or config.load()
    text = (text or "").strip()
    if not text:
        return False
    limit = int(cfg.get("max_chars") or 0)
    if limit and len(text) > limit:
        text = text[:limit].rsplit(" ", 1)[0] + "..."

    stop_playback()  # a new line replaces the old one rather than overlapping
    try:
        if cfg.get("backend") == "http":
            return _speak_http(text, cfg, cache)
        return _speak_command(text, cfg)
    except Exception:
        return False


def _speak_command(text, cfg):
    argv = cfg.get("command", {}).get("argv") or []
    if not argv:
        return False
    _spawn(_fill(argv, text=text))
    return True


def _speak_http(text, cfg, cache=False):
    import urllib.request

    http = cfg.get("http", {})
    if cache:
        cached = cache_path(text, cfg)
        if os.path.exists(cached):
            play = http.get("play_command")
            if play:
                _spawn(_fill(play, audio=cached))
                return True
    body = json.dumps(_inject(http.get("body", {}), text)).encode("utf-8")
    request = urllib.request.Request(
        http["url"], data=body, headers=http.get("headers", {}))
    with urllib.request.urlopen(request, timeout=cfg.get("timeout", 8)) as response:
        payload = response.read()

    field = http.get("audio_url_field")
    if field:
        url = json.loads(payload.decode("utf-8"))[field]
        if http.get("rewrite_audio_host", True):
            url = rewrite_host(url, http["url"])
        # Fetch rather than hand the URL to the player: players like ffplay
        # exit 0 on a failed fetch, so downloading here is the only way a
        # broken audio URL becomes a real error instead of silence.
        with urllib.request.urlopen(url, timeout=cfg.get("timeout", 8)) as audio_response:
            payload = audio_response.read()
    if not payload:
        return False
    if cache:
        audio = cache_path(text, cfg)
        os.makedirs(os.path.dirname(audio), exist_ok=True)
        with open(audio, "wb") as fh:
            fh.write(payload)
    else:
        handle, audio = tempfile.mkstemp(prefix="vox-", suffix=".mp3")
        with os.fdopen(handle, "wb") as fh:
            fh.write(payload)
        _sweep_temp()

    play = http.get("play_command")
    if not play:
        return False
    _spawn(_fill(play, audio=audio))
    return True


def cache_path(text, cfg):
    """Stable on-disk path for the audio of text under the current voice.

    Keyed on text and the request body (which carries the voice) so changing
    the voice re-renders rather than replaying the old one.
    """
    import hashlib
    voice_key = json.dumps(cfg.get("http", {}).get("body", {}), sort_keys=True)
    digest = hashlib.sha1((voice_key + "\x00" + text).encode("utf-8")).hexdigest()
    return os.path.join(config.home(), "openers", digest + ".mp3")


def rewrite_host(url, endpoint):
    """Point url at the same host we successfully reached at endpoint.

    TTS servers often advertise a LAN address for other devices on the network
    (a smart speaker, a phone) that the machine running Claude Code cannot
    route to. The path is what identifies the audio, so keep it and borrow the
    host we know works.
    """
    from urllib.parse import urljoin, urlsplit, urlunsplit
    target, source = urlsplit(url), urlsplit(endpoint)
    if not target.netloc:
        # A relative reply is already relative to the endpoint we called.
        return urljoin(endpoint, url)
    if target.netloc == source.netloc:
        return url
    return urlunsplit((source.scheme or target.scheme, source.netloc,
                       target.path, target.query, target.fragment))


def _sweep_temp(max_age=3600):
    """Delete stale vox audio files so the temp dir does not grow forever."""
    import time
    now = time.time()
    directory = tempfile.gettempdir()
    try:
        names = os.listdir(directory)
    except OSError:
        return
    for name in names:
        if not (name.startswith("vox-") and name.endswith(".mp3")):
            continue
        path = os.path.join(directory, name)
        try:
            if now - os.path.getmtime(path) > max_age:
                os.remove(path)
        except OSError:
            pass


def _inject(body, text):
    """Deep-copy a JSON body template, replacing {text} in every string."""
    if isinstance(body, dict):
        return {k: _inject(v, text) for k, v in body.items()}
    if isinstance(body, list):
        return [_inject(v, text) for v in body]
    if isinstance(body, str):
        return body.replace("{text}", text)
    return body
