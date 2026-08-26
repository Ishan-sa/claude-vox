---
description: Toggle spoken responses (claude-vox) - on, off, status, or test
allowed-tools: Bash(python3:*)
---

!`python3 "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/vox/vox.py" ${ARGUMENTS:-status}`

The output above is from claude-vox. If it says voice mode is ON, follow the
marker instruction it printed for the rest of this session. If it says OFF,
stop appending the spoken marker line. Acknowledge in one short sentence.
