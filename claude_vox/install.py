"""Wire claude-vox into (and out of) Claude Code's settings.json.

Hook entries are tagged with a marker command path so uninstall can find and
remove exactly what we added, leaving any other hooks untouched.
"""

import json
import os

EVENTS = {
    "Stop": "stop",
    "UserPromptSubmit": "hush",
    "SessionStart": "session-start",
}


def settings_path(claude_dir):
    return os.path.join(claude_dir, "settings.json")


def install_dir(claude_dir):
    """Where the vox code and its state live."""
    return os.path.join(claude_dir, "vox")


def hook_command(claude_dir, subcommand):
    script = os.path.join(install_dir(claude_dir), "vox.py")
    return "python3 %s %s" % (script, subcommand)


def _is_ours(entry, claude_dir):
    script = os.path.join(install_dir(claude_dir), "vox.py")
    for hook in entry.get("hooks", []):
        if script in str(hook.get("command", "")):
            return True
    return False


def add_hooks(settings, claude_dir):
    """Return settings with vox hooks present exactly once per event."""
    settings = json.loads(json.dumps(settings or {}))  # copy, don't mutate
    hooks = settings.setdefault("hooks", {})
    for event, subcommand in EVENTS.items():
        matchers = [m for m in hooks.get(event, []) if not _is_ours(m, claude_dir)]
        matchers.append({"hooks": [{
            "type": "command",
            "command": hook_command(claude_dir, subcommand),
        }]})
        hooks[event] = matchers
    return settings


def remove_hooks(settings, claude_dir):
    """Return settings with only vox's own hook entries stripped out."""
    settings = json.loads(json.dumps(settings or {}))
    hooks = settings.get("hooks", {})
    for event in list(hooks):
        remaining = [m for m in hooks[event] if not _is_ours(m, claude_dir)]
        if remaining:
            hooks[event] = remaining
        else:
            del hooks[event]
    if not hooks:
        settings.pop("hooks", None)
    return settings


def read_settings(claude_dir):
    try:
        with open(settings_path(claude_dir), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (IOError, OSError):
        return {}
    except ValueError:
        raise SystemExit(
            "settings.json is not valid JSON - fix it before installing: %s"
            % settings_path(claude_dir))


def write_settings(claude_dir, settings):
    """Write settings atomically, keeping a one-shot backup of what was there."""
    path = settings_path(claude_dir)
    os.makedirs(claude_dir, exist_ok=True)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as src:
            existing = src.read()
        with open(path + ".vox-backup", "w", encoding="utf-8") as dst:
            dst.write(existing)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)


def main(argv):
    action = argv[0] if argv else "install"
    claude_dir = argv[1] if len(argv) > 1 else os.path.join(
        os.path.expanduser("~"), ".claude")
    settings = read_settings(claude_dir)
    if action == "install":
        write_settings(claude_dir, add_hooks(settings, claude_dir))
        from . import config
        path, created = config.bootstrap()
        print("config: %s%s" % (path, " (created)" if created else " (kept)"))
    elif action == "uninstall":
        write_settings(claude_dir, remove_hooks(settings, claude_dir))
    else:
        raise SystemExit("usage: install.py {install|uninstall} [claude_dir]")
    return 0
