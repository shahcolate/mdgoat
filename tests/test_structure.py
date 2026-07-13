from __future__ import annotations

import unittest

from mdgoat import scan


def rules_found(text):
    return {f.rule_id for f in scan(text).findings}


GOOD_TABLE = """\
| Region | Q1 | Q2 |
|--------|----|----|
| East   | 10 | 20 |
| West   | 5  | 15 |
"""

BAD_TABLE = """\
| Region | Q1 | Q2 |
|--------|----|----|
| East   | 10 | 20 |
| West   | 5  |
"""


class TableTests(unittest.TestCase):
    def test_good_table_passes(self):
        self.assertNotIn("STR001", rules_found(GOOD_TABLE))

    def test_short_row_flagged(self):
        self.assertIn("STR001", rules_found(BAD_TABLE))

    def test_table_in_fence_ignored(self):
        self.assertNotIn("STR001", rules_found("```\n%s```\n" % BAD_TABLE))


class FenceTests(unittest.TestCase):
    def test_unclosed_fence_flagged(self):
        self.assertIn("STR002", rules_found("intro\n\n```python\nprint('hi')\n"))

    def test_closed_fence_ok(self):
        self.assertNotIn("STR002", rules_found("```python\nprint('hi')\n```\n"))


class HeadingTests(unittest.TestCase):
    def test_level_jump_flagged(self):
        self.assertIn("STR003", rules_found("## Section\n\n#### Deep\n"))

    def test_sequential_levels_ok(self):
        self.assertNotIn("STR003", rules_found("# One\n\n## Two\n\n### Three\n"))

    def test_headingless_long_doc(self):
        text = ("plain prose sentence. " * 40 + "\n") * 6
        self.assertIn("STR005", rules_found(text))


class LinkTests(unittest.TestCase):
    def test_empty_link_flagged(self):
        self.assertIn("STR004", rules_found("See [the docs]() for more.\n"))

    def test_normal_link_ok(self):
        self.assertNotIn("STR004", rules_found("See [docs](https://example.com).\n"))


if __name__ == "__main__":
    unittest.main()
