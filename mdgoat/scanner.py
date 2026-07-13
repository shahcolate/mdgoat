"""Run every detector over a document and assemble a report."""

from __future__ import annotations

from typing import Iterable, Optional

from .detectors import ALL_DETECTORS
from .models import Document, FileReport, Severity, estimate_tokens
from .scoring import grade_for, score_findings

_SEVERITY_ORDER = lambda f: (-int(f.severity), f.line or 0, f.rule_id)  # noqa: E731


def scan(
    text: str,
    path: str = "<text>",
    rules: Optional[Iterable[str]] = None,
    ignore: Optional[Iterable[str]] = None,
) -> FileReport:
    """Scan markdown text and return a :class:`FileReport`.

    ``rules`` restricts the scan to the given rule IDs; ``ignore`` drops
    the given rule IDs from the results.
    """
    doc = Document(text, path=path)
    findings = []
    for detector in ALL_DETECTORS:
        findings.extend(detector(doc))

    if rules is not None:
        wanted = {r.upper() for r in rules}
        findings = [f for f in findings if f.rule_id in wanted]
    if ignore is not None:
        dropped = {r.upper() for r in ignore}
        findings = [f for f in findings if f.rule_id not in dropped]

    findings.sort(key=lambda f: (-int(f.severity), f.line or 0, f.rule_id))
    score = score_findings(findings)
    return FileReport(
        path=path,
        findings=findings,
        score=score,
        grade=grade_for(score, findings),
        token_estimate=estimate_tokens(text),
        char_count=len(text),
        line_count=len(doc.lines),
    )
