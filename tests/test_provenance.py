"""Provenance gate: the bench MUST NOT score against unverified (LLM-scaffold)
statute text. This is the single non-negotiable rule of the project."""
import unittest
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws, resolve_article
from benchmark.verify import (
    refuse_unverified_ground_truth,
    ground_truth_verified,
)


class TestProvenanceGate(unittest.TestCase):
    def setUp(self):
        self.laws = load_laws()

    def test_scaffold_node_is_unverified(self):
        r = resolve_article(self.laws, "民法典", "584", "2023-01-01")
        self.assertTrue(r.found)
        # Simulate a not-yet-signed-off scaffold node regardless of the repo's
        # current ledger state, so the test verifies the GATE invariant (an
        # unverified node must not be usable as ground truth) rather than the
        # mutable verification status of one specific article.
        r.verification_status = "unverified"
        self.assertFalse(ground_truth_verified(r))
        gate = refuse_unverified_ground_truth(r, None, "2023-01-01")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.verdict, "UNVERIFIABLE")

    def test_unverified_resolves_to_unverifiable_not_score(self):
        r = resolve_article(self.laws, "公司法", "10", "2025-01-01")
        self.assertTrue(r.found)
        # Simulate a not-yet-signed-off scaffold node regardless of the repo's
        # current ledger state, so the test verifies the GATE invariant (any
        # unverified resolved node must be blocked) rather than the mutable
        # verification status of one specific article.
        r.verification_status = "unverified"
        gate = refuse_unverified_ground_truth(r, None, "2025-01-01")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.verdict, "UNVERIFIABLE")
        self.assertEqual(gate.hardness, "transparent")

    def test_verified_node_would_proceed(self):
        # Simulate an expert-verified node by flipping the flag on the result.
        r = resolve_article(self.laws, "民法典", "584", "2023-01-01")
        r.verification_status = "verified"
        gate = refuse_unverified_ground_truth(r, None, "2023-01-01")
        self.assertIsNone(gate)  # caller may proceed to real verification

    def test_unknown_law_is_not_a_ground_truth_violation(self):
        r = resolve_article(self.laws, "不存在的法律", "1", "2025-01-01")
        self.assertFalse(r.found)
        # gate only fires on found+unverified; unknown law is handled elsewhere
        self.assertIsNone(refuse_unverified_ground_truth(r, None, "2025-01-01"))


if __name__ == "__main__":
    unittest.main()
