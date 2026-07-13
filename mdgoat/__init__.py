"""mdgoat — the markdown quality gate for the AI input layer.

Goats eat anything. Your LLM shouldn't.

mdgoat scans markdown for hidden prompt-injection payloads, document
conversion artifacts, and structural damage; scores it for LLM-readiness;
and auto-fixes everything that is safe to fix deterministically.

Public API:

    >>> import mdgoat
    >>> report = mdgoat.scan("# Hello​ world")
    >>> report.score, report.grade
    (98, 'A+')
    >>> result = mdgoat.clean("# Hello​ world")
    >>> result.text
    '# Hello world\\n'
"""

from __future__ import annotations

from .models import Document, Finding, Severity
from .scanner import scan
from .cleaner import CleanResult, clean
from .scoring import GRADES, grade_for, score_findings
from .differ import DiffResult, diff_reports, diff_text
from .cost import CostReport, cost_report, count_tokens
from . import canary

__version__ = "0.2.0"

__all__ = [
    "Document",
    "Finding",
    "Severity",
    "scan",
    "clean",
    "CleanResult",
    "score_findings",
    "grade_for",
    "GRADES",
    "diff_reports",
    "diff_text",
    "DiffResult",
    "cost_report",
    "count_tokens",
    "CostReport",
    "canary",
    "__version__",
]
