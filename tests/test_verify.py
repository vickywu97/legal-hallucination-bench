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
    refuse_unverified_ground_truth, EXACT, PARTIAL, FABRICATED, Verification,
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
        # HVI = existence/temporal only: 1 TEMPORAL_DEPRECATED of 3 hard
        # citations (the PARTIAL is a content failure, excluded from HVI).
        self.assertAlmostEqual(rep.metrics["hr_statutory"], 1 / 3, places=5)
        # 1 deprecated / 3 cited
        self.assertAlmostEqual(rep.metrics["rate_deprecated"], 1 / 3, places=5)
        # 1 unverifiable / 4 total
        self.assertAlmostEqual(rep.metrics["rate_unverifiable"], 0.25, places=5)
        # CI is a 2-tuple
        self.assertEqual(len(rep.ci["hr_statutory"]), 2)
        # per-domain HVI (CRIMINAL_LAW has 1 OK + 1 PARTIAL-content; no HVI -> 0)
        self.assertIn("CRIMINAL_LAW", rep.per_domain)
        self.assertAlmostEqual(rep.per_domain["CRIMINAL_LAW"], 0.0, places=5)


class RangeCitationTests(unittest.TestCase):
    """P1: range citations (第146条至第148条 -> 146/147/148) resolve and diff
    as a unit; any non-existent sub-article escalates to HALLUCINATION."""
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        cls.crev = cls.laws["民法典"].revisions[
            list(cls.laws["民法典"].revisions)[-1]]
        cls.gt = "\n".join(
            cls.crev.articles[str(a)].content for a in (146, 147, 148))

    def test_range_exact(self):
        cit = _c("CIVIL_CODE", "民法典", "146-148")
        v = verify_citation(cit, "2025-01-01", self.laws,
                            candidate_text=self.gt)
        self.assertEqual(v.verdict, "OK")
        self.assertEqual(v.diff_level, EXACT)
        self.assertEqual(v.score, 1.0)
        self.assertEqual(v.category, "EXACT")

    def test_range_missing_article(self):
        # 149 does not exist in the KB -> whole range is HALLUCINATION
        cit = _c("CIVIL_CODE", "民法典", "146-149")
        v = verify_citation(cit, "2025-01-01", self.laws,
                            candidate_text=self.gt)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.score, 0.0)
        self.assertEqual(v.category, "NOT_FOUND")


class CrossLawMisattributionTests(unittest.TestCase):
    """P1: 张冠李戴 detection now scans across laws (higher bar 0.90)."""
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        cls.crim_rev = cls.laws["刑法"].revisions[
            list(cls.laws["刑法"].revisions)[-1]]
        cls.civil_rev = cls.laws["民法典"].revisions[
            list(cls.laws["民法典"].revisions)[-1]]
        cls.gt_232 = cls.crim_rev.articles["232"].content
        cls.civil_584 = cls.civil_rev.articles["584"].content  # verified

    def test_same_law_misattribution(self):
        # cite 234 but render 232's text -> same-law MISATTRIBUTED
        cit = _c("CRIMINAL_LAW", "刑法", "234")
        v = verify_citation(cit, "2025-01-01", self.laws,
                            candidate_text=self.gt_232)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "MISATTRIBUTED")
        self.assertIn("same law", v.note)

    def test_cross_law_misattribution(self):
        # cite 刑法 232 but render 民法典 584's full text -> cross-law MISATTRIBUTED
        cit = _c("CRIMINAL_LAW", "刑法", "232")
        v = verify_citation(cit, "2025-01-01", self.laws,
                            candidate_text=self.civil_584)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "MISATTRIBUTED")
        self.assertIn("DIFFERENT law", v.note)
        self.assertIn("民法典", v.note)


class DateHardeningTests(unittest.TestCase):
    """P0: as_of_date parsing must tolerate None / empty / non-ISO formats and
    never crash on bare string comparison."""
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()

    def test_normalize_as_of_variants(self):
        from knowledge_base.loader import normalize_as_of
        self.assertIsNone(normalize_as_of(None))
        self.assertIsNone(normalize_as_of(""))
        self.assertIsNone(normalize_as_of("null"))
        self.assertIsNone(normalize_as_of("garbage"))
        self.assertEqual(normalize_as_of("2024/06/01"), "2024-06-01")
        self.assertEqual(normalize_as_of("2024年6月1日"), "2024-06-01")
        self.assertEqual(normalize_as_of("2024-06-01"), "2024-06-01")

    def test_non_iso_date_still_flags_temporal_trap(self):
        # 旧公司法 repealed 2024-07-01; a post-repeal NON-ISO date must still flag
        cit = _c("COMPANY_LAW", "旧公司法", "3", dep=True)
        v = verify_citation(cit, "2025/01/01", self.laws)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "TEMPORAL_DEPRECATED")

    def test_null_date_does_not_crash(self):
        # None date cannot confirm post-repeal; must degrade gracefully, not TypeError
        cit = _c("COMPANY_LAW", "旧公司法", "3", dep=True)
        v = verify_citation(cit, None, self.laws)
        self.assertIsInstance(v, Verification)


if __name__ == "__main__":
    unittest.main()
