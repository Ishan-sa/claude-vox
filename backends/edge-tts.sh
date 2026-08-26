#!/bin/sh
# claude-vox command backend: speak through a Microsoft Edge neural voice.
#
#   edge-tts.sh [--prewarm] <voice> <text>
#
# Wire it into config.json as the command backend:
#
#   { "backend": "command",
#     "command": { "argv": ["~/.claude/vox/backends/edge-tts.sh",
#                           "en-GB-RyanNeural", "{text}"] } }
#
# Why a script rather than calling edge-tts directly from argv: edge-tts writes
# a file, it does not play one, so something has to synthesise, play, and clean
# up. Doing that here keeps the config a single line and lets short, repeated
# lines -- the openers -- be cached and replayed with no network round-trip.
#
# Three behaviours worth knowing about:
#
#   Caching   Lines of CACHE_MAX_CHARS or fewer are stored under the vox home
#             keyed by voice, prosody and text, so an opener is synthesised
#             once and thereafter plays instantly. Longer lines are spoken once
#             and never repeat, so they go to a temp file that is deleted after
#             playback.
#   Fallback  If synthesis fails for any reason -- offline, Microsoft down, the
#             venv removed -- it speaks through the local offline voice instead
#             of going silent. A speech tool that says nothing when the network
#             blips is worse than one that sounds worse.
#   Exit 0    Never wedge the session. Callers ignore the status anyway, but a
#             non-zero exit here would show up in hook debugging as noise.
set -u

PREWARM=0
if [ "${1:-}" = "--prewarm" ]; then
    PREWARM=1
    shift
fi

VOICE="${1:-en-GB-RyanNeural}"
TEXT="${2:-}"
# Whitespace-only is not silence to `[ -n ]`, but it is to a listener -- and a
# blank line would otherwise cost a network round-trip to synthesise nothing.
[ -n "$(printf '%s' "$TEXT" | tr -d '[:space:]')" ] || exit 0

# Mirrors config.home() in claude_vox/config.py -- keep the two in step.
VOX_HOME="${CLAUDE_VOX_HOME:-$HOME/.claude/vox}"
CACHE_DIR="$VOX_HOME/cache"

# Prosody. A touch slower and lower than default reads as composed rather than
# chirpy, which is what you want from something talking over your shoulder.
RATE="${VOX_RATE:--4%}"
PITCH="${VOX_PITCH:--4Hz}"

CACHE_MAX_CHARS="${VOX_CACHE_MAX_CHARS:-120}"
CACHE_KEEP="${VOX_CACHE_KEEP:-200}"

# --- locating the pieces ----------------------------------------------------

find_edge() {
    # The venv setup-edge-tts.sh builds wins, so a global edge-tts of a
    # different vintage cannot quietly change the voice.
    if [ -x "$VOX_HOME/venv/bin/edge-tts" ]; then
        echo "$VOX_HOME/venv/bin/edge-tts"
        return 0
    fi
    command -v edge-tts 2>/dev/null
}

find_player() {
    # afplay is macOS built-in; the rest cover the common Linux installs.
    for p in afplay mpv ffplay mpg123 cvlc; do
        if command -v "$p" >/dev/null 2>&1; then
            echo "$p"
            return 0
        fi
    done
    return 1
}

play() {  # play <file>
    case "$PLAYER" in
        afplay) afplay "$1" ;;
        mpv)    mpv --no-video --really-quiet "$1" ;;
        ffplay) ffplay -nodisp -autoexit -loglevel quiet "$1" ;;
        mpg123) mpg123 -q "$1" ;;
        cvlc)   cvlc --play-and-exit --quiet "$1" ;;
    esac
}

sha1() {
    if command -v shasum >/dev/null 2>&1; then
        shasum -a 1 | cut -d' ' -f1
    elif command -v sha1sum >/dev/null 2>&1; then
        sha1sum | cut -d' ' -f1
    else
        # No hasher: skip caching rather than fail. Callers treat an empty key
        # as "do not cache".
        echo ""
    fi
}

