"""Security detectors: the invisible ways a document can attack your LLM.

Converted documents are an unreviewed input channel straight into your
model's context window. These detectors target the known smuggling tricks:
invisible Unicode, tag-block ASCII smuggling, bidi overrides, instructions
hidden in HTML comments / alt text / hidden elements, homoglyph spoofing,
and image-URL exfiltration beacons.

All non-ASCII characters in this module are written as escape sequences —
mdgoat's own source has to pass mdgoat.
"""

from __future__ import annotations

import re
from typing import Iterable, List
from urllib.parse import urlsplit

from ..models import CATEGORY_SECURITY, Document, Finding, Severity

# ---------------------------------------------------------------------------
# SEC001 — invisible characters
# ---------------------------------------------------------------------------

ZWSP = "\u200b"
ZWNJ = "\u200c"
ZWJ = "\u200d"
WORD_JOINER = "\u2060"
SOFT_HYPHEN = "\u00ad"
CGJ = "\u034f"
MVS = "\u180e"
BOM = "\ufeff"
VS16 = "\ufe0f"

INVISIBLE_CHARS = {
    ZWSP: "ZERO WIDTH SPACE",
    ZWNJ: "ZERO WIDTH NON-JOINER",
    ZWJ: "ZERO WIDTH JOINER",
    WORD_JOINER: "WORD JOINER",
    SOFT_HYPHEN: "SOFT HYPHEN",
    CGJ: "COMBINING GRAPHEME JOINER",
    MVS: "MONGOLIAN VOWEL SEPARATOR",
    BOM: "ZERO WIDTH NO-BREAK SPACE (BOM)",
}

# ZWJ and VS16 are legitimate inside emoji sequences; only flag them when
# neither neighbor looks like an emoji, where they have no honest purpose.
_EMOJI_CONTEXT_CHARS = (ZWJ, VS16)


def _looks_emoji(ch: str) -> bool:
    if not ch:
        return False
    cp = ord(ch)
    return (
        cp >= 0x1F000
        or 0x2190 <= cp <= 0x2BFF
        or cp in (0x2640, 0x2642, 0x2764, 0x00A9, 0x00AE, 0x2122)
    )


