from __future__ import annotations

import unittest

from mdgoat import scan


def rules_found(text):
    return {f.rule_id for f in scan(text).findings}


class MojibakeTests(unittest.TestCase):
    def test_curly_quote_mojibake(self):
        self.assertIn("ART001", rules_found("Itâ€™s broken\n"))

    def test_accent_mojibake(self):
        self.assertIn("ART001", rules_found("CafÃ© au lait\n"))

    def test_proper_unicode_ok(self):
        self.assertNotIn("ART001", rules_found("Café — it’s fine\n"))


class LigatureTests(unittest.TestCase):
    def test_fi_ligature(self):
        report = scan("The ﬁnal ﬁle\n")
        f = next(f for f in report.findings if f.rule_id == "ART002")
        self.assertEqual(f.count, 2)


class SpaceTests(unittest.TestCase):
    def test_nbsp_flagged(self):
        self.assertIn("ART003", rules_found("10 000 users\n"))


class ControlCharTests(unittest.TestCase):
    def test_form_feed_flagged(self):
        self.assertIn("ART004", rules_found("page one\x0cpage two\n"))

    def test_tab_and_newline_ok(self):
        self.assertNotIn("ART004", rules_found("col1\tcol2\nrow\n"))


class HyphenationTests(unittest.TestCase):
    def test_hyphen_break_flagged(self):
        self.assertIn("ART005", rules_found("The conver-\nsion completed\n"))

    def test_list_dash_ok(self):
        self.assertNotIn("ART005", rules_found("- item one\n- item two\n"))


class ReplacementTests(unittest.TestCase):
    def test_replacement_char(self):
        report = scan("data � lost\n")
        f = next(f for f in report.findings if f.rule_id == "ART006")
        self.assertFalse(f.fixable)


class BoilerplateTests(unittest.TestCase):
    def test_repeated_footer(self):
        footer = "CONFIDENTIAL - Acme Corp Annual Report 2026\n"
        text = ("Some real content here.\n\n" + footer + "\n") * 3
        self.assertIn("ART007", rules_found(text))

    def test_unique_lines_ok(self):
        text = "\n".join("This is unique line number %d of prose." % i for i in range(10))
        self.assertNotIn("ART007", rules_found(text + "\n"))


class PageNumberTests(unittest.TestCase):
    def test_stranded_page_numbers(self):
        text = "Intro text.\n\n12\n\nMore text.\n\nPage 13 of 90\n\nEnd.\n"
        self.assertIn("ART008", rules_found(text))

    def test_numbered_list_ok(self):
        text = "Steps:\n1. first\n2. second\n"
        self.assertNotIn("ART008", rules_found(text))


class HtmlResidueTests(unittest.TestCase):
    def test_entity_soup_flagged(self):
        text = "a&nbsp;b&nbsp;c&amp;d&nbsp;e&nbsp;f <div>x</div>\n"
        self.assertIn("ART009", rules_found(text))

    def test_single_entity_ok(self):
        self.assertNotIn("ART009", rules_found("AT&amp;T\n"))


if __name__ == "__main__":
    unittest.main()
