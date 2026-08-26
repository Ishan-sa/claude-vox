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


def first_working_intro(path, before=None):
    """(uuid, text) of the line Claude says as it starts working.

    In a working turn the transcript reads: a text block ("I'll dig into the
    dropdown.") followed by a separate tool_use entry. That first text block,
    once a tool call confirms work has begun, is what we speak live. Only
    entries after `before` (the newest uuid when the turn started) count, so a
    caller can poll: (None, None) means either no text yet or no tool call yet,
    both of which just mean "keep waiting". A text-only reply never produces a
    tool call, so it correctly yields no live intro - the Stop summary covers
    it instead.
    """
    passed = before is None
    candidate = None
    for entry in iter_entries(path):
        if entry.get("type") != "assistant" or entry.get("isSidechain"):
            continue
        uuid = entry.get("uuid")
        if not passed:
            if uuid == before:
                passed = True
            continue
        content = entry.get("message", {}).get("content")
        if not isinstance(content, list):
            continue
        kinds = [b.get("type") for b in content if isinstance(b, dict)]
        if candidate is None:
            for block in content:
                if block.get("type") == "text" and (block.get("text") or "").strip():
                    candidate = (uuid, block["text"].strip())
                    break
        if candidate and "tool_use" in kinds:
            return candidate
    return None, None


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

# --- speakable(): keep spoken lines from reading like a terminal -------------
#
# A summary read aloud must never spell out `npx tsc --noEmit`, a file path, or
# localhost:3000 - it sounds like a robot dictating a screen. These strip the
# few token shapes that are unmistakably code, and deliberately leave ordinary
# prose (and plain decimals like 3.5) untouched. The model's own marker line is
# usually already clean; this is the safety net, and it also grooms the live
# intro, which is Claude's real first sentence.
_FENCED = re.compile(r"```.*?```", re.S)
_URLISH = re.compile(r"\b\w+://\S+|\bwww\.\S+", re.I)
_INLINE_CODE = re.compile(r"`+([^`]*)`+")
_PLAIN_WORD = re.compile(r"^[A-Za-z]+(?:['-][A-Za-z]+)*$")
_FLAG = re.compile(r"^-{1,2}[A-Za-z][\w-]*$")
_HOST_PORT = re.compile(r"^[\w.-]+:\d+")
_IP = re.compile(r"^\d{1,3}(?:\.\d{1,3}){3}\b")
_FILE_EXT = re.compile(
    r"\.(?:ts|tsx|js|jsx|mjs|cjs|py|rb|go|rs|java|c|cc|cpp|h|hpp|cs|php|swift|kt"
    r"|json|ya?ml|toml|ini|cfg|conf|env|md|rst|txt|csv|tsv|log|sh|bash|zsh|fish"
    r"|sql|html?|xml|css|scss|less|mp3|wav|ogg|flac|png|jpe?g|gif|svg|pdf|zip"
    r"|tar|gz)$", re.I)
_STRIP_EDGES = "\"'`.,;:!?()[]{}<>"


def _is_techy_token(token):
    """True when a bare word is code, not speech: a path, flag, host, filename."""
    if "/" in token or "\\" in token:
        return True
    core = token.strip(_STRIP_EDGES)
    if not core:
        return False
    return bool(_FLAG.match(core) or _HOST_PORT.match(core)
                or _IP.match(core) or _FILE_EXT.search(core))


def speakable(text, limit=None):
    """Rewrite a line so it reads aloud as speech, not as a screen dump.

    Fenced code, links, code-shaped inline spans, paths, flags, hosts and
    filenames are removed; plain prose and ordinary numbers are left alone.
    Optionally capped to `limit` characters at a sentence boundary.
    """
    if not text:
        return ""
    text = _FENCED.sub(" ", text)
    text = _URLISH.sub(" ", text)
    # An inline span is spoken only when it is a single ordinary word ("list");
    # anything command- or path-shaped is dropped rather than read out.
    text = _INLINE_CODE.sub(
        lambda m: m.group(1) if _PLAIN_WORD.match(m.group(1).strip()) else " ",
        text)
    kept = [tok for tok in text.split() if not _is_techy_token(tok)]
    text = clean(" ".join(kept))
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)   # no space before punctuation
    text = re.sub(r"\s{2,}", " ", text).strip()
    if limit:
        text = cap(text, limit)
    return text


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
    if mode == "assistant":
        # The model writes its own spoken summary on the marker line; groom it
        # for the ear. With no marker line, fall back to the closing prose so a
        # response is never left unspoken.
        if marked:
            return speakable(marked, limit)
        _, summary = natural_segments(text, limit)
        return speakable(summary, limit) if summary else None
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
