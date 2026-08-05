"""Soft 张冠李戴 probe (diagnostic only — never affects score/category).

The hard MISATTRIBUTED check (benchmark/verify._cross_check_misattribution)
only fires on near-verbatim overlap (same-law cov>=0.80, cross-law>=0.90).
Real models often PARAPHRASE the wrong article, which slips through as
FABRICATED_GENERIC/PARTIAL and leaves CRFI blind. ``_soft_misattribution_check``
runs when the hard check did NOT trigger and surfaces a near-miss overlap in
the loose band below the hard threshold — written to Verification.note only.

Proven:
  1. moderate (non-verbatim) overlap with a DIFFERENT article -> SOFT flag,
     unchanged category/score (same-law).
  2. genuine partial answer to the CITED article -> NO soft flag.
  3. completely unrelated text -> NO soft flag.
  4. hard MISATTRIBUTED (verbatim wrong article) -> NO soft flag (hard wins).
  5. VAT-domain case (cite 增值税法第11条, paraphrase 第10条) -> SOFT flag.
  6. unit: _soft_misattribution_check returns None for unrelated candidate.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import Citation
from benchmark.verify import (
    verify_citation, _soft_misattribution_check, _resolve_citation,
    normalize, segment,
)


def _c(code, name, ano, dep=False):
    return Citation(cit_type="law", raw=f"{name}第{ano}条", law_code=code,
                    law_name=name, article_no=ano, deprecated_alias=dep)


def _prefix_clauses(text, frac=0.65):
    """Return a prefix subset of ~frac of `text`'s clauses (joined without
    separators) so forward coverage of `text` by the result lands in the soft
    band [0.50, 0.80)."""
    clauses = segment(normalize(text))
    k = max(1, round(frac * len(clauses)))
    return "".join(clauses[:k])


class SoftMisattributionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        cls.crim_rev = cls.laws["刑法"].revisions[
            list(cls.laws["刑法"].revisions)[-1]]
        cls.gt_232 = cls.crim_rev.articles["232"].content   # cited
        cls.gt_234 = cls.crim_rev.articles["234"].content   # neighbor (same law)
        cls.vat_rev = cls.laws["增值税法"].revisions[
            list(cls.laws["增值税法"].revisions)[-1]]
        cls.vat_10 = cls.vat_rev.articles["10"].content
        cls.vat_11 = cls.vat_rev.articles["11"].content

    def test_soft_fires_on_paraphrased_same_law(self):
        # cite 232, render a moderate subset of 234 -> hard miss, soft hit
        cand = _prefix_clauses(self.gt_234)
        v = verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                            "2025-01-01", self.laws, candidate_text=cand)
        self.assertEqual(v.category, "FABRICATED_GENERIC")
        self.assertEqual(v.score, 0.0)
        self.assertIn("SOFT_MISATTRIBUTED", v.note)
        self.assertIn("234", v.note)  # same-law neighbor label

    def test_soft_absent_for_genuine_partial_cited(self):
        # render a subset of the CITED article (232) -> PARTIAL, not misattr
        cand = _prefix_clauses(self.gt_232)
        v = verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                            "2025-01-01", self.laws, candidate_text=cand)
        self.assertEqual(v.category, "PARTIAL")
        self.assertNotIn("SOFT_MISATTRIBUTED", v.note)

    def test_soft_absent_for_unrelated_text(self):
        cand = "本条所规定的内容纯属虚构不存在于任何现行法律xyz"
        v = verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                            "2025-01-01", self.laws, candidate_text=cand)
        self.assertEqual(v.category, "FABRICATED_GENERIC")
        self.assertNotIn("SOFT_MISATTRIBUTED", v.note)

    def test_soft_absent_when_hard_misattributed(self):
        # full verbatim wrong article -> hard MISATTRIBUTED, no soft flag appended
        v = verify_citation(_c("CRIMINAL_LAW", "刑法", "232"),
                            "2025-01-01", self.laws, candidate_text=self.gt_234)
        self.assertEqual(v.category, "MISATTRIBUTED")
        self.assertNotIn("SOFT_MISATTRIBUTED", v.note)

    def test_soft_vat_domain_paraphrase(self):
        # cite VAT 第11条 (征收率), paraphrase 第10条 (税率) subset
        cand = _prefix_clauses(self.vat_10)
        v = verify_citation(_c("VAT_LAW", "增值税法", "11"),
                            "2026-01-01", self.laws, candidate_text=cand)
        self.assertEqual(v.category, "FABRICATED_GENERIC")
        self.assertEqual(v.score, 0.0)
        self.assertIn("SOFT_MISATTRIBUTED", v.note)
        self.assertIn("10", v.note)

    def test_function_returns_none_for_unrelated(self):
        resolved = _resolve_citation(self.laws,
                                     _c("CRIMINAL_LAW", "刑法", "232"),
                                     "2025-01-01")
        res = _soft_misattribution_check(self.laws, resolved,
                                         "虚构条文xyz不存在", "232")
        self.assertIsNone(res)


if __name__ == "__main__":
    unittest.main()
