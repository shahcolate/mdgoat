"""mdgoat command-line interface.

    mdgoat scan  docs/            # find problems
    mdgoat score README.md        # 0-100 LLM-readiness score
    mdgoat clean report.md        # fix what's safely fixable
    mdgoat diff a.md b.md         # compare two conversions
    mdgoat cost report.md         # token & dollar footprint
    mdgoat canary inject doc.md   # red-team your injection defenses
    mdgoat rules                  # list every rule
"""

from __future__ import annotations

import argparse
import difflib
import json
import sys
from pathlib import Path
from typing import List, Optional

from . import __version__, canary as canary_mod
from .cleaner import clean
from .cost import EXAMPLE_PRICES_PER_1M, cost_report
from .differ import diff_reports
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
    elif args.markdown:
        print("| File | Score | Grade | ~Tokens |")
        print("|------|------:|:-----:|--------:|")
        for r in reports:
            print(
                "| `%s` | %d/100 | %s | %s |"
                % (r.path, r.score, r.grade, format(r.token_estimate, ","))
            )
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


def _read_one(path: str) -> str:
    if path == "-":
        return sys.stdin.read()
    p = Path(path)
    if not p.is_file():
        print("mdgoat: no such file: %s" % path, file=sys.stderr)
        raise SystemExit(2)
    return p.read_text(encoding="utf-8", errors="replace")


def cmd_diff(args) -> int:
    left = scan(_read_one(args.left), path=args.left)
    right = scan(_read_one(args.right), path=args.right)
    result = diff_reports(left, right)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, ensure_ascii=False))
        return 0
    color = use_color()

    def line(r):
        return "  %-40s %3d/100 (%s)  ~%s tokens" % (
            r.path, r.score, r.grade, format(r.token_estimate, ",")
        )

    print("Comparing two documents by LLM-readiness:")
    print(line(left))
    print(line(right))
    print()
    if result.winner:
        print(
            "  → %s is cleaner by %d point(s)."
            % (result.winner, abs(result.score_delta))
        )
    else:
        print("  → tie (%d/100 each)." % left.score)

    if result.only_left:
        print("\n  Only in %s (%d):" % (left.path, len(result.only_left)))
        for f in result.only_left:
            print("    %-8s %s %s" % (f.severity.label, f.rule_id, f.message[:88]))
    if result.only_right:
        print("\n  Only in %s (%d):" % (right.path, len(result.only_right)))
        for f in result.only_right:
            print("    %-8s %s %s" % (f.severity.label, f.rule_id, f.message[:88]))
    if not result.only_left and not result.only_right:
        print("\n  Identical findings.")
    return 0


def cmd_cost(args) -> int:
    reports = []
    for path, text in _read_inputs(args.paths):
        reports.append(
            cost_report(
                text,
                path=path,
                tokenizer=args.tokenizer,
                models=args.model,
                price_per_1m=args.price_per_1m,
                per_section=args.per_section,
            )
        )
    if not reports:
        print("mdgoat: no markdown files found", file=sys.stderr)
        return 2
    if args.json:
        payload = [r.to_dict() for r in reports]
        print(json.dumps(payload[0] if len(payload) == 1 else payload, indent=2))
        return 0
    for i, r in enumerate(reports):
        if i:
            print()
        print("%s  %s tokens (%s)" % (r.path, format(r.tokens, ","), r.tokenizer))
        for model, cost in r.model_costs.items():
            print("  $%.4f per call   %s" % (cost, model))
        if r.sections:
            print("  top sections by tokens:")
            for s in r.sections[:8]:
                print("    %6s  %s" % (format(s.tokens, ","), s.heading[:60]))
    return 0


