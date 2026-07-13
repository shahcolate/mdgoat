"""Structure detectors: markdown that no longer parses the way it looks.

Broken tables, unclosed fences, and mangled heading hierarchies are the
most common casualties of automated conversion — and the most damaging to
chunking and retrieval, because structure is exactly what markdown was
supposed to preserve.
"""

from __future__ import annotations

import re
from typing import Iterable, List, Optional, Tuple

from ..models import CATEGORY_STRUCTURE, Document, Finding, Severity

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_TABLE_SEP_RE = re.compile(r"^\s*\|?[\s:|-]+\|[\s:|-]*$")
_FENCE_RE = re.compile(r"^\s{0,3}(```+|~~~+)")


def _split_cells(row: str) -> List[str]:
    body = row.strip()
    if body.startswith("|"):
        body = body[1:]
    if body.endswith("|") and not body.endswith("\\|"):
        body = body[:-1]
    cells = re.split(r"(?<!\\)\|", body)
    return [c.strip() for c in cells]


# ---------------------------------------------------------------------------
# STR001 — broken tables
# ---------------------------------------------------------------------------


def detect_broken_tables(doc: Document) -> Iterable[Finding]:
    findings = []
    i = 0
    lines = doc.lines
    while i < len(lines) - 1:
        if doc.in_fence(i + 1) or "|" not in lines[i]:
            i += 1
            continue
        if not _TABLE_SEP_RE.match(lines[i + 1]) or "|" not in lines[i + 1]:
            i += 1
            continue
        header_cols = len(_split_cells(lines[i]))
        sep_cols = len(_split_cells(lines[i + 1]))
        start_line = i + 1
        bad_rows: List[Tuple[int, int]] = []
        j = i + 2
        while j < len(lines) and "|" in lines[j] and lines[j].strip():
            cols = len(_split_cells(lines[j]))
            if cols != header_cols:
                bad_rows.append((j + 1, cols))
            j += 1
        if sep_cols != header_cols:
            bad_rows.insert(0, (start_line + 1, sep_cols))
        if bad_rows:
            first_bad = bad_rows[0][0]
            findings.append(
                Finding(
                    rule_id="STR001",
                    rule_name="broken-table",
                    category=CATEGORY_STRUCTURE,
                    severity=Severity.MEDIUM,
                    message=(
                        "Table starting at line %d has %d row(s) whose column "
                        "count differs from the header (%d columns). The model "
                        "sees misaligned cells, not a table."
                        % (start_line, len(bad_rows), header_cols)
                    ),
                    line=first_bad,
                    column=1,
                    snippet=lines[first_bad - 1].strip()[:60],
                    count=len(bad_rows),
                    fixable=False,
                )
            )
        i = j
    return findings


# ---------------------------------------------------------------------------
# STR002 — unclosed code fence
# ---------------------------------------------------------------------------


def detect_unclosed_fence(doc: Document) -> Iterable[Finding]:
    open_line: Optional[int] = None
    open_marker = ""
    for i, line in enumerate(doc.lines):
        m = _FENCE_RE.match(line)
        if not m:
            continue
        marker = m.group(1)[:3]
        if open_line is None:
            open_line = i + 1
            open_marker = marker
        elif marker == open_marker:
            open_line = None
    if open_line is None:
        return []
    return [
        Finding(
            rule_id="STR002",
            rule_name="unclosed-code-fence",
            category=CATEGORY_STRUCTURE,
            severity=Severity.HIGH,
            message=(
                "Code fence opened at line %d is never closed — everything "
                "after it is silently treated as code." % open_line
            ),
            line=open_line,
            column=1,
            snippet=doc.lines[open_line - 1].strip()[:60],
            fixable=False,
        )
    ]


# ---------------------------------------------------------------------------
# STR003 — heading hierarchy jumps
# ---------------------------------------------------------------------------


def detect_heading_jumps(doc: Document) -> Iterable[Finding]:
    findings = []
    prev_level = 0
    for i, line in enumerate(doc.lines):
        if doc.in_fence(i + 1):
            continue
        m = _HEADING_RE.match(line)
        if not m:
            continue
        level = len(m.group(1))
        if prev_level and level > prev_level + 1:
            findings.append(
                Finding(
                    rule_id="STR003",
                    rule_name="heading-level-jump",
                    category=CATEGORY_STRUCTURE,
                    severity=Severity.LOW,
                    message=(
                        "Heading jumps from level %d to %d — hierarchy-aware "
                        "chunkers will misplace this section."
                        % (prev_level, level)
                    ),
                    line=i + 1,
                    column=1,
                    snippet=line.strip()[:60],
                    fixable=False,
                )
            )
        prev_level = level
    return findings


# ---------------------------------------------------------------------------
# STR004 — empty links and images
# ---------------------------------------------------------------------------

_EMPTY_LINK_RE = re.compile(r"!?\[\s*\]\(\s*\)|\[[^\]]+\]\(\s*\)")


def detect_empty_links(doc: Document) -> Iterable[Finding]:
    hits = []
    for m in _EMPTY_LINK_RE.finditer(doc.text):
        line, _ = doc.location(m.start())
        if not doc.in_fence(line):
            hits.append(m.start())
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="STR004",
            rule_name="empty-links",
            category=CATEGORY_STRUCTURE,
            severity=Severity.LOW,
            message=(
                "%d empty link(s)/image(s) — the conversion lost the target."
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
# STR005 — no headings in a long document
# ---------------------------------------------------------------------------


def detect_headingless_document(doc: Document) -> Iterable[Finding]:
    if len(doc.text) < 4000:
        return []
    for i, line in enumerate(doc.lines):
        if not doc.in_fence(i + 1) and _HEADING_RE.match(line):
            return []
    return [
        Finding(
            rule_id="STR005",
            rule_name="headingless-document",
            category=CATEGORY_STRUCTURE,
            severity=Severity.LOW,
            message=(
                "%d characters with no headings at all — the document arrived "
                "as one undifferentiated wall of text, which defeats "
                "structure-aware chunking." % len(doc.text)
            ),
            line=1,
            column=1,
            fixable=False,
        )
    ]


DETECTORS = [
    detect_broken_tables,
    detect_unclosed_fence,
    detect_heading_jumps,
    detect_empty_links,
    detect_headingless_document,
]
