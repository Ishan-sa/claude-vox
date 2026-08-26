#!/usr/bin/env bash
# Switch claude-vox to a neural voice using Microsoft Edge's TTS.
#
#   ./setup-edge-tts.sh [voice] [--opener]
#
# The stock `say` / `espeak-ng` voices are intelligible but plainly synthetic.
# edge-tts reaches Microsoft's neural voices, needs no API key or account, and
# is the one dependency in this project -- installed into its own venv under
# the vox home so it cannot collide with anything on your system Python.
#
# Run this after ./install.sh.
set -euo pipefail

VOICE="en-GB-RyanNeural"
ENABLE_OPENER=0
for arg in "$@"; do
  case "$arg" in
    --opener) ENABLE_OPENER=1 ;;
    -*)       echo "unknown flag: $arg" >&2; exit 2 ;;
    *)        VOICE="$arg" ;;
  esac
done

NL=$'\n'
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="${CLAUDE_VOX_HOME:-$CLAUDE_DIR/vox}"
BACKEND="$DEST/backends/edge-tts.sh"

command -v python3 >/dev/null || { echo "needs python3 on PATH"; exit 1; }
[ -f "$DEST/vox.py" ] || { echo "run ./install.sh first"; exit 1; }

if [ ! -x "$BACKEND" ]; then
  SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
  mkdir -p "$DEST/backends"
  cp "$SRC/backends/edge-tts.sh" "$BACKEND"
  chmod +x "$BACKEND"
fi

echo "Installing edge-tts into $DEST/venv"
python3 -m venv "$DEST/venv"
"$DEST/venv/bin/pip" install --quiet --upgrade pip
"$DEST/venv/bin/pip" install --quiet edge-tts
echo "  $("$DEST/venv/bin/edge-tts" --version 2>&1 | tail -1)"

# Checked without a pipe on purpose: `--list-voices | grep -q` looks correct
# and is not, because grep exits at the first match, edge-tts dies of SIGPIPE,
# and `set -o pipefail` reports the whole pipeline as failed -- so every valid
# voice gets flagged as invalid. An empty list means we are offline, which is
# not evidence the voice is wrong, so say nothing.
VOICES="$("$DEST/venv/bin/edge-tts" --list-voices 2>/dev/null || true)"
if [ -n "$VOICES" ] && [[ "$NL$VOICES" != *"$NL$VOICE "* ]]; then
  echo
  echo "warning: '$VOICE' is not in the voice list. Browse them with:"
  echo "  $DEST/venv/bin/edge-tts --list-voices"
fi

python3 - "$DEST" "$BACKEND" "$VOICE" "$ENABLE_OPENER" <<'PY'
import sys
sys.path.insert(0, sys.argv[1])
from claude_vox import config

backend, voice, enable_opener = sys.argv[2], sys.argv[3], sys.argv[4] == "1"
cfg = config.load()
cfg["backend"] = "command"
cfg["command"]["argv"] = [backend, voice, "{text}"]
if enable_opener:
    cfg.setdefault("opener", {})["enabled"] = True
config.save(cfg)
print("config: %s" % config.config_path())
print("  voice: %s" % voice)
print("  opener: %s" % ("on" if cfg.get("opener", {}).get("enabled") else "off"))
PY

# Pre-render the openers so the very first prompt is acknowledged instantly
# instead of paying a network round-trip mid-hook.
python3 - "$DEST" "$BACKEND" "$VOICE" <<'PY'
import subprocess
import sys
sys.path.insert(0, sys.argv[1])
from claude_vox import config

backend, voice = sys.argv[2], sys.argv[3]
cfg = config.load()
opener = cfg.get("opener", {})
if not opener.get("enabled"):
    sys.exit(0)
phrases = opener.get("phrases") or []
print("Pre-rendering %d opener phrase(s):" % len(phrases))
for phrase in phrases:
    subprocess.call([backend, "--prewarm", voice, phrase])
    print("  %s" % phrase)
PY

echo
python3 "$DEST/vox.py" status
echo
echo "Next:"
echo "  1. python3 $DEST/vox.py test     # confirm you hear the neural voice"
echo "  2. restart Claude Code, then run: /vox on"