def detect_invisible_chars(doc: Document) -> Iterable[Finding]:
    hits: List[int] = []
    names = set()
    text = doc.text
    for i, ch in enumerate(text):
        name = INVISIBLE_CHARS.get(ch)
        if ch in _EMOJI_CONTEXT_CHARS or "\ufe00" <= ch <= "\ufe0e":
            prev_ch = text[i - 1] if i > 0 else ""
            next_ch = text[i + 1] if i + 1 < len(text) else ""
            if _looks_emoji(prev_ch) or _looks_emoji(next_ch):
                continue
            if name is None:
                name = "VARIATION SELECTOR"
        if not name:
            continue
        if ch == BOM and i == 0:
            continue  # a leading BOM is mundane; the cleaner strips it anyway
        hits.append(i)
        names.add(name)
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="SEC001",
            rule_name="invisible-characters",
            category=CATEGORY_SECURITY,
            severity=Severity.HIGH,
            message=(
                "%d invisible character(s) (%s). Invisible to humans, fully "
                "visible to the LLM — a classic prompt-smuggling channel."
                % (len(hits), ", ".join(sorted(names)))
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# SEC002 — Unicode tag-block smuggling (ASCII smuggling)
# ---------------------------------------------------------------------------

_TAG_RE = re.compile("[\U000E0000-\U000E007F]+")


def detect_tag_smuggling(doc: Document) -> Iterable[Finding]:
    findings = []
    for m in _TAG_RE.finditer(doc.text):
        decoded = "".join(
            chr(ord(c) - 0xE0000) for c in m.group() if 0xE0020 <= ord(c) <= 0xE007E
        )
        line, col = doc.location(m.start())
        preview = decoded.strip()
        if len(preview) > 80:
            preview = preview[:79] + "…"
        message = (
            "Unicode tag-block sequence (%d chars) — the 'ASCII smuggling' "
            "technique for hiding instructions from humans." % len(m.group())
        )
        if preview:
            message += " Decoded payload: %r" % preview
        findings.append(
            Finding(
                rule_id="SEC002",
                rule_name="unicode-tag-smuggling",
                category=CATEGORY_SECURITY,
                severity=Severity.CRITICAL,
                message=message,
                line=line,
                column=col,
                snippet=doc.snippet_at(m.start()),
                count=len(m.group()),
                fixable=True,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# SEC003 — bidirectional control characters
# ---------------------------------------------------------------------------

_BIDI_RE = re.compile("[\u202a-\u202e\u2066-\u2069]")


def detect_bidi_controls(doc: Document) -> Iterable[Finding]:
    hits = [m.start() for m in _BIDI_RE.finditer(doc.text)]
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="SEC003",
            rule_name="bidi-controls",
            category=CATEGORY_SECURITY,
            severity=Severity.HIGH,
            message=(
                "%d bidirectional control character(s). These reorder rendered "
                "text so what a human reviews is not what the model reads "
                "(the 'Trojan Source' trick)." % len(hits)
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=True,
        )
    ]


# ---------------------------------------------------------------------------
# Instruction-phrase heuristics (used by several detectors below)
# ---------------------------------------------------------------------------

INSTRUCTION_RE = re.compile(
    r"""(?ix)
    ignore\s+(?:all\s+|any\s+)?(?:previous|prior|above|earlier)\s+
        (?:instructions?|prompts?|messages?|context)
  | disregard\s+(?:the\s+)?(?:previous|prior|above|system)
  | forget\s+(?:everything|all\s+previous|your\s+instructions)
  | you\s+are\s+now\b
  | new\s+instructions?\s*:
  | system\s+prompt
  | \bdo\s+not\s+(?:tell|reveal|inform|mention|disclose)\b
  | \b(?:reply|respond|answer)\s+(?:with\s+)?only\b
  | \bexfiltrat
  | \bsend\s+(?:this|the|all|it|them)\b.{0,40}\bto\s+(?:https?:|www\.|[\w.+-]+@)
  | \bbegin\s+(?:system|admin|hidden)\b
    """,
)


def _instruction_hit(content: str):
    return INSTRUCTION_RE.search(content)


# ---------------------------------------------------------------------------
# SEC004 / SEC005 — HTML comments (invisible to renderers, visible to LLMs)
# ---------------------------------------------------------------------------

_COMMENT_RE = re.compile(r"<!--(.*?)-->", re.DOTALL)


def detect_html_comments(doc: Document) -> Iterable[Finding]:
    findings = []
    benign_hits: List[int] = []
    for m in _COMMENT_RE.finditer(doc.text):
        line, col = doc.location(m.start())
        if doc.in_fence(line):
            continue
        content = m.group(1)
        if _instruction_hit(content):
            preview = " ".join(content.split())
            if len(preview) > 80:
                preview = preview[:79] + "…"
            findings.append(
                Finding(
                    rule_id="SEC004",
                    rule_name="hidden-instructions-in-comment",
                    category=CATEGORY_SECURITY,
                    severity=Severity.CRITICAL,
                    message=(
                        "HTML comment contains instruction-like text invisible "
                        "to rendered views: %r" % preview
                    ),
                    line=line,
                    column=col,
                    snippet=doc.snippet_at(m.start()),
                    fixable=True,
                )
            )
        else:
            benign_hits.append(m.start())
    if benign_hits:
        line, col = doc.location(benign_hits[0])
        findings.append(
            Finding(
                rule_id="SEC005",
                rule_name="html-comment",
                category=CATEGORY_SECURITY,
                severity=Severity.LOW,
                message=(
                    "%d HTML comment(s). Invisible when rendered but included "
                    "in LLM input — review or strip before ingestion."
                    % len(benign_hits)
                ),
                line=line,
                column=col,
                snippet=doc.snippet_at(benign_hits[0]),
                count=len(benign_hits),
                fixable=True,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# SEC006 — hidden HTML elements
# ---------------------------------------------------------------------------

_HIDDEN_HTML_RE = re.compile(
    r"""(?ix)
    <[a-z][^>]*
    (?:
        style\s*=\s*["'][^"']*(?:display\s*:\s*none|visibility\s*:\s*hidden|font-size\s*:\s*0)
      | \shidden(?=[\s>=])
      | \saria-hidden\s*=\s*["']true
    )
    [^>]*>
    """
)


def detect_hidden_html(doc: Document) -> Iterable[Finding]:
    findings = []
    for m in _HIDDEN_HTML_RE.finditer(doc.text):
        line, col = doc.location(m.start())
        if doc.in_fence(line):
            continue
        findings.append(
            Finding(
                rule_id="SEC006",
                rule_name="hidden-html-element",
                category=CATEGORY_SECURITY,
                severity=Severity.CRITICAL,
                message=(
                    "HTML element styled to be invisible when rendered. "
                    "Whatever it contains, only the LLM will read it."
                ),
                line=line,
                column=col,
                snippet=doc.snippet_at(m.start()),
                fixable=False,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# SEC007 — instructions in alt text / link titles
# ---------------------------------------------------------------------------

_ALT_RE = re.compile(r"!\[([^\]]{4,})\]")
_TITLE_RE = re.compile(r"\[[^\]]*\]\(\s*\S+\s+\"([^\"]{4,})\"\s*\)")


def detect_alt_title_injection(doc: Document) -> Iterable[Finding]:
    findings = []
    for regex, channel, slug in (
        (_ALT_RE, "image alt text", "alt-text"),
        (_TITLE_RE, "link title", "link-title"),
    ):
        for m in regex.finditer(doc.text):
            line, col = doc.location(m.start())
            if doc.in_fence(line):
                continue
            if _instruction_hit(m.group(1)):
                preview = m.group(1)
                if len(preview) > 80:
                    preview = preview[:79] + "…"
                findings.append(
                    Finding(
                        rule_id="SEC007",
                        rule_name="instructions-in-%s" % slug,
                        category=CATEGORY_SECURITY,
                        severity=Severity.HIGH,
                        message=(
                            "Instruction-like text hidden in %s: %r"
                            % (channel, preview)
                        ),
                        line=line,
                        column=col,
                        snippet=doc.snippet_at(m.start()),
                        fixable=False,
                    )
                )
    return findings


# ---------------------------------------------------------------------------
# SEC008 — image URLs that can exfiltrate data
# ---------------------------------------------------------------------------

_IMAGE_URL_RE = re.compile(r"!\[[^\]]*\]\(\s*(<[^>]+>|\S+?)(?:\s+\"[^\"]*\")?\s*\)")

_BEACON_HOSTS = (
    "webhook.site",
    "requestbin",
    "pipedream.net",
    "ngrok.io",
    "ngrok-free.app",
    "burpcollaborator",
    "oastify.com",
    "interact.sh",
    "canarytokens",
    "beeceptor.com",
)


def detect_exfil_images(doc: Document) -> Iterable[Finding]:
    findings = []
    for m in _IMAGE_URL_RE.finditer(doc.text):
        line, col = doc.location(m.start())
        if doc.in_fence(line):
            continue
        url = m.group(1).strip("<>")
        if not url.lower().startswith(("http://", "https://")):
            continue
        try:
            parts = urlsplit(url)
        except ValueError:
            continue
        host = (parts.hostname or "").lower()
        beacon = any(h in host for h in _BEACON_HOSTS)
        big_query = (
            len(parts.query) > 40
            or "%7b" in parts.query.lower()
            or "{" in parts.query
        )
        if not (beacon or big_query):
            continue
        reason = (
            "known callback/beacon service" if beacon else "long dynamic query string"
        )
        findings.append(
            Finding(
                rule_id="SEC008",
                rule_name="image-exfiltration-url",
                category=CATEGORY_SECURITY,
                severity=Severity.HIGH,
                message=(
                    "Image URL looks like a data-exfiltration beacon (%s): %s — "
                    "auto-fetched by many renderers, leaking whatever is "
                    "templated into it." % (reason, url[:100])
                ),
                line=line,
                column=col,
                snippet=doc.snippet_at(m.start()),
                fixable=False,
            )
        )
    return findings


# ---------------------------------------------------------------------------
# SEC009 — mixed-script (homoglyph) words
# ---------------------------------------------------------------------------

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)


def _scripts(word: str) -> set:
    scripts = set()
    for ch in word:
        cp = ord(ch)
        if cp < 128:
            scripts.add("latin")
        elif 0x0400 <= cp <= 0x04FF:
            scripts.add("cyrillic")
        elif 0x0370 <= cp <= 0x03FF:
            scripts.add("greek")
    return scripts


def detect_homoglyphs(doc: Document) -> Iterable[Finding]:
    hits = []
    examples = []
    for m in _WORD_RE.finditer(doc.text):
        s = _scripts(m.group())
        if "latin" in s and ("cyrillic" in s or "greek" in s):
            hits.append(m.start())
            if len(examples) < 3:
                examples.append(m.group())
    if not hits:
        return []
    line, col = doc.location(hits[0])
    return [
        Finding(
            rule_id="SEC009",
            rule_name="mixed-script-homoglyphs",
            category=CATEGORY_SECURITY,
            severity=Severity.HIGH,
            message=(
                "%d word(s) mix Latin with Cyrillic/Greek lookalikes (e.g. %s) — "
                "reads normally to humans, tokenizes differently for the model."
                % (len(hits), ", ".join(repr(e) for e in examples))
            ),
            line=line,
            column=col,
            snippet=doc.snippet_at(hits[0]),
            count=len(hits),
            fixable=False,
        )
    ]


DETECTORS = [
    detect_invisible_chars,
    detect_tag_smuggling,
    detect_bidi_controls,
    detect_html_comments,
    detect_hidden_html,
    detect_alt_title_injection,
    detect_exfil_images,
    detect_homoglyphs,
]
