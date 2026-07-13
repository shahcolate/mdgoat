from __future__ import annotations

import unittest

from mdgoat import scan
from mdgoat.models import Finding, Severity
from mdgoat.scoring import badge_markdown, grade_for, score_findings


def finding(rule_id, severity):
    return Finding(
        rule_id=rule_id,
        rule_name=rule_id.lower(),
        category="security",
        severity=severity,
        message="test",
    )


class ScoringTests(unittest.TestCase):
    def test_empty_findings_is_perfect(self):
        self.assertEqual(score_findings([]), 100)
        self.assertEqual(grade_for(100), "A+")

    def test_clean_document_scores_100(self):
        report = scan("# Title\n\nA perfectly normal paragraph.\n")
        self.assertEqual(report.score, 100)
        self.assertEqual(report.grade, "A+")

    def test_critical_caps_score(self):
        score = score_findings([finding("SEC002", Severity.CRITICAL)])
        self.assertLessEqual(score, 40)
        self.assertEqual(grade_for(score), "F")

    def test_per_rule_cap(self):
        many = [finding("EFF002", Severity.LOW) for _ in range(50)]
        # LOW deducts 2, capped at 3x -> at most 6 points from one rule
        self.assertGreaterEqual(score_findings(many), 94)

    def test_severity_ordering(self):
        high = score_findings([finding("X", Severity.HIGH)])
        medium = score_findings([finding("X", Severity.MEDIUM)])
        low = score_findings([finding("X", Severity.LOW)])
        self.assertLess(high, medium)
        self.assertLess(medium, low)

    def test_badge_markdown(self):
        badge = badge_markdown(97, "A+")
        self.assertIn("img.shields.io", badge)
        self.assertIn("97", badge)
        self.assertIn("brightgreen", badge)


if __name__ == "__main__":
    unittest.main()
