"""Terminal and JSON rendering of scan results."""

from __future__ import annotations

import json
import sys
from typing import List

from .models import FileReport, Severity
from .scoring import badge_markdown

_RESET = "\x1b[0m"
_BOLD = "\x1b[1m"
_DIM = "\x1b[2m"

_SEVERITY_COLORS = {
    Severity.CRITICAL: "\x1b[1;35m",  # bold magenta
    Severity.HIGH: "\x1b[31m",        # red
    Severity.MEDIUM: "\x1b[33m",      # yellow
    Severity.LOW: "\x1b[36m",         # cyan
    Severity.INFO: "\x1b[2m",         # dim
}

_GRADE_COLORS = {
    "A+": "\x1b[1;32m",
    "A": "\x1b[32m",
    "B": "\x1b[32m",
    "C": "\x1b[33m",
    "D": "\x1b[33m",
    "F": "\x1b[1;31m",
}


def use_color(stream=None) -> bool:
    stream = stream or sys.stdout
    return hasattr(stream, "isatty") and stream.isatty()


def _c(code: str, text: str, color: bool) -> str:
    return "%s%s%s" % (code, text, _RESET) if color else text


def render_report(report: FileReport, color: bool = False, quiet: bool = False) -> str:
    out: List[str] = []
    grade_str = _c(_GRADE_COLORS.get(report.grade, ""), report.grade, color)
    header = "%s  %s/100 (%s)  ~%s tokens" % (
        _c(_BOLD, report.path, color),
        report.score,
        grade_str,
        format(report.token_estimate, ","),
    )
    out.append(header)

    if not report.findings:
        out.append("  " + _c("\x1b[32m", "clean — nothing found", color))
        return "\n".join(out)

    for f in report.findings:
        if quiet and f.severity < Severity.MEDIUM:
            continue
        sev = _c(_SEVERITY_COLORS[f.severity], "%-8s" % f.severity.label, color)
        loc = ""
        if f.line is not None:
            loc = ":%d" % f.line
            if f.column is not None:
                loc += ":%d" % f.column
        out.append("  %s %s%s  %s" % (sev, f.rule_id, loc, f.message))
        if f.snippet:
            out.append("           %s" % _c(_DIM, "| " + f.snippet, color))
    counts = report.counts_by_severity()
    summary = ", ".join(
        "%d %s" % (n, label.lower()) for label, n in counts.items() if n
    )
    out.append("  " + _c(_DIM, "-- %d finding(s): %s" % (len(report.findings), summary), color))
    return "\n".join(out)


def render_score_line(report: FileReport, color: bool = False, badge: bool = False) -> str:
    grade_str = _c(_GRADE_COLORS.get(report.grade, ""), "%-2s" % report.grade, color)
    line = "%3d/100  %s  %s" % (report.score, grade_str, report.path)
    if badge:
        line += "\n         %s" % badge_markdown(report.score, report.grade)
    return line


def reports_to_json(reports: List[FileReport]) -> str:
    if len(reports) == 1:
        return json.dumps(reports[0].to_dict(), indent=2, ensure_ascii=False)
    return json.dumps([r.to_dict() for r in reports], indent=2, ensure_ascii=False)