def cmd_canary(args) -> int:
    if args.canary_command == "inject":
        text = _read_one(args.file)
        result = canary_mod.inject(text, techniques=args.technique)
        manifest = result.manifest()
        if args.output:
            Path(args.output).write_text(result.text, encoding="utf-8")
            print("mdgoat: wrote poisoned document to %s" % args.output, file=sys.stderr)
        else:
            sys.stdout.write(result.text)
        manifest_path = args.manifest or (
            (args.output + ".manifest.json") if args.output else None
        )
        if manifest_path:
            Path(manifest_path).write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            print("mdgoat: wrote manifest to %s" % manifest_path, file=sys.stderr)
        elif args.output:
            pass
        print(
            "mdgoat: planted %d canary/canaries (%s)"
            % (manifest["count"], ", ".join(c["technique"] for c in manifest["canaries"])),
            file=sys.stderr,
        )
        if manifest_path is None and not args.output:
            # stdout held the document; emit the manifest to stderr as JSON so
            # nothing is lost when piping.
            print(json.dumps(manifest), file=sys.stderr)
        return 0

    if args.canary_command == "verify":
        manifest = json.loads(_read_one(args.manifest))
        response = _read_one(args.response)
        result = canary_mod.verify(response, manifest)
        if args.json:
            print(json.dumps(result.to_dict(), indent=2))
        else:
            color = use_color()
            green = "\x1b[1;32m" if color else ""
            red = "\x1b[1;31m" if color else ""
            dim = "\x1b[2m" if color else ""
            reset = "\x1b[0m" if color else ""
            if result.defended:
                print("%sPASS%s: no canary tokens leaked — every injection was neutralized." % (green, reset))
            else:
                print(
                    "%sFAIL%s: %d injection channel(s) reached the model:"
                    % (red, reset, len(result.fired))
                )
                for c in result.fired:
                    print("  %s%s%s  (%s)" % (red, c.token, reset, c.technique))
            if result.survived:
                print(
                    "  %sdefended: %s%s"
                    % (dim, ", ".join(c.technique for c in result.survived), reset)
                )
        return 0 if result.defended else 1

    print("mdgoat: canary needs a subcommand (inject or verify)", file=sys.stderr)
    return 2


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
    p_score.add_argument("--markdown", action="store_true", help="emit a markdown table (great for CI job summaries)")
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

    p_diff = sub.add_parser("diff", help="compare two markdown files by LLM-readiness (e.g. two converters)")
    p_diff.add_argument("left", help="first file (or '-' for stdin)")
    p_diff.add_argument("right", help="second file")
    p_diff.add_argument("--json", action="store_true", help="machine-readable output")
    p_diff.set_defaults(func=cmd_diff)

    p_cost = sub.add_parser("cost", help="estimate token footprint and per-call dollar cost")
    p_cost.add_argument("paths", nargs="*", default=["-"], help="files, directories, or '-' for stdin")
    p_cost.add_argument("--json", action="store_true", help="machine-readable output")
    p_cost.add_argument(
        "--tokenizer",
        default="builtin",
        choices=["builtin", "tiktoken"],
        help="token counter; 'tiktoken' is exact but needs mdgoat[tokenizers] (default: builtin)",
    )
    p_cost.add_argument(
        "--model",
        action="append",
        metavar="NAME",
        help="price row(s) to show (repeatable); choices: %s" % ", ".join(EXAMPLE_PRICES_PER_1M),
    )
    p_cost.add_argument(
        "--price-per-1m",
        type=float,
        default=None,
        metavar="USD",
        help="your own price per 1,000,000 input tokens (overrides the built-in table)",
    )
    p_cost.add_argument("--per-section", action="store_true", help="break tokens down by top-level heading")
    p_cost.set_defaults(func=cmd_cost)

    p_canary = sub.add_parser(
        "canary",
        help="red-team your injection defenses: plant benign marked injections, then verify",
    )
    canary_sub = p_canary.add_subparsers(dest="canary_command")

    p_inject = canary_sub.add_parser("inject", help="plant benign marked canary injections into a document")
    p_inject.add_argument("file", help="source document (or '-' for stdin)")
    p_inject.add_argument("--output", "-o", metavar="FILE", help="write poisoned document here (default: stdout)")
    p_inject.add_argument("--manifest", metavar="FILE", help="write the canary manifest JSON here")
    p_inject.add_argument(
        "--technique",
        action="append",
        metavar="NAME",
        help="channel(s) to use (repeatable); choices: %s" % ", ".join(canary_mod.TECHNIQUES),
    )
    p_inject.set_defaults(func=cmd_canary)

    p_cverify = canary_sub.add_parser("verify", help="check a model response for leaked canary tokens")
    p_cverify.add_argument("manifest", help="the manifest JSON written by 'canary inject'")
    p_cverify.add_argument("response", help="the model/pipeline output to check (or '-' for stdin)")
    p_cverify.add_argument("--json", action="store_true", help="machine-readable output")
    p_cverify.set_defaults(func=cmd_canary)

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
