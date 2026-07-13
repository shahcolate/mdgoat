"""Core data types shared across mdgoat."""

from __future__ import annotations

import bisect
from dataclasses import dataclass, field
from enum import IntEnum
from typing import List, Optional, Tuple


class Severity(IntEnum):
    """How much a finding should worry you."""

    INFO = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name

    @classmethod
    def from_name(cls, name: str) -> "Severity":
        try:
            return cls[name.strip().upper()]
        except KeyError:
            raise ValueError(
                "unknown severity %r (expected one of %s)"
                % (name, ", ".join(s.name.lower() for s in cls))
            )


# Categories group rules for reporting.
CATEGORY_SECURITY = "security"
CATEGORY_ARTIFACT = "artifact"
CATEGORY_STRUCTURE = "structure"
CATEGORY_EFFICIENCY = "efficiency"


@dataclass
class Finding:
    """A single issue discovered in a document.

    Char-level issues (e.g. invisible characters) are aggregated into one
    finding per rule with ``count`` set to the number of occurrences and
    ``line``/``column`` pointing at the first one.
    """

    rule_id: str
    rule_name: str
    category: str
    severity: Severity
    message: str
    line: Optional[int] = None
    column: Optional[int] = None
    snippet: Optional[str] = None
    count: int = 1
    fixable: bool = False

    def to_dict(self) -> dict:
        return {
            "rule_id": self.rule_id,
            "rule_name": self.rule_name,
            "category": self.category,
            "severity": self.severity.label,
            "message": self.message,
            "line": self.line,
            "column": self.column,
            "snippet": self.snippet,
            "count": self.count,
            "fixable": self.fixable,
        }


class Document:
    """A markdown document plus cheap positional lookups."""

    def __init__(self, text: str, path: str = "<text>"):
        self.text = text
        self.path = path
        self.lines = text.split("\n")
        starts = [0]
        for line in self.lines[:-1]:
            starts.append(starts[-1] + len(line) + 1)
        self._line_starts = starts
        self.fenced_lines = _fenced_line_mask(self.lines)

    def location(self, index: int) -> Tuple[int, int]:
        """Return 1-based (line, column) for a character offset."""
        index = max(0, min(index, len(self.text)))
        li = bisect.bisect_right(self._line_starts, index) - 1
        return li + 1, index - self._line_starts[li] + 1

    def in_fence(self, line_number: int) -> bool:
        """True if the 1-based line number falls inside a code fence."""
        idx = line_number - 1
        if 0 <= idx < len(self.fenced_lines):
            return self.fenced_lines[idx]
        return False

    def snippet_at(self, index: int, width: int = 60) -> str:
        line_no, _ = self.location(index)
        line = self.lines[line_no - 1]
        stripped = line.strip()
        if len(stripped) > width:
            stripped = stripped[: width - 1] + "…"
        return stripped


def _fenced_line_mask(lines: List[str]) -> List[bool]:
    """Mark lines that are inside (or delimit) a fenced code block."""
    mask = [False] * len(lines)
    open_marker: Optional[str] = None
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if open_marker is None:
            for marker in ("```", "~~~"):
                if stripped.startswith(marker):
                    open_marker = marker
                    mask[i] = True
                    break
        else:
            mask[i] = True
            if stripped.startswith(open_marker) and stripped.rstrip("`~ ") == "":
                open_marker = None
    return mask


@dataclass
class FileReport:
    """The result of scanning one document."""

    path: str
    findings: List[Finding] = field(default_factory=list)
    score: int = 100
    grade: str = "A+"
    token_estimate: int = 0
    char_count: int = 0
    line_count: int = 0

    @property
    def worst_severity(self) -> Optional[Severity]:
        if not self.findings:
            return None
        return max(f.severity for f in self.findings)

    def counts_by_severity(self) -> dict:
        counts = {s.label: 0 for s in reversed(list(Severity))}
        for f in self.findings:
            counts[f.severity.label] += 1
        return counts

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "score": self.score,
            "grade": self.grade,
            "token_estimate": self.token_estimate,
            "char_count": self.char_count,
            "line_count": self.line_count,
            "counts": self.counts_by_severity(),
            "findings": [f.to_dict() for f in self.findings],
        }


def estimate_tokens(text: str) -> int:
    """Rough LLM token estimate (no tokenizer dependency, ~±15%).

    Blends the two classic heuristics: ~4 characters per token and
    ~0.75 words per token.
    """
    if not text:
        return 0
    chars = len(text)
    words = len(text.split())
    return int(round((chars / 4.0 + words / 0.75) / 2.0))
