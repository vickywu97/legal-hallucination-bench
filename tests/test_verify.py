"""Tests for the Week-4 content-diff verification engine (benchmark/verify.py).

Covers every branch of docs/DIFF_POLICY.md:
  - three-level content diff (EXACT / PARTIAL / FABRICATED)
  - failure sub-categories (TRUNCATED / MISATTRIBUTED / FABRICATED_GENERIC)
  - temporal trap (TEMPORAL_DEPRECATED) and NOT_FOUND
  - provenance gate (UNVERIFIED_GT -> UNVERIFIABLE, never scored)
  - normalization + segmentation units
  - score.py aggregation (HR, deprecated rate, unverifiable rate)
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import Citation
from benchmark.verify import (
    verify_citation, normalize, segment,
    refuse_unverified_ground_truth, EXACT, PARTIAL, FABRICATED,
)
from benchmark.score import score


def _c(code, name, ano, dep=False):
    return Citation(cit_type="law", raw=f"{name}第{ano}条", law_code=code,
                    law_name=name, article_no=ano, deprecated_alias=dep)


class NormalizeTests(unittest.TestCase):
    def test_strips_bracket_title(self):
        self.assertNotIn("【", normalize("【故意杀人罪】故意杀人的，处死刑。"))
        self.assertEqual(normalize("【故意杀人罪】故意杀人的，处死刑。"),
                         normalize("故意杀人的，处死刑。"))

    def test_strips_leading_article_label(self):
        self.assertEqual(normalize("第232条故意杀人的"), normalize("故意杀人的"))

    def test_unifies_punctuation(self):
        self.assertEqual(normalize("甲；乙。丙，丁"),
                         normalize("甲;乙.丙,丁"))

    def test_segment(self):
        self.assertEqual(segment("甲。乙；丙"), ["甲", "乙", "丙"])


class DiffLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        # grab a verified 刑法 article (232) text
        cls.gt = cls.laws["刑法"].revisions[
            list(cls.laws["刑法"].revisions)[-1]].articles["232"].content

    def _v(self, cand):
        return verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                                "2025-01-01", self.laws, candidate_text=cand)

    def test_exact(self):
        v = self._v(self.gt)
        self.assertEqual(v.diff_level, EXACT)
        self.assertEqual(v.verdict, "OK")
        self.assertEqual(v.score, 1.0)

    def test_superset_extra_explanation_is_fabricated(self):
        # Appending an extra explanatory clause makes the answer non-exact.
        # Under the strict binary policy a non-exact answer is FABRICATED
        # (HALLUCINATION), NOT OK -- even if it covers 100% of clauses. The
        # diagnostic category remains PARTIAL, but the score is 0.0.
        v = self._v(self.gt + "（本条第1款所称故意杀人包括作为与不作为）")
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "PARTIAL")
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertAlmostEqual(v.score, 0.0)

    def test_drop_last_clause_is_fabricated(self):
        # Dropping the last clause makes the answer non-exact -> FABRICATED.
        # Diagnostic category PARTIAL, but score is 0.0 (no partial credit).
        seg = self.gt.split("；")
        v = self._v("；".join(seg[:-1]))
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "PARTIAL")
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertAlmostEqual(v.score, 0.0)

    def test_fabricated_generic(self):
        v = self._v("本条所规定的内容纯属虚构不存在于任何现行法律xyz")
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "FABRICATED_GENERIC")
        self.assertEqual(v.score, 0.0)

    def test_truncated(self):
        # prefix of ground truth -> reverse coverage high, length < 0.7x
        cand = self.gt[:max(1, int(len(self.gt) * 0.4))]
        v = self._v(cand)
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "TRUNCATED")

    def test_misattributed(self):
        # model cites 232 but outputs 234's verified text -> 张冠李戴
        gt234 = self.laws["刑法"].revisions[
            list(self.laws["刑法"].revisions)[-1]].articles["234"].content
        v = self._v(gt234)
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "MISATTRIBUTED")


class CitationLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()

    def test_citation_ok_no_candidate(self):
        v = verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                            "2025-01-01", self.laws)
        self.assertEqual(v.verdict, "OK")
        self.assertEqual(v.category, "CITATION_OK")

    def test_temporal_deprecated(self):
        v = verify_citation(_c("COMPANY_LAW", "旧公司法", "3", dep=True),
                            "2025-01-01", self.laws)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "TEMPORAL_DEPRECATED")

    def test_not_found_relocated(self):
        # 公司法旧第13条在新法已 relocation -> not in new revision
        v = verify_citation(_c("COMPANY_LAW", "公司法", "13"),
                            "2025-01-01", self.laws)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "NOT_FOUND")

    def test_old_company_law_article_purged(self):
        # After purging the 2018 Company Law nodes, the old article 3 no longer
        # exists even at a pre-repeal date -> NOT_FOUND (not UNVERIFIABLE: the
        # node was removed, not merely left unverified). This documents the
        # clean-KB invariant: stale articles are gone, never silently scorable.
        v = verify_citation(_c("COMPANY_LAW", "公司法", "3"),
                            "2020-01-01", self.laws)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "NOT_FOUND")


class ProvenanceGateTests(unittest.TestCase):
    def test_gate_returns_unverifiable_for_unverified(self):
        from knowledge_base.loader import ResolveResult
        r = ResolveResult(found=True, content="x", verification_status="unverified")
        gate = refuse_unverified_ground_truth(r, _c("X", "y", "1"), "2025-01-01")
        self.assertIsNotNone(gate)
        self.assertEqual(gate.verdict, "UNVERIFIABLE")

    def test_gate_none_for_verified(self):
        from knowledge_base.loader import ResolveResult
        r = ResolveResult(found=True, content="x", verification_status="verified")
        self.assertIsNone(refuse_unverified_ground_truth(r, _c("X", "y", "1"), "2025-01-01"))


class ScoreTests(unittest.TestCase):
    def test_aggregation(self):
        recs = [
            {"verdict": "OK", "hardness": "hard", "category": "EXACT",
             "domain": "CRIMINAL_LAW", "score": 1.0},
            {"verdict": "HALLUCINATION", "hardness": "hard", "category": "PARTIAL",
             "domain": "CRIMINAL_LAW", "score": 0.0},
            {"verdict": "HALLUCINATION", "hardness": "hard",
             "category": "TEMPORAL_DEPRECATED", "domain": "COMPANY_LAW", "score": 0.0},
            {"verdict": "UNVERIFIABLE", "hardness": "transparent",
             "category": "UNVERIFIED_GT", "domain": "COMPANY_LAW", "score": 0.0},
        ]
        rep = score(recs)
        # 2 HALLUCINATION + 1 OK -> HR = 2/3
        self.assertAlmostEqual(rep.metrics["hr_statutory"], 2 / 3, places=5)
        # 1 deprecated / 3 cited
        self.assertAlmostEqual(rep.metrics["rate_deprecated"], 1 / 3, places=5)
        # 1 unverifiable / 4 total
        self.assertAlmostEqual(rep.metrics["rate_unverifiable"], 0.25, places=5)
        # CI is a 2-tuple
        self.assertEqual(len(rep.ci["hr_statutory"]), 2)
        # per-domain
        self.assertIn("CRIMINAL_LAW", rep.per_domain)
        self.assertAlmostEqual(rep.per_domain["CRIMINAL_LAW"], 0.5, places=5)


if __name__ == "__main__":
    unittest.main()
