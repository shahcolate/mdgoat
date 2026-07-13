"""Compare two markdown documents by LLM-readiness.

The headline use case: you converted the same source (a PDF, a Word doc)
with two different tools — MarkItDown vs Docling vs your own pipeline — and
want to know which output is *actually cleaner*, not just which looks nicer.
mdgoat diff scores both and shows exactly which problems each one has that
the other doesn't.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import FileReport, Finding
from .scanner import scan


def _finding_key(f: Finding) -> Tuple[str, Optional[int]]:
    """Identity of a finding for set comparison: rule + line."""
    return (f.rule_id, f.line)


@dataclass
class DiffResult:
    left: FileReport
    right: FileReport
    only_left: List[Finding] = field(default_factory=list)
    only_right: List[Finding] = field(default_factory=list)
    shared_rules: List[str] = field(default_factory=list)

    @property
    def score_delta(self) -> int:
        """Right minus left. Positive means the right document is cleaner."""
        return self.right.score - self.left.score

    @property
    def winner(self) -> Optional[str]:
        if self.right.score > self.left.score:
            return self.right.path
        if self.left.score > self.right.score:
            return self.left.path
        return None

    def to_dict(self) -> dict:
        return {
            "left": {"path": self.left.path, "score": self.left.score, "grade": self.left.grade,
                     "tokens": self.left.token_estimate},
            "right": {"path": self.right.path, "score": self.right.score, "grade": self.right.grade,
                      "tokens": self.right.token_estimate},
            "score_delta": self.score_delta,
            "winner": self.winner,
            "only_left": [f.to_dict() for f in self.only_left],
            "only_right": [f.to_dict() for f in self.only_right],
            "shared_rules": self.shared_rules,
        }


def diff_reports(left: FileReport, right: FileReport) -> DiffResult:
    left_keys: Dict[Tuple[str, Optional[int]], Finding] = {
        _finding_key(f): f for f in left.findings
    }
    right_keys: Dict[Tuple[str, Optional[int]], Finding] = {
        _finding_key(f): f for f in right.findings
    }
    left_rules = {f.rule_id for f in left.findings}
    right_rules = {f.rule_id for f in right.findings}

    only_left = [f for k, f in left_keys.items() if k not in right_keys]
    only_right = [f for k, f in right_keys.items() if k not in left_keys]
    only_left.sort(key=lambda f: (-int(f.severity), f.line or 0, f.rule_id))
    only_right.sort(key=lambda f: (-int(f.severity), f.line or 0, f.rule_id))

    return DiffResult(
        left=left,
        right=right,
        only_left=only_left,
        only_right=only_right,
        shared_rules=sorted(left_rules & right_rules),
    )


def diff_text(left_text: str, left_path: str, right_text: str, right_path: str) -> DiffResult:
    return diff_reports(
        scan(left_text, path=left_path),
        scan(right_text, path=right_path),
    )