# The offline safety net, in the order most likely to exist per platform.
speak_offline() {
    [ "$PREWARM" -eq 1 ] && exit 0   # nothing to warm if we cannot synthesise
    if command -v say >/dev/null 2>&1; then
        say -v "${VOX_FALLBACK_VOICE:-Daniel}" "$TEXT" 2>/dev/null \
            || say "$TEXT" 2>/dev/null
    elif command -v espeak-ng >/dev/null 2>&1; then
        espeak-ng "$TEXT" 2>/dev/null
    elif command -v espeak >/dev/null 2>&1; then
        espeak "$TEXT" 2>/dev/null
    elif command -v spd-say >/dev/null 2>&1; then
        spd-say -w "$TEXT" 2>/dev/null
    fi
    exit 0
}

EDGE="$(find_edge || true)"
[ -n "$EDGE" ] && [ -x "$EDGE" ] || speak_offline
PLAYER="$(find_player || true)"
[ -n "$PLAYER" ] || speak_offline

# --- synthesis --------------------------------------------------------------

synth() {  # synth <outfile>
    # NOTE: --rate=-4% must be one argv token. Written as `--rate -4%` argparse
    # reads the value as another flag and edge-tts exits with a usage error,
    # which a hook would swallow into silence. Keep the equals sign.
    "$EDGE" --voice "$VOICE" --rate="$RATE" --pitch="$PITCH" \
            --text "$TEXT" --write-media "$1" >/dev/null 2>&1 \
        && [ -s "$1" ]
}

prune_cache() {
    # Bounded, not clever: openers rotate through a fixed set, but /vox test
    # lines and short responses land here too and would otherwise accumulate
    # forever. Only runs after a miss, so cache hits stay a single afplay.
    count=$(ls -1 "$CACHE_DIR" 2>/dev/null | wc -l | tr -d ' ')
    [ "$count" -gt "$CACHE_KEEP" ] || return 0
    ls -1t "$CACHE_DIR" 2>/dev/null | tail -n +"$((CACHE_KEEP + 1))" | while IFS= read -r stale; do
        rm -f "$CACHE_DIR/$stale"
    done
}

key=""
if [ "${#TEXT}" -le "$CACHE_MAX_CHARS" ]; then
    key=$(printf '%s\n%s\n%s\n%s' "$VOICE" "$RATE" "$PITCH" "$TEXT" | sha1)
fi

if [ -n "$key" ]; then
    mkdir -p "$CACHE_DIR" 2>/dev/null || true
    audio="$CACHE_DIR/$key.mp3"
    if [ ! -s "$audio" ]; then
        # Synthesise to a partial file and rename, so a killed run never leaves
        # a truncated mp3 that would be treated as a valid cache hit forever.
        synth "$audio.part" || { rm -f "$audio.part"; speak_offline; }
        mv "$audio.part" "$audio"
        prune_cache
    fi
    [ "$PREWARM" -eq 1 ] && exit 0
    play "$audio"
    exit 0
fi

[ "$PREWARM" -eq 1 ] && exit 0

# Sweep first: the hush hook kills this whole process group mid-sentence when
# you type again, so the cleanup at the bottom is not guaranteed to run and
# temp files would otherwise pile up. Mirrors _sweep_temp() in speak.py.
find "${TMPDIR:-/tmp}" -maxdepth 1 -name 'vox-*' -type f -mmin +60 -delete 2>/dev/null || true

# mktemp reserves the name atomically; the player wants the .mp3 extension, so
# rename into it rather than appending and orphaning what mktemp just created.
reserved="$(mktemp "${TMPDIR:-/tmp}/vox-XXXXXX")"
audio="$reserved.mp3"
mv "$reserved" "$audio"
synth "$audio" || { rm -f "$audio"; speak_offline; }
play "$audio"
rm -f "$audio"
exit 0
