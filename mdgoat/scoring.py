"""LLM-readiness scoring.

Every document starts at 100. Findings deduct points by severity, with a
per-rule cap so one noisy rule can't dominate. Any CRITICAL security
finding caps the score at 40 — a document carrying hidden instructions is
not "mostly fine".
"""

from __future__ import annotations

from typing import Iterable, List

from .models import Finding, Severity

DEDUCTIONS = {
    Severity.CRITICAL: 30,
    Severity.HIGH: 12,
    Severity.MEDIUM: 5,
    Severity.LOW: 2,
    Severity.INFO: 0,
}

# One rule can deduct at most 3x its base severity, no matter how many
# findings it produced.
RULE_CAP_MULTIPLIER = 3

CRITICAL_SCORE_CAP = 40

GRADES = [
    (97, "A+"),
    (90, "A"),
    (80, "B"),
    (70, "C"),
    (60, "D"),
    (0, "F"),
]


def score_findings(findings: Iterable[Finding]) -> int:
    per_rule: dict = {}
    has_critical = False
    for f in findings:
        per_rule.setdefault(f.rule_id, []).append(f)
        if f.severity == Severity.CRITICAL:
            has_critical = True

    total = 0
    for rule_id, rule_findings in per_rule.items():
        base = DEDUCTIONS[rule_findings[0].severity]
        deduction = sum(DEDUCTIONS[f.severity] for f in rule_findings)
        total += min(deduction, base * RULE_CAP_MULTIPLIER)

    score = max(0, 100 - total)
    if has_critical:
        score = min(score, CRITICAL_SCORE_CAP)
    return score


def grade_for(score: int, findings: Iterable[Finding] = ()) -> str:
    for threshold, grade in GRADES:
        if score >= threshold:
            return grade
    return "F"


def badge_color(grade: str) -> str:
    return {
        "A+": "brightgreen",
        "A": "brightgreen",
        "B": "green",
        "C": "yellow",
        "D": "orange",
        "F": "red",
    }.get(grade, "lightgrey")


def badge_markdown(score: int, grade: str) -> str:
    """A shields.io badge for READMEs — the bragging-rights loop."""
    label = "mdgoat"
    value = "%d%%20%s" % (score, grade.replace("+", "%2B"))
    return "![mdgoat: %d %s](https://img.shields.io/badge/%s-%s-%s)" % (
        score,
        grade,
        label,
        value,
        badge_color(grade),
    )
