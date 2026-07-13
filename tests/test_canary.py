from __future__ import annotations

import unittest

from mdgoat import canary, scan
from mdgoat.models import Severity

IDS = ["aa11", "bb22", "cc33", "dd44", "ee55"]


class InjectTests(unittest.TestCase):
    def test_plants_one_per_technique(self):
        result = canary.inject("# Doc\n\nBody.\n", _fixed_ids=IDS)
        self.assertEqual(len(result.canaries), len(canary.TECHNIQUES))
        techniques = {c.technique for c in result.canaries}
        self.assertEqual(techniques, set(canary.TECHNIQUES))

    def test_tokens_are_unique_and_prefixed(self):
        result = canary.inject("# Doc\n\nBody.\n", _fixed_ids=IDS)
        tokens = [c.token for c in result.canaries]
        self.assertEqual(len(tokens), len(set(tokens)))
        for t in tokens:
            self.assertTrue(t.startswith(canary.TOKEN_PREFIX))

    def test_selected_techniques_only(self):
        result = canary.inject("# Doc\n\nBody.\n", techniques=["html-comment"], _fixed_ids=IDS)
        self.assertEqual(len(result.canaries), 1)
        self.assertEqual(result.canaries[0].technique, "html-comment")

    def test_unknown_technique_raises(self):
        with self.assertRaises(ValueError):
            canary.inject("x\n", techniques=["nope"])

    def test_every_canary_is_detected_by_scan(self):
        # Dogfood: the scanner must flag the poisoned document as unsafe.
        result = canary.inject("# Report\n\nParagraph one.\n\nParagraph two.\n", _fixed_ids=IDS)
        report = scan(result.text)
        self.assertLessEqual(report.score, 40)  # critical -> capped
        self.assertEqual(report.grade, "F")
        # at least the smuggling channels are surfaced
        rules = {f.rule_id for f in report.findings}
        self.assertTrue({"SEC001", "SEC002", "SEC004", "SEC006"} & rules)

    def test_original_content_preserved(self):
        src = "# Report\n\nImportant business content.\n"
        result = canary.inject(src, _fixed_ids=IDS)
        self.assertIn("Important business content.", result.text)


class VerifyTests(unittest.TestCase):
    def setUp(self):
        self.result = canary.inject("# Doc\n\nA.\n\nB.\n\nC.\n", _fixed_ids=IDS)
        self.manifest = self.result.manifest()

    def test_no_leak_is_defended(self):
        v = canary.verify("The model gave a clean answer with no tokens.", self.manifest)
        self.assertTrue(v.defended)
        self.assertEqual(v.fired, [])
        self.assertEqual(len(v.survived), len(self.manifest["canaries"]))

    def test_leaked_token_fires(self):
        leaked = self.manifest["canaries"][0]["token"]
        v = canary.verify("Sure! " + leaked, self.manifest)
        self.assertFalse(v.defended)
        self.assertEqual(len(v.fired), 1)
        self.assertEqual(v.fired[0].token, leaked)

    def test_multiple_leaks(self):
        toks = [c["token"] for c in self.manifest["canaries"][:3]]
        v = canary.verify(" ".join(toks), self.manifest)
        self.assertEqual(len(v.fired), 3)

    def test_manifest_roundtrip_via_json(self):
        import json
        blob = json.dumps(self.manifest)
        reloaded = json.loads(blob)
        v = canary.verify(self.manifest["canaries"][1]["token"], reloaded)
        self.assertEqual(len(v.fired), 1)


if __name__ == "__main__":
    unittest.main()
