#!/usr/bin/env python3
"""Entrypoint for both the Claude Code hooks and the /vox slash command."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from claude_vox.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
