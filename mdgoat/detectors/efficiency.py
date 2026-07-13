"""Efficiency detectors: tokens you are paying for and getting nothing from."""

from __future__ import annotations

import re
from collections import Counter
from typing import Iterable

from ..models import CATEGORY_EFFICIENCY, Document, Finding, Severity

# ---------------------------------------------------------------------------
# EFF001 — trailing whitespace
# ---------------------------------------------------------------------------


def detect_trailing_whitespace(doc: Document) -> Iterable[Finding]:
    hits = [
        i + 1
        for i, line in enumerate(doc.lines)
        if line != line.rstrip() and not doc.in_fence(i + 1)
    ]
    if not hits:
        return []
    return [
        Finding(
            rule_id="EFF001",
            rule_name="trailing-whitespace",
            category=CATEGORY_EFFICIENCY,
            severity=Severity.INFO,
            message="%d line(s) with trailing whitespace." % len(hits),
            line=hits[0],
            column=1,
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# EFF002 — excessive blank lines
# ---------------------------------------------------------------------------

_BLANK_RUN_RE = re.compile(r"\n[ \t]*\n[ \t]*\n(?:[ \t]*\n)*")


def detect_blank_runs(doc: Document) -> Iterable[Finding]:
    hits = []
    for m in _BLANK_RUN_RE.finditer(doc.text):
        line, _ = doc.location(m.start())
        if not doc.in_fence(line + 1):
            hits.append(m.start())
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="EFF002",
            rule_name="excessive-blank-lines",
            category=CATEGORY_EFFICIENCY,
            severity=Severity.LOW,
            message=(
                "%d run(s) of 2+ consecutive blank lines — pure token waste."
                % len(hits)
            ),
            line=line,
            column=col,
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# EFF003 — duplicated blocks
# ---------------------------------------------------------------------------


def detect_duplicate_blocks(doc: Document) -> Iterable[Finding]:
    blocks = Counter()
    first_seen = {}
    offset_line = 1
    for block in doc.text.split("\n\n"):
        normalized = " ".join(block.split())
        n_lines = block.count("\n") + 2
        if len(normalized) >= 120 and not doc.in_fence(offset_line):
            blocks[normalized] += 1
            first_seen.setdefault(normalized, offset_line)
        offset_line += n_lines
    dups = [(b, n) for b, n in blocks.items() if n >= 2]
    if not dups:
        return []
    worst, n = max(dups, key=lambda x: x[1])
    preview = worst[:60] + ("…" if len(worst) > 60 else "")
    return [
        Finding(
            rule_id="EFF003",
            rule_name="duplicate-blocks",
            category=CATEGORY_EFFICIENCY,
            severity=Severity.LOW,
            message=(
                "%d paragraph(s) appear more than once (e.g. %r repeated %d "
                "times) — duplicated context skews retrieval and costs tokens."
                % (len(dups), preview, n)
            ),
            line=first_seen[worst],
            column=1,
            count=len(dups),
            fixable=False,
        )
    ]


# ---------------------------------------------------------------------------
# EFF004 — normalizable typographic punctuation
# ---------------------------------------------------------------------------

SMART_PUNCTUATION = {
    "‘": "'",
    "’": "'",
    "“": '"',
    "”": '"',
    "–": "-",
    "—": " - ",
    "…": "...",
    "´": "'",
    "ʼ": "'",
}

_SMART_RE = re.compile("[‘’“”–—…´ʼ]")


def detect_smart_punctuation(doc: Document) -> Iterable[Finding]:
    hits = []
    for m in _SMART_RE.finditer(doc.text):
        line, _ = doc.location(m.start())
        if not doc.in_fence(line):
            hits.append(m.start())
    if len(hits) < 10:
        return []  # a few curly quotes are style, not damage
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="EFF004",
            rule_name="typographic-punctuation",
            category=CATEGORY_EFFICIENCY,
            severity=Severity.INFO,
            message=(
                "%d typographic quote/dash/ellipsis character(s) that can be "
                "normalized to ASCII equivalents for cheaper, more consistent "
                "tokenization." % len(hits)
            ),
            line=line,
            column=col,
            count=len(hits),
            fixable=True,
        )
    ]


DETECTORS = [
    detect_trailing_whitespace,
    detect_blank_runs,
    detect_duplicate_blocks,
    detect_smart_punctuation,
]
