#!/usr/bin/env bash
# Install claude-vox into ~/.claude: copy the code, register the hooks,
# and drop in the /vox slash command.
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CLAUDE_DIR="${CLAUDE_CONFIG_DIR:-$HOME/.claude}"
DEST="$CLAUDE_DIR/vox"

command -v python3 >/dev/null || { echo "claude-vox needs python3 on PATH"; exit 1; }

echo "Installing claude-vox -> $DEST"
mkdir -p "$DEST" "$CLAUDE_DIR/commands"
# Preserve config.json, playing.pid, and any venv/cache a voice backend
# built; replace only the code.
rm -rf "$DEST/claude_vox" "$DEST/backends"
cp -r "$SRC/claude_vox" "$DEST/claude_vox"
cp -r "$SRC/backends" "$DEST/backends"
chmod +x "$DEST/backends"/*.sh
cp "$SRC/vox.py" "$DEST/vox.py"
chmod +x "$DEST/vox.py"
cp "$SRC/commands/vox.md" "$CLAUDE_DIR/commands/vox.md"

python3 -c "
import sys; sys.path.insert(0, '$DEST')
from claude_vox import install; install.main(['install', '$CLAUDE_DIR'])
"

echo
echo "Hooks registered in $CLAUDE_DIR/settings.json (backup: settings.json.vox-backup)"
python3 "$DEST/vox.py" status
echo
echo "Next:"
echo "  1. python3 $DEST/vox.py test     # confirm you hear it"
echo "  2. restart Claude Code, then run: /vox on"
echo
echo "For a neural voice instead of the stock one: ./setup-edge-tts.sh"
