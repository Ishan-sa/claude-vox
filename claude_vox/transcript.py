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


def last_assistant_entry(path):
    """Return (uuid, text) for the most recent main-agent assistant text block.

    The uuid says which response the text belongs to, so a caller can tell a
    freshly written entry from one it has already handled. Sidechain entries
    are subagent output and are deliberately ignored - only what the user
    actually sees on screen should be spoken.
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
                    return entry.get("uuid"), text
    return None, None


def last_assistant_text(path):
    """Return the most recent main-agent assistant text block, or None."""
    return last_assistant_entry(path)[1]


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


_BULLET = re.compile(r"^\s*([-*+]|\d+[.)]|#{1,6}\s)")
_SENTENCE_END = re.compile(r"[.!?](?:\s|$)")


def prose_paragraphs(text):
    """Return the response's prose paragraphs, dropping code and structure.

    Fenced code blocks, bullet/numbered lists, and one-line headers ("Where
    things stand:") are removed, so what's left is the sentences a person would
    actually read aloud - the opening remark and the closing thought.
    """
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    out = []
    for block in re.split(r"\n\s*\n", text):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        if not lines:
            continue
        if all(_BULLET.match(ln) for ln in lines):      # a list block
            continue
        if len(lines) == 1 and lines[0].rstrip().endswith(":"):  # a header
            continue
        cleaned = clean(block)
        if cleaned:
            out.append(cleaned)
    return out


def cap(text, limit):
    """Trim text to limit characters, preferring a sentence then word boundary."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    window = text[:limit]
    ends = list(_SENTENCE_END.finditer(window))
    if ends and ends[-1].end() > limit * 0.4:
        return window[:ends[-1].end()].strip()
    return window.rsplit(" ", 1)[0].strip() + "..."


def natural_segments(text, limit=280):
    """(intro, summary): the first and last prose paragraphs, each capped."""
    paras = prose_paragraphs(text)
    if not paras:
        return None, None
    return cap(paras[0], limit), cap(paras[-1], limit)


def spoken_from_response(text, mode="bookends", marker=DEFAULT_MARKER, limit=280):
    """Decide what to speak from one response.

    An explicit marker line always wins - it is the model deliberately choosing
    the spoken words. Otherwise the mode selects from the natural prose:
    "intro", "summary", or "bookends" (intro then summary, read as one line).
    """
    marked = extract_marked_line(text, marker)
    if marked:
        return marked
    if mode == "marker":
        return None
    intro, summary = natural_segments(text, limit)
    if mode == "intro":
        return intro
    if mode == "summary":
        return summary
    # bookends
    if intro and summary and intro != summary:
        return intro + " ... " + summary
    return intro or summary


def spoken_line(path, marker=DEFAULT_MARKER):
    """Marker-only pipeline (kept for callers that want just the marker line)."""
    text = last_assistant_text(path)
    if text is None:
        return None
    return extract_marked_line(text, marker)


def spoken_text(path, mode="bookends", marker=DEFAULT_MARKER, limit=280):
    """Full pipeline: transcript path -> text to speak for the given mode."""
    text = last_assistant_text(path)
    if text is None:
        return None
    return spoken_from_response(text, mode, marker, limit)
