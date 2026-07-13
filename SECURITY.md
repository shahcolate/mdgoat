# Security Policy

mdgoat is a defensive tool: it exists to find prompt-injection and data-loss
hazards in markdown *before* that markdown reaches a language model. Two
different kinds of "security issue" can apply to it.

## A technique mdgoat fails to detect

If you know of an invisible-injection, smuggling, or conversion-corruption
technique that mdgoat does **not** currently catch, that is a **feature
request**, not a vulnerability in mdgoat. Please open a public issue using the
**New detector** template with a minimal reproducing document. Improving
coverage in the open helps everyone.

## A vulnerability in mdgoat itself

If you find a flaw in mdgoat's own behavior — for example:

- the **cleaner corrupting legitimate content** (changing meaning, breaking
  valid Unicode, damaging code blocks), or
- a crafted input that causes a **crash, hang, or catastrophic backtracking**
  (ReDoS), or
- the scanner reporting a document as clean while a known payload survives,

please report it privately first. Use GitHub's
[private vulnerability reporting](https://github.com/shahcolate/mdgoat/security/advisories/new)
for this repository, or email the maintainers. We aim to acknowledge within a
few days and to ship a fix promptly.

Please include:
- the exact input (a small file or a hex/`\u` dump is ideal, since the payloads
  are often invisible),
- the mdgoat version (`mdgoat --version`) and Python version,
- what happened versus what you expected.

## Supported versions

mdgoat is pre-1.0; fixes land on the latest release. Once 1.0 ships, this table
will track supported lines.

Thank you for helping keep the AI input layer safe.
