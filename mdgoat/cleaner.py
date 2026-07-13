"""Deterministic cleanup: fix everything that is safe to fix without an LLM.

The cleaner never touches the *meaning* of a document. It removes smuggling
channels, repairs conversion damage with known-correct mappings, and
normalizes whitespace/punctuation. Anything judgement-shaped (broken
tables, boilerplate) is reported by the scanner but left alone here.

Character-level fixes apply everywhere, including code fences (invisible
characters in a code block still reach the model). Prose-level fixes
(comment stripping, de-hyphenation, punctuation, entity decoding) skip
fenced code, which must be preserved byte-for-byte.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from .detectors.artifacts import HYPHEN_BREAK_RE, LIGATURES
from .detectors.efficiency import SMART_PUNCTUATION
from .models import estimate_tokens

# --- character-level tables -------------------------------------------------

_TAG_BLOCK_RE = re.compile("[\U000E0000-\U000E007F]")
_INVISIBLE_RE = re.compile("[\u200b\u200c\u2060\u00ad\u034f\u180e\ufeff]")
# ZWJ / variation selectors only when NOT adjacent to an emoji (emoji safety).
# Every branch requires an ASCII neighbor on the emoji-facing side, so a
# selector that is part of a real emoji sequence (e.g. the VS16 in "\u2764\ufe0f") is
# never stripped, including when it sits at the very start or end of the text.
_ZWJ_ASCII_RE = re.compile(
    "(?<=[\x00-\x7f])[\u200d\ufe00-\ufe0f](?=[\x00-\x7f])"
    "|\\A[\u200d\ufe00-\ufe0f](?=[\x00-\x7f])"
    "|(?<=[\x00-\x7f])[\u200d\ufe00-\ufe0f]\\Z"
)
_BIDI_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")
_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0e-\x1f\x7f\x80-\x9f]")
_ODD_SPACE_RE = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")

# cp1252 codepoints for bytes 0x80-0x9F, used to reverse mojibake.
_CP1252_HIGH = {
    0x20AC: 0x80, 0x201A: 0x82, 0x0192: 0x83, 0x201E: 0x84, 0x2026: 0x85,
    0x2020: 0x86, 0x2021: 0x87, 0x02C6: 0x88, 0x2030: 0x89, 0x0160: 0x8A,
    0x2039: 0x8B, 0x0152: 0x8C, 0x017D: 0x8E, 0x2018: 0x91, 0x2019: 0x92,
    0x201C: 0x93, 0x201D: 0x94, 0x2022: 0x95, 0x2013: 0x96, 0x2014: 0x97,
    0x02DC: 0x98, 0x2122: 0x99, 0x0161: 0x9A, 0x203A: 0x9B, 0x0153: 0x9C,
    0x017E: 0x9E, 0x0178: 0x9F,
}

# UTF-8 lead bytes for Latin/general-punctuation text decoded as cp1252:
# 0xC2, 0xC3 (two-byte sequences) and 0xE2 (three-byte punctuation).
_MOJIBAKE_PAIR_RE = re.compile(
    "[\u00c2\u00c3\u00e2]["
    + "\u0080-\u00ff"
    + re.escape("".join(chr(cp) for cp in _CP1252_HIGH))
    + "]{1,3}"
)

_COMMENT_RE = re.compile(r"[ \t]*<!--.*?-->", re.DOTALL)

_ENTITIES = {
    "&nbsp;": " ",
    "&amp;": "&",
    "&quot;": '"',
    "&apos;": "'",
    "&#39;": "'",
    "&rsquo;": "'",
    "&lsquo;": "'",
    "&rdquo;": '"',
    "&ldquo;": '"',
    "&mdash;": " - ",
    "&ndash;": "-",
    "&hellip;": "...",
    "&bull;": "-",
}


@dataclass
class CleanResult:
    text: str
    changes: Dict[str, int] = field(default_factory=dict)
    tokens_before: int = 0
    tokens_after: int = 0

    @property
    def total_changes(self) -> int:
        return sum(self.changes.values())

    @property
    def tokens_saved(self) -> int:
        return max(0, self.tokens_before - self.tokens_after)

    def to_dict(self) -> dict:
        return {
            "changes": self.changes,
            "total_changes": self.total_changes,
            "tokens_before": self.tokens_before,
            "tokens_after": self.tokens_after,
            "tokens_saved": self.tokens_saved,
        }


def _to_bytes_via_cp1252(chunk: str):
    out = bytearray()
    for ch in chunk:
        cp = ord(ch)
        if cp <= 0xFF:
            out.append(cp)
        elif cp in _CP1252_HIGH:
            out.append(_CP1252_HIGH[cp])
        else:
            return None
    return bytes(out)


def _fix_mojibake(text: str) -> Tuple[str, int]:
    count = 0

    def repair(m: "re.Match") -> str:
        nonlocal count
        raw = _to_bytes_via_cp1252(m.group())
        if raw is None:
            return m.group()
        # Greedy matching may grab a trailing lead-byte that belongs to the
        # next (or no) sequence; shrink until the bytes decode cleanly.
        for end in range(len(raw), 1, -1):
            try:
                fixed = raw[:end].decode("utf-8")
            except UnicodeDecodeError:
                continue
            count += 1
            return fixed + m.group()[end:]
        return m.group()

    # Repair repeatedly: doubly-encoded text resolves one layer per pass.
    for _ in range(3):
        new = _MOJIBAKE_PAIR_RE.sub(repair, text)
        if new == text:
            break
        text = new
    return text, count


def _segments(text: str):
    """Yield (is_fenced, chunk) pairs whose concatenation is the input."""
    lines = text.split("\n")
    buf: List[str] = []
    fenced = False
    open_marker = ""
    for line in lines:
        stripped = line.lstrip()
        if not fenced and (stripped.startswith("```") or stripped.startswith("~~~")):
            if buf:
                yield False, "\n".join(buf) + "\n"
                buf = []
            fenced = True
            open_marker = stripped[:3]
            buf.append(line)
        elif fenced:
            buf.append(line)
            if stripped.startswith(open_marker) and stripped.rstrip("`~ ") == "":
                yield True, "\n".join(buf) + "\n"
                buf = []
                fenced = False
        else:
            buf.append(line)
    if buf:
        yield fenced, "\n".join(buf)


def _apply(text, regex, replacement, changes, key):
    new, n = regex.subn(replacement, text)
    if n:
        changes[key] = changes.get(key, 0) + n
    return new


def clean(
    text: str,
    strip_comments: bool = True,
    normalize_punctuation: bool = True,
) -> CleanResult:
    """Clean markdown text; returns the fixed text plus a change ledger."""
    changes: Dict[str, int] = {}
    tokens_before = estimate_tokens(text)

    # 0. line endings
    if "\r" in text:
        n = text.count("\r")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
        changes["line-endings"] = n

    # 1. mojibake repair FIRST, before control stripping. C1 control bytes
    # (0x80-0x9F) are the third byte of many mojibake sequences (e.g. the
    # closing curly quote U+201D -> "\xe2\x80\x9d"); stripping them first
    # would leave the sequence unrepairable.
    text, n = _fix_mojibake(text)
    if n:
        changes["mojibake"] = n

    # 2. character-level security fixes (everywhere, including fences)
    text = _apply(text, _TAG_BLOCK_RE, "", changes, "unicode-tag-smuggling")
    text = _apply(text, _INVISIBLE_RE, "", changes, "invisible-characters")
    text = _apply(text, _ZWJ_ASCII_RE, "", changes, "invisible-characters")
    text = _apply(text, _BIDI_RE, "", changes, "bidi-controls")
    text = _apply(text, _CONTROL_RE, "", changes, "control-characters")

    # 3. ligatures (everywhere)
    for lig, expansion in LIGATURES.items():
        if lig in text:
            changes["ligatures"] = changes.get("ligatures", 0) + text.count(lig)
            text = text.replace(lig, expansion)

    # 4. odd spaces -> regular space (everywhere)
    text = _apply(text, _ODD_SPACE_RE, " ", changes, "non-standard-spaces")

    # 5. prose-level fixes, skipping fenced code
    out_parts: List[str] = []
    for fenced, chunk in _segments(text):
        if fenced:
            out_parts.append(chunk)
            continue
        if strip_comments:
            chunk = _apply(chunk, _COMMENT_RE, "", changes, "html-comments")
        chunk, n = HYPHEN_BREAK_RE.subn(r"\1\2", chunk)
        if n:
            changes["hyphenation-breaks"] = changes.get("hyphenation-breaks", 0) + n
        for entity, plain in _ENTITIES.items():
            if entity in chunk:
                changes["html-entities"] = changes.get("html-entities", 0) + chunk.count(entity)
                chunk = chunk.replace(entity, plain)
        if normalize_punctuation:
            for smart, plain in SMART_PUNCTUATION.items():
                if smart in chunk:
                    changes["typographic-punctuation"] = (
                        changes.get("typographic-punctuation", 0) + chunk.count(smart)
                    )
                    chunk = chunk.replace(smart, plain)
        out_parts.append(chunk)
    text = "".join(out_parts)

    # 6. whitespace hygiene: strip trailing spaces first so blank-ish lines
    # become truly blank, then collapse 2+ blank lines to one.
    text = _apply(text, re.compile(r"[ \t]+$", re.MULTILINE), "", changes, "trailing-whitespace")
    text = _apply(text, re.compile(r"\n{3,}"), "\n\n", changes, "excessive-blank-lines")

    # 7. exactly one trailing newline
    if text and not text.endswith("\n"):
        text += "\n"
    while text.endswith("\n\n"):
        text = text[:-1]

    return CleanResult(
        text=text,
        changes=changes,
        tokens_before=tokens_before,
        tokens_after=estimate_tokens(text),
    )
