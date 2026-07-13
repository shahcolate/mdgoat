"""Estimate the token footprint and per-call cost of a markdown document.

By default this uses mdgoat's built-in dependency-free estimator (~±15%).
For exact counts, install an optional tokenizer:

    pip install "mdgoat[tokenizers]"     # brings in tiktoken

and pass ``--tokenizer tiktoken``.

Pricing is illustrative and moves constantly — always confirm current rates
and override with ``--price-per-1m`` for anything that matters. Tokens are
the number mdgoat is actually confident about; cost is a convenience on top.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .models import estimate_tokens

# Illustrative input (prompt) prices in USD per 1,000,000 tokens. These WILL
# go stale; they exist so `mdgoat cost` prints a plausible dollar figure out
# of the box. Override per-run with --price-per-1m, or --model to pick a row.
EXAMPLE_PRICES_PER_1M: Dict[str, float] = {
    "gpt-4o": 2.50,
    "gpt-4o-mini": 0.15,
    "claude-opus": 15.00,
    "claude-sonnet": 3.00,
    "claude-haiku": 0.80,
    "gemini-flash": 0.075,
}

DEFAULT_MODEL = "claude-sonnet"


def count_tokens(text: str, tokenizer: str = "builtin") -> Tuple[int, str]:
    """Return (token_count, tokenizer_used).

    ``tokenizer`` may be "builtin" (default, no dependency) or "tiktoken"
    (exact for OpenAI models, requires the optional dependency). If tiktoken
    is requested but unavailable, falls back to the builtin estimator and
    says so in the returned label.
    """
    if tokenizer == "tiktoken":
        try:
            import tiktoken  # type: ignore

            enc = tiktoken.get_encoding("o200k_base")
            return len(enc.encode(text)), "tiktoken/o200k_base"
        except Exception:
            return estimate_tokens(text), "builtin (tiktoken unavailable)"
    return estimate_tokens(text), "builtin"


@dataclass
class CostReport:
    path: str
    tokens: int
    tokenizer: str
    char_count: int
    model_costs: Dict[str, float] = field(default_factory=dict)
    sections: List["SectionCost"] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "tokens": self.tokens,
            "tokenizer": self.tokenizer,
            "char_count": self.char_count,
            "model_costs_usd": self.model_costs,
            "sections": [s.to_dict() for s in self.sections],
        }


@dataclass
class SectionCost:
    heading: str
    line: int
    tokens: int

    def to_dict(self) -> dict:
        return {"heading": self.heading, "line": self.line, "tokens": self.tokens}


def _split_sections(text: str) -> List[Tuple[str, int, str]]:
    """Split into (heading, line_number, body) by top-level ATX headings.

    Code fences are skipped so a ``# comment`` inside a code block is never
    mistaken for a heading.
    """
    lines = text.split("\n")
    sections: List[Tuple[str, int, str]] = []
    current_head = "(document start)"
    current_line = 1
    buf: List[str] = []
    in_fence = False
    fence_marker = ""
    for i, line in enumerate(lines):
        stripped = line.lstrip()
        if not in_fence and (stripped.startswith("```") or stripped.startswith("~~~")):
            in_fence = True
            fence_marker = stripped[:3]
        elif in_fence and stripped.startswith(fence_marker) and stripped.rstrip("`~ ") == "":
            in_fence = False
        elif not in_fence and stripped[:2] in ("# ", "##") and stripped.startswith("#"):
            level = len(stripped) - len(stripped.lstrip("#"))
            if 1 <= level <= 2:
                if buf or sections or current_head != "(document start)":
                    sections.append((current_head, current_line, "\n".join(buf)))
                current_head = line.strip().lstrip("#").strip() or "(untitled)"
                current_line = i + 1
                buf = []
                continue
        buf.append(line)
    sections.append((current_head, current_line, "\n".join(buf)))
    return [s for s in sections if s[2].strip() or s[0] != "(document start)"]


def cost_report(
    text: str,
    path: str = "<text>",
    tokenizer: str = "builtin",
    models: Optional[List[str]] = None,
    price_per_1m: Optional[float] = None,
    per_section: bool = False,
) -> CostReport:
    tokens, used = count_tokens(text, tokenizer)
    model_costs: Dict[str, float] = {}
    if price_per_1m is not None:
        model_costs["custom"] = round(tokens / 1_000_000 * price_per_1m, 6)
    else:
        for name in models or list(EXAMPLE_PRICES_PER_1M):
            if name in EXAMPLE_PRICES_PER_1M:
                model_costs[name] = round(
                    tokens / 1_000_000 * EXAMPLE_PRICES_PER_1M[name], 6
                )

    sections: List[SectionCost] = []
    if per_section:
        for heading, line, body in _split_sections(text):
            stoks, _ = count_tokens(body, tokenizer)
            sections.append(SectionCost(heading=heading, line=line, tokens=stoks))
        sections.sort(key=lambda s: -s.tokens)

    return CostReport(
        path=path,
        tokens=tokens,
        tokenizer=used,
        char_count=len(text),
        model_costs=model_costs,
        sections=sections,
    )
