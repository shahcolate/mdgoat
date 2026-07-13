"""Artifact detectors: the damage document conversion leaves behind.

PDF extractors, OCR, and copy-paste pipelines leave fingerprints — mojibake,
ligatures, hyphenation breaks, repeated page furniture — that waste tokens
and quietly corrupt retrieval quality.

Non-ASCII characters that are invisible or ambiguous are written as escape
sequences; visible mojibake byte-sequences are spelled out for clarity.
"""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable, List

from ..models import CATEGORY_ARTIFACT, Document, Finding, Severity

# ---------------------------------------------------------------------------
# ART001 — mojibake (UTF-8 read as Latin-1/cp1252)
# ---------------------------------------------------------------------------

MOJIBAKE_RE = re.compile(
    "\u00e2\u20ac."          # "a-hat euro" trigraphs: curly quotes, dashes, ellipsis
    "|\u00c3[\u0080-\u00ff]"  # accented-letter pairs
    "|\u00c2[\u00a0-\u00bf]"  # stray C2-prefix pairs
)


def detect_mojibake(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in MOJIBAKE_RE.finditer(doc.text)]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART001",
            rule_name="mojibake",
            category=CATEGORY_ARTIFACT,
            severity=Severity.MEDIUM,
            message=(
                "%d mojibake sequence(s) (UTF-8 text decoded as Latin-1, "
                "e.g. â€™ instead of an apostrophe). Garbles "
                "meaning and wastes tokens." % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# ART002 — typographic ligatures (OCR fingerprint)
# ---------------------------------------------------------------------------

LIGATURES = {
    "ﬀ": "ff",
    "ﬁ": "fi",
    "ﬂ": "fl",
    "ﬃ": "ffi",
    "ﬄ": "ffl",
    "ﬅ": "st",
    "ﬆ": "st",
}

_LIGATURE_RE = re.compile("[\ufb00-\ufb06]")


def detect_ligatures(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in _LIGATURE_RE.finditer(doc.text)]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART002",
            rule_name="ligatures",
            category=CATEGORY_ARTIFACT,
            severity=Severity.LOW,
            message=(
                "%d typographic ligature(s) (ﬁ, ﬂ, ...) — a PDF/OCR "
                "fingerprint that breaks exact-match search and tokenization."
                % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# ART003 — non-standard spaces
# ---------------------------------------------------------------------------

_ODD_SPACE_RE = re.compile("[\u00a0\u2000-\u200a\u202f\u205f\u3000]")


def detect_odd_spaces(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in _ODD_SPACE_RE.finditer(doc.text)]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART003",
            rule_name="non-standard-spaces",
            category=CATEGORY_ARTIFACT,
            severity=Severity.LOW,
            message=(
                "%d non-breaking/typographic space(s). Visually identical to "
                "a space, but a different token to the model." % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# ART004 — control characters
# ---------------------------------------------------------------------------

_CONTROL_RE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\x80-\x9f]")


def detect_control_chars(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in _CONTROL_RE.finditer(doc.text)]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART004",
            rule_name="control-characters",
            category=CATEGORY_ARTIFACT,
            severity=Severity.HIGH,
            message=(
                "%d control character(s) (form feeds, C1 bytes, ...). A sure "
                "sign of a broken extraction pipeline." % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# ART005 — hyphenation line breaks
# ---------------------------------------------------------------------------

HYPHEN_BREAK_RE = re.compile(r"([A-Za-z]{2,})-\n([a-z]{2,})")


def detect_hyphenation_breaks(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in HYPHEN_BREAK_RE.finditer(doc.text)]
    hits = [h for h in hits if not doc.in_fence(doc.location(h)[0])]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART005",
            rule_name="hyphenation-breaks",
            category=CATEGORY_ARTIFACT,
            severity=Severity.LOW,
            message=(
                "%d probable hyphenation line-break(s) (words split like "
                "'conver-' / 'sion' across lines by PDF layout)." % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# ART006 — replacement characters (data already lost)
# ---------------------------------------------------------------------------


def detect_replacement_chars(doc: Document) -> Iterable[Finding]:
    hits = [i for i, ch in enumerate(doc.text) if ch == "�"]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="ART006",
            rule_name="replacement-characters",
            category=CATEGORY_ARTIFACT,
            severity=Severity.MEDIUM,
            message=(
                "%d U+FFFD replacement character(s) — bytes were destroyed "
                "during conversion and cannot be recovered automatically."
                % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=False,
        )
    ]


# ---------------------------------------------------------------------------
# ART007 — repeated boilerplate lines (page headers/footers)
# ---------------------------------------------------------------------------


def detect_boilerplate(doc: Document) -> Iterable[Finding]:
    counter: Counter = Counter()
    first_seen = {}
    for i, raw in enumerate(doc.lines):
        if doc.in_fence(i + 1):
            continue
        line = raw.strip()
        if len(line) < 20 or line.startswith(("#", "|", "-", "*", ">", "```")):
            continue
        counter[line] += 1
        first_seen.setdefault(line, i + 1)
    findings = []
    for line, n in counter.most_common(3):
        if n < 3:
            break
        preview = line if len(line) <= 60 else line[:59] + "…"
        findings.append(
            Finding(
                rule_id="ART007",
                rule_name="repeated-boilerplate",
                category=CATEGORY_ARTIFACT,
                severity=Severity.MEDIUM,
                message=(
                    "Line repeated %d times (%r) — looks like a page "
                    "header/footer that survived conversion, polluting every "
                    "retrieval chunk it lands in." % (n, preview)
                ),
                line=first_seen[line],
                column=1,
                snippet=preview,
                count=n,
                fixable=False,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# ART008 — orphaned page numbers
# ---------------------------------------------------------------------------

_PAGE_NUM_RE = re.compile(r"^\s*(?:page\s+)?\d{1,4}(?:\s+of\s+\d{1,4})?\s*$", re.I)


def detect_page_numbers(doc: Document) -> Iterable[Finding]:
    hits: List[int] = []
    for i, line in enumerate(doc.lines):
        if doc.in_fence(i + 1):
            continue
        if _PAGE_NUM_RE.match(line) and line.strip():
            # Only count when surrounded by blank lines: a stranded artifact,
            # not list content.
            prev_blank = i == 0 or not doc.lines[i - 1].strip()
            next_blank = i == len(doc.lines) - 1 or not doc.lines[i + 1].strip()
            if prev_blank and next_blank:
                hits.append(i + 1)
    if len(hits) < 2:
        return []
    return [
        Finding(
            rule_id="ART008",
            rule_name="orphaned-page-numbers",
            category=CATEGORY_ARTIFACT,
            severity=Severity.LOW,
            message=(
                "%d stranded page-number line(s) — pagination artifacts from "
                "the source document." % len(hits)
            ),
            line=hits[0],
            column=1,
            snippet=doc.lines[hits[0] - 1].strip(),
            count=len(hits),
            fixable=False,
        )
    ]


# ---------------------------------------------------------------------------
# ART009 — HTML residue
# ---------------------------------------------------------------------------

_ENTITY_RE = re.compile(r"&(?:nbsp|amp|quot|apos|lt|gt|mdash|ndash|hellip|rsquo|lsquo|rdquo|ldquo|#\d{1,6});")
_TAG_HTML_RE = re.compile(r"</?(?:div|span|font|center|p|table|tbody|tr|td|th)\b[^>]*>", re.I)


def detect_html_residue(doc: Document) -> Iterable[Finding]:
    entity_hits = []
    tag_hits = []
    for regex, bucket in ((_ENTITY_RE, entity_hits), (_TAG_HTML_RE, tag_hits)):
        for m in regex.finditer(doc.text):
            line, _ = doc.location(m.start())
            if not doc.in_fence(line):
                bucket.append(m.start())
    total = len(entity_hits) + len(tag_hits)
    if total < 5:
        return []
    first = min(entity_hits + tag_hits)
    line, col = doc.location(first)
    return [
        Finding(
            rule_id="ART009",
            rule_name="html-residue",
            category=CATEGORY_ARTIFACT,
            severity=Severity.MEDIUM if total >= 20 else Severity.LOW,
            message=(
                "%d HTML leftover(s) (%d entities, %d structural tags) that "
                "should have become markdown." % (total, len(entity_hits), len(tag_hits))
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(first),
            count=total,
            fixable=True,
        )
    ]


DETECTORS = [
    detect_mojibake,
    detect_ligatures,
    detect_odd_spaces,
    detect_control_chars,
    detect_hyphenation_breaks,
    detect_replacement_chars,
    detect_boilerplate,
    detect_page_numbers,
    detect_html_residue,
]
