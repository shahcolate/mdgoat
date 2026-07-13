# Changelog

All notable changes to mdgoat are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project
adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.0] - 2026-07-13

### Added
- **`mdgoat diff a.md b.md`** — compare two markdown documents by
  LLM-readiness and see exactly which problems each has that the other
  doesn't. Built for choosing between converters (MarkItDown vs Docling vs
  your own pipeline). `--json` supported.
- **`mdgoat cost`** — estimate the token footprint and per-call dollar cost of
  a document, with an optional `--per-section` breakdown by heading. Uses the
  built-in dependency-free estimator by default; `--tokenizer tiktoken`
  (install `mdgoat[tokenizers]`) gives exact OpenAI counts. Bring your own
  price with `--price-per-1m`.
- **`mdgoat canary`** — the red-team companion to the scanner. `canary inject`
  plants benign, uniquely-marked injections through five smuggling channels;
  `canary verify` checks a model/pipeline response for leaked canary tokens so
  you can measure whether your defenses hold. Every planted canary is also
  something `mdgoat scan` catches.
- **Published GitHub Action** (`action.yml`) — `uses: shahcolate/mdgoat@v0.2.0`
  writes a score table to the job summary, optionally comments it on the PR,
  and gates on `fail-on` / `min-score`.
- **`mdgoat score --markdown`** — emit a markdown table (used by the Action's
  job summary; handy for any CI).
- Library API: `mdgoat.diff_text()`, `mdgoat.cost_report()`,
  `mdgoat.count_tokens()`, `mdgoat.canary`.

## [0.1.0] - 2026-07-13

The first release. mdgoat scans, scores, and cleans markdown before it reaches
an LLM.

### Added
- **`mdgoat scan`** — 27 rules across four categories:
  - **Security:** invisible characters, Unicode tag-block ASCII smuggling
    (with payload decoding), bidi overrides, hidden-comment / alt-text /
    hidden-element injections, image exfiltration beacons, and homoglyph words.
  - **Artifacts:** mojibake, ligatures, non-standard spaces, control
    characters, hyphenation breaks, replacement characters, repeated page
    furniture, orphaned page numbers, and HTML residue.
  - **Structure:** broken tables, unclosed code fences, heading-level jumps,
    empty links, and headingless documents.
  - **Efficiency:** trailing whitespace, excessive blank lines, duplicate
    blocks, and typographic punctuation.
- **`mdgoat score`** — 0–100 LLM-readiness score with a letter grade,
  `--min-score` gating, and a `--badge` shields.io generator.
- **`mdgoat clean`** — deterministic, content-preserving auto-fixes with
  `--in-place`, `--diff`, and `--check` modes.
- **`mdgoat rules`** — lists every rule.
- Library API: `mdgoat.scan()`, `mdgoat.clean()`, `mdgoat.score_findings()`.
- Zero runtime dependencies; Python 3.9–3.13; MIT licensed.
- CI matrix, pre-commit hook, and runnable example fixtures.

[Unreleased]: https://github.com/shahcolate/mdgoat/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/shahcolate/mdgoat/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/shahcolate/mdgoat/releases/tag/v0.1.0
