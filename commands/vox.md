---
description: Toggle spoken responses (claude-vox) - on, off, status, test, or opener
allowed-tools: Bash(python3:*)
---

!`python3 "${CLAUDE_PLUGIN_ROOT:-${CLAUDE_CONFIG_DIR:-$HOME/.claude}/vox}/vox.py" ${ARGUMENTS:-status}`

The line above is claude-vox's own status output. Relay it to me in one short
sentence. Do NOT change how you write your responses -- claude-vox reads your
normal prose automatically. Only if it explicitly printed a marker instruction
(that happens in "marker" mode) should you follow it.
