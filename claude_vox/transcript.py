"""Pull the spoken line out of a Claude Code transcript.

Claude Code hands a Stop hook the path to a JSONL transcript. Each line is one
entry; assistant entries look like:

    {"type": "assistant", "isSidechain": false,
     "message": {"role": "assistant", "content": [{"type": "text", "text": "..."}]}}

We want the most recent text block written by the main agent, then the marker
line inside it.
"""

import json
import re

DEFAULT_MARKER = "\U0001f50a"  # speaker emoji


def iter_entries(path):
    """Yield decoded JSONL entries, skipping blank and malformed lines.

    A half-written final line is normal when the hook fires, so a bad line is
    skipped rather than raised.
    """
    with open(path, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except ValueError:
                continue


def last_assistant_text(path):
    """Return the most recent main-agent assistant text block, or None.

    Sidechain entries are subagent output and are deliberately ignored - only
    what the user actually sees on screen should be spoken.
    """
    entries = [e for e in iter_entries(path)
               if e.get("type") == "assistant" and not e.get("isSidechain")]
    for entry in reversed(entries):
        content = entry.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        for block in reversed(content):
            if block.get("type") == "text":
                text = (block.get("text") or "").strip()
                if text:
                    return text
    return None


def extract_marked_line(text, marker=DEFAULT_MARKER):
    """Return the spoken text from the last marker line, or None if unmarked.

    The marker may sit anywhere on the line (bare, bolded, quoted) so the whole
    prefix up to and including it is dropped. Returning None is the normal
    "stay silent" path, not an error.
    """
    if not text or not marker:
        return None
    spoken = None
    for line in text.splitlines():
        if marker in line:
            spoken = line.split(marker, 1)[1]
    if spoken is None:
        return None
    spoken = clean(spoken)
    return spoken or None


_MD_PATTERNS = [
    (re.compile(r"`{1,3}([^`]*)`{1,3}"), r"\1"),        # code spans
    (re.compile(r"\*\*([^*]+)\*\*"), r"\1"),            # bold
    (re.compile(r"(?<!\w)\*([^*]+)\*(?!\w)"), r"\1"),   # italics
    (re.compile(r"\[([^\]]+)\]\([^)]*\)"), r"\1"),      # links -> label
    (re.compile(r"\*+"), " "),                         # unpaired emphasis marks
    (re.compile(r"[_~#>]+"), " "),                      # stray markdown chrome
    (re.compile(r"\s+"), " "),
]


def clean(text):
    """Strip markdown so the voice reads prose, not punctuation."""
    for pattern, repl in _MD_PATTERNS:
        text = pattern.sub(repl, text)
    return text.strip(" -:\t")


def spoken_line(path, marker=DEFAULT_MARKER):
    """Full pipeline: transcript path -> text to speak, or None to stay silent."""
    text = last_assistant_text(path)
    if text is None:
        return None
    return extract_marked_line(text, marker)
