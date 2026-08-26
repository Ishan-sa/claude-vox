#!/usr/bin/env bash
# Remove claude-vox's hooks, command, and code. Config is left behind unless
# --purge is passed.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CLAUDE_DIR/vox"

if [ -d "$DEST" ]; then
  python3 -c "
import sys; sys.path.insert(0, '$DEST')
from claude_vox import install; install.main(['uninstall', '$CLAUDE_DIR'])
"
fi
rm -f "$CLAUDE_DIR/commands/vox.md"
rm -rf "$DEST/claude_vox" "$DEST/backends" "$DEST/vox.py"
if [ "${1:-}" = "--purge" ]; then
  rm -rf "$DEST"
  echo "Removed claude-vox and its config."
else
  echo "Removed claude-vox. Config kept at $DEST/config.json (--purge to delete,"
  echo "which also drops the edge-tts venv and cached audio)."
fi
