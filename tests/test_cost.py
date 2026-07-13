from __future__ import annotations

import unittest

from mdgoat import cost_report, count_tokens
from mdgoat.cost import EXAMPLE_PRICES_PER_1M


class CostTests(unittest.TestCase):
    def test_builtin_token_count(self):
        tokens, used = count_tokens("hello world " * 100)
        self.assertGreater(tokens, 0)
        self.assertEqual(used, "builtin")

    def test_tiktoken_falls_back_gracefully(self):
        # tiktoken may or may not be installed; either way this must not raise.
        tokens, used = count_tokens("some text", tokenizer="tiktoken")
        self.assertGreater(tokens, 0)
        self.assertTrue(used.startswith("tiktoken") or used.startswith("builtin"))

    def test_default_models_priced(self):
        r = cost_report("word " * 1000)
        for model in EXAMPLE_PRICES_PER_1M:
            self.assertIn(model, r.model_costs)
        # a pricier model costs more than a cheaper one for the same tokens
        self.assertGreater(r.model_costs["claude-opus"], r.model_costs["claude-haiku"])

    def test_price_override(self):
        r = cost_report("word " * 1000, price_per_1m=10.0)
        self.assertEqual(set(r.model_costs), {"custom"})
        self.assertAlmostEqual(r.model_costs["custom"], r.tokens / 1_000_000 * 10.0, places=6)

    def test_model_selection(self):
        r = cost_report("text", models=["gpt-4o"])
        self.assertEqual(set(r.model_costs), {"gpt-4o"})

    def test_per_section_breakdown(self):
        text = "# Big\n\n" + ("word " * 400) + "\n\n# Small\n\ntiny\n"
        r = cost_report(text, per_section=True)
        self.assertGreaterEqual(len(r.sections), 2)
        # sections are sorted largest-first
        self.assertGreaterEqual(r.sections[0].tokens, r.sections[-1].tokens)
        self.assertEqual(r.sections[0].heading, "Big")

    def test_empty_document(self):
        r = cost_report("")
        self.assertEqual(r.tokens, 0)

    def test_per_section_ignores_headings_in_code_fences(self):
        text = "# Real\n\ntext\n\n```python\n# not a heading\nx = 1\n```\n\n## Sub\n\nmore\n"
        r = cost_report(text, per_section=True)
        headings = {s.heading for s in r.sections}
        self.assertIn("Real", headings)
        self.assertIn("Sub", headings)
        self.assertNotIn("not a heading", headings)


if __name__ == "__main__":
    unittest.main()
