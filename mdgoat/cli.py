"""mdgoat command-line interface.

    mdgoat scan  docs/            # find problems
    mdgoat score README.md        # 0-100 LLM-readiness score
    mdgoat clean report.md        # fix what's safely fixable
    mdgoat rules                  # list every rule
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__
from .cleaner import clean
from .models import Severity
from .report import (
    render_report,
    render_score_line,
    reports_to_json,
    use_color,
)
from .rules import RULES
from .scanner import scan
from .scoring import badge_markdown

MARKDOWN_SUFFIXES = {".md", ".markdown", ".mdown", ".mkd", ".mdx"}


def _collect_files(paths: List[str]) -> List[Path]:
    files: List[Path] = []
    for raw in paths:
        p = Path(raw)
        if raw == "-":
            continue
        if p.is_dir():
            found = sorted(
                f for f in p.rglob("*")
                if f.suffix.lower() in MARKDOWN_SUFFIXES and f.is_file()
            )
            files.extend(found)
        elif p.is_file():
            files.append(p)
        else:
            print("mdgoat: no such file or directory: %s" % raw, file=sys.stderr)
            raise SystemExit(2)
    return files


def _read_inputs(paths: List[str]):
    """Yield (display_path, text) for every input, including stdin as '-'."""
    if not paths or paths == ["-"]:
        yield "<stdin>", sys.stdin.read()
        return
    if "-" in paths:
        yield "<stdin>", sys.stdin.read()
    for f in _collect_files(paths):
        try:
            yield str(f), f.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print("mdgoat: cannot read %s: %s" % (f, exc), file=sys.stderr)
            raise SystemExit(2)


def cmd_scan(args) -> int:
    color = use_color() and not args.json
    reports = []
    for path, text in _read_inputs(args.paths):
        reports.append(
            scan(text, path=path, ignore=args.ignore)
        )
    if not reports:
        print("mdgoat: no markdown files found", file=sys.stderr)
        return 2
    if args.json:
        print(reports_to_json(reports))
    else:
        for i, r in enumerate(reports):
            if i:
                print()
            print(render_report(r, color=color, quiet=args.quiet))
    threshold = Severity.from_name(args.fail_on)
    failed = any(
        f.severity >= threshold for r in reports for f in r.findings
    )
    return 1 if failed else 0


def cmd_score(args) -> int:
    color = use_color() and not args.json
    reports = []
    for path, text in _read_inputs(args.paths):
        reports.append(scan(text, path=path, ignore=args.ignore))
    if not reports:
        print("mdgoat: no markdown files found", file=sys.stderr)
        return 2
    if args.json:
        payload = [
            {
                "path": r.path,
                "score": r.score,
                "grade": r.grade,
                "token_estimate": r.token_estimate,
                "badge": badge_markdown(r.score, r.grade),
            }
            for r in reports
        ]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2))
    else:
        for r in reports:
            print(render_score_line(r, color=color, badge=args.badge))
    if args.min_score is not None:
        if any(r.score < args.min_score for r in reports):
            return 1
    return 0


def cmd_clean(args) -> int:
    inputs = list(_read_inputs(args.paths))
    if not inputs:
        print("mdgoat: no markdown files found", file=sys.stderr)
        return 2
    if len(inputs) > 1 and not args.in_place and not args.check:
        print(
            "mdgoat: multiple files require --in-place (or --check)",
            file=sys.stderr,
        )
        return 2

    dirty = False
    for path, text in inputs:
        result = clean(
            text,
            strip_comments=not args.keep_comments,
            normalize_punctuation=not args.keep_punctuation,
        )
        changed = result.text != text
        dirty = dirty or changed
        if args.check:
            status = "would fix %d issue(s)" % result.total_changes if changed else "clean"
            print("%s: %s" % (path, status), file=sys.stderr)
            continue
        if args.diff:
            sys.stdout.writelines(
                difflib.unified_diff(
                    text.splitlines(keepends=True),
                    result.text.splitlines(keepends=True),
                    fromfile=path,
                    tofile=path + " (cleaned)",
                )
            )
        elif args.in_place:
            if path == "<stdin>":
                print("mdgoat: cannot edit stdin in place", file=sys.stderr)
                return 2
            if changed:
                Path(path).write_text(result.text, encoding="utf-8")
        else:
            sys.stdout.write(result.text)
        if result.total_changes:
            ledger = ", ".join(
                "%s x%d" % (k, v) for k, v in sorted(result.changes.items())
            )
            print(
                "mdgoat: %s: fixed %d issue(s) (%s), ~%d tokens saved"
                % (path, result.total_changes, ledger, result.tokens_saved),
                file=sys.stderr,
            )
        else:
            print("mdgoat: %s: already clean" % path, file=sys.stderr)
    if args.check:
        return 1 if dirty else 0
    return 0


def cmd_rules(args) -> int:
    print("%-8s %-32s %-11s %-9s %-4s %s" % ("ID", "NAME", "CATEGORY", "SEVERITY", "FIX", "DESCRIPTION"))
    for rule_id, name, category, severity, fixable, description in RULES:
        print(
            "%-8s %-32s %-11s %-9s %-4s %s"
            % (rule_id, name, category, severity.label, "yes" if fixable else "no", description)
        )
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mdgoat",
        description="The markdown quality gate for the AI input layer. "
        "Goats eat anything. Your LLM shouldn't.",
    )
    parser.add_argument("--version", action="version", version="mdgoat %s" % __version__)
    sub = parser.add_subparsers(dest="command")

    def add_common(p):
        p.add_argument("paths", nargs="*", default=["-"], help="files, directories, or '-' for stdin")
        p.add_argument("--json", action="store_true", help="machine-readable output")
        p.add_argument(
            "--ignore",
            action="append",
            metavar="RULE",
            help="rule ID to ignore (repeatable), e.g. --ignore EFF004",
        )

    p_scan = sub.add_parser("scan", help="scan markdown for security, artifact, structure, and efficiency issues")
    add_common(p_scan)
    p_scan.add_argument(
        "--fail-on",
        default="high",
        choices=["info", "low", "medium", "high", "critical"],
        help="exit non-zero if any finding is at or above this severity (default: high)",
    )
    p_scan.add_argument("--quiet", action="store_true", help="only show MEDIUM and above")
    p_scan.set_defaults(func=cmd_scan)

    p_score = sub.add_parser("score", help="score LLM-readiness 0-100 with a letter grade")
    add_common(p_score)
    p_score.add_argument("--badge", action="store_true", help="emit a shields.io badge for your README")
    p_score.add_argument("--min-score", type=int, default=None, metavar="N", help="exit non-zero if any file scores below N")
    p_score.set_defaults(func=cmd_score)

    p_clean = sub.add_parser("clean", help="auto-fix everything that is safe to fix")
    add_common(p_clean)
    p_clean.add_argument("--in-place", "-i", action="store_true", help="rewrite files instead of printing")
    p_clean.add_argument("--diff", action="store_true", help="print a unified diff instead of the result")
    p_clean.add_argument("--check", action="store_true", help="report whether files would change; exit 1 if so")
    p_clean.add_argument("--keep-comments", action="store_true", help="do not strip HTML comments")
    p_clean.add_argument("--keep-punctuation", action="store_true", help="do not normalize typographic punctuation")
    p_clean.set_defaults(func=cmd_clean)

    p_rules = sub.add_parser("rules", help="list every rule")
    p_rules.set_defaults(func=cmd_rules)

    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except BrokenPipeError:
        # Downstream closed the pipe (e.g. `mdgoat rules | head`). Exit quietly.
        try:
            sys.stdout.close()
        except Exception:
            pass
        return 0
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
