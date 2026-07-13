from __future__ import annotations

import unittest

from mdgoat import diff_text


class DiffTests(unittest.TestCase):
    def test_cleaner_document_wins(self):
        dirty = "# Doc\n\nProfits​ up. Itâ€™s good.\n"
        clean = "# Doc\n\nProfits up. It's good.\n"
        d = diff_text(dirty, "a.md", clean, "b.md")
        self.assertEqual(d.winner, "b.md")
        self.assertGreater(d.score_delta, 0)

    def test_only_left_lists_extra_findings(self):
        dirty = "text​with zwsp\n"
        clean = "text with space\n"
        d = diff_text(dirty, "dirty.md", clean, "clean.md")
        rules = {f.rule_id for f in d.only_left}
        self.assertIn("SEC001", rules)
        self.assertEqual(d.only_right, [])

    def test_identical_documents_tie(self):
        text = "# Same\n\nIdentical content.\n"
        d = diff_text(text, "a.md", text, "b.md")
        self.assertIsNone(d.winner)
        self.assertEqual(d.score_delta, 0)
        self.assertEqual(d.only_left, [])
        self.assertEqual(d.only_right, [])

    def test_to_dict_shape(self):
        d = diff_text("a​\n", "a.md", "b\n", "b.md")
        data = d.to_dict()
        self.assertEqual(data["winner"], "b.md")
        self.assertIn("only_left", data)
        self.assertIn("left", data)


if __name__ == "__main__":
    unittest.main()
