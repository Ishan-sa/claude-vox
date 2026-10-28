"""Is the voice you hear the voice you chose?

edge-tts.sh falls back to the offline OS voice rather than go silent, which is
right for one line and wrong for weeks: a Homebrew Python upgrade once deleted
the interpreter the venv was built on, and every line after that came out in
the fallback voice with nothing saying why. These checks turn that into a
warning at session start and in `vox status`, and `vox repair` fixes it.
"""

import os
import shutil
import subprocess
import sys

from . import config

# Written by edge-tts.sh as "<epoch> <reason>" whenever it falls back, and
# removed on the next successful synthesis -- keep the name in step with it.
FALLBACK_FILE = "last_fallback"


def uses_edge(cfg):
    """True if the configured backend is the edge-tts script."""
    if cfg.get("backend") != "command":
        return False
    argv = cfg.get("command", {}).get("argv") or []
    return bool(argv) and os.path.basename(argv[0]) == "edge-tts.sh"


def voice_name(cfg):
    argv = cfg.get("command", {}).get("argv") or []
    return argv[1] if len(argv) > 2 else "neural"


def venv_dir():
    return os.path.join(config.home(), "venv")


def venv_problem():
    """Why the edge-tts venv cannot synthesise, or None if it can."""
    venv = venv_dir()
    if not os.path.isdir(venv):
        # edge-tts.sh also accepts one on PATH, so only a missing venv with
        # nothing to stand in for it is a problem.
        if shutil.which("edge-tts"):
            return None
        return "edge-tts is not installed"
    python = os.path.join(venv, "bin", "python3")
    # exists() follows symlinks, so a venv whose interpreter was deleted out
    # from under it reads as missing here -- the Homebrew-upgrade case.
    if not os.path.exists(python):
        return ("the Python its venv was built on is gone, usually after a "
                "Homebrew Python upgrade")
    try:
        result = subprocess.run(
            [python, "-c", "import edge_tts"], stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return "the Python in its venv will not run"
    if result.returncode != 0:
        return "edge-tts is missing from its venv"
    return None


def last_fallback():
    """The reason the most recent line fell back to the offline voice, or None."""
    try:
        with open(os.path.join(config.home(), FALLBACK_FILE),
                  "r", encoding="utf-8") as fh:
            line = fh.read().strip()
    except (IOError, OSError):
        return None
    _, _, reason = line.partition(" ")
    return reason or "unknown reason"


def problem(cfg):
    """One sentence on why speech is not in the chosen voice, or None."""
    if not uses_edge(cfg):
        return None
    broken = venv_problem()
    if broken:
        return broken
    fell_back = last_fallback()
    if fell_back:
        return "the last line fell back to the offline voice (%s)" % fell_back
    return None


def warning(cfg):
    """A user-facing warning for the current problem, or None."""
    reason = problem(cfg)
    if not reason:
        return None
    return ("claude-vox: the %s voice is not working -- %s -- so speech is "
            "coming out in the backup voice. Run /vox repair to fix it."
            % (voice_name(cfg), reason))


def repair(out=sys.stdout):
    """Rebuild the edge-tts venv on the Python running this. True on success."""
    venv = venv_dir()
    print("Rebuilding %s on %s" % (venv, sys.executable), file=out)
    try:
        subprocess.check_call([sys.executable, "-m", "venv", "--clear", venv])
        subprocess.check_call(
            [os.path.join(venv, "bin", "python3"), "-m", "pip", "install",
             "--quiet", "--upgrade", "pip", "edge-tts"])
    except (OSError, subprocess.CalledProcessError) as exc:
        print("repair failed: %s" % exc, file=out)
        return False
    try:
        os.remove(os.path.join(config.home(), FALLBACK_FILE))
    except OSError:
        pass
    broken = venv_problem()
    if broken:
        print("still broken: %s" % broken, file=out)
        return False
    return True
