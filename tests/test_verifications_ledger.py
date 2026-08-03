"""Tests for the human verification ledger (verifications.json) workflow.

Proves that:
* `verified` promotes a node and can override its content with a correction.
* `rejected` + corrected text promotes to verified (expert fixed it).
* `rejected` without correction stays excluded from scoring.
* `validate()` accepts the `rejected` status.
* the scoring gate refuses BOTH unverified and rejected nodes.
* `verification_progress` counts correctly.
"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.build_statute import generate, validate
from knowledge_base.verify_kb import apply_decision, verification_progress
from benchmark.verify import refuse_unverified_ground_truth


def find_node(nodes, law_code, article_number, effective_date):
    for n in nodes:
        if (n["law_code"] == law_code
                and n["article_number"] == article_number
                and n["effective_date"] == effective_date):
            return n
    return None


class TestVerificationLedger(unittest.TestCase):
    def test_default_all_unverified(self):
        # Assert the SEED *scaffold* defaults to unverified when no human verdicts
        # exist. Pass an explicit empty ledger so the test does not depend on the
        # presence/absence of a real verifications.json on disk (which legitimately
        # appears as nodes get expert-verified over time).
        nodes = generate(ledger={})
        self.assertTrue(nodes)
        self.assertTrue(all(n["verification_status"] == "unverified" for n in nodes))

    def test_verified_promotes_and_overrides(self):
        nodes = generate()
        tgt = find_node(nodes, "CIVIL_CODE", "第1条", "2021-01-01")
        self.assertIsNotNone(tgt)
        ledger = {}
        apply_decision(ledger, tgt["id"], "verified",
                       corrected_content="正确文本X")
        m = find_node(generate(ledger=ledger), "CIVIL_CODE", "第1条", "2021-01-01")
        self.assertEqual(m["verification_status"], "verified")
        self.assertEqual(m["content"], "正确文本X")
        self.assertEqual(m["verified_by"], "Vicky Wu (律师/税务师/专利代理师)")
        self.assertIsNotNone(m["verified_at"])

    def test_rejected_with_correction_promotes(self):
        nodes = generate()
        tgt = find_node(nodes, "COMPANY_LAW", "第15条", "2024-07-01")
        ledger = {}
        apply_decision(ledger, tgt["id"], "rejected",
                       corrected_content="修正后文本")
        m = find_node(generate(ledger=ledger), "COMPANY_LAW", "第15条", "2024-07-01")
        self.assertEqual(m["verification_status"], "verified")
        self.assertEqual(m["content"], "修正后文本")

    def test_rejected_without_correction_blocked(self):
        nodes = generate()
        tgt = find_node(nodes, "COMPANY_LAW", "第15条", "2024-07-01")
        ledger = {}
        apply_decision(ledger, tgt["id"], "rejected")
        m = find_node(generate(ledger=ledger), "COMPANY_LAW", "第15条", "2024-07-01")
        self.assertEqual(m["verification_status"], "rejected")
        # both unverified and rejected are refused by the scoring gate
        fake = SimpleNamespace(found=True, verification_status="rejected")
        g = refuse_unverified_ground_truth(fake, None, "2020-01-01")
        self.assertIsNotNone(g)
        self.assertEqual(g.verdict, "UNVERIFIABLE")

    def test_validate_allows_rejected(self):
        nodes = generate()
        tgt = find_node(nodes, "COMPANY_LAW", "第15条", "2024-07-01")
        ledger = {}
        apply_decision(ledger, tgt["id"], "rejected")
        errors = validate(generate(ledger=ledger))
        self.assertEqual(errors, [], f"unexpected errors: {errors}")

    def test_progress_counts(self):
        nodes = generate()
        tgt = find_node(nodes, "CIVIL_CODE", "第1条", "2021-01-01")
        ledger = {}
        apply_decision(ledger, tgt["id"], "verified")
        merged = generate(ledger=ledger)
        prog = verification_progress(merged)
        self.assertEqual(prog["totals"]["verified"], 1)
        self.assertEqual(prog["totals"]["unverified"], len(merged) - 1)


if __name__ == "__main__":
    unittest.main()
