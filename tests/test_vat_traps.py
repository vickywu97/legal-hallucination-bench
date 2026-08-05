"""VAT-law trap validation (Phase 2 — 增值税法 domain).

These tests prove the 张冠李戴 (MISATTRIBUTED) engine actually fires on the
three VAT trap questions added in questions.json (Q16/Q17/Q18), and lock in
two invariants discovered while building them:

  1. The extractor must recognise ``《增值税法》`` (registered alias of
     VAT_LAW) so a VAT citation resolves instead of falling to NOT_FOUND.
  2. VAT_LAW only comes into force on/after 2026-01-01, so any VAT citation
     resolved at the default as_of 2025-01-01 returns NOT_FOUND. The trap
     questions therefore carry ``as_of_date: "2026-01-01"`` — this test guards
     that gate so a future edit can't silently break the traps.

MISATTRIBUTED fires when a model cites article N but renders a DIFFERENT
verified article M's text (same-law cov >= 0.80). See benchmark/verify.py
``_cross_check_misattribution``.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import Citation
from benchmark.verify import verify_citation, EXACT, FABRICATED
from benchmark.pipeline import run_answer


def _vat(laws, ano):
    """Return verified content of a VAT_LAW article (keyed by Chinese name)."""
    rev = laws["增值税法"].revisions[list(laws["增值税法"].revisions)[-1]]
    return rev.articles[ano].content


def _c(code, name, ano):
    return Citation(cit_type="law", raw=f"{name}第{ano}条", law_code=code,
                    law_name=name, article_no=ano)


class VatMisattributionUnitTests(unittest.TestCase):
    """Cite the *correct* article number but render a *confusable* article's
    verified text -> MISATTRIBUTED (张冠李戴). This is the exact failure the
    Q16/Q17/Q18 traps are designed to catch."""

    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        cls.gt10 = _vat(cls.laws, "10")   # 税率表 (13%/9%/6%)
        cls.gt11 = _vat(cls.laws, "11")   # 征收率 3%
        cls.gt21 = _vat(cls.laws, "21")   # 留抵税额结转/退还
        cls.gt22 = _vat(cls.laws, "22")   # 不得抵扣进项税额
        cls.gt23 = _vat(cls.laws, "23")   # 起征点免征
        cls.gt24 = _vat(cls.laws, "24")   # 免税项目列举

    def _v(self, cited_ano, rendered_text):
        return verify_citation(_c("VAT_LAW", "增值税法", cited_ano),
                               "2026-01-01", self.laws,
                               candidate_text=rendered_text)

    # --- Q16: 税率(第10条) vs 征收率(第11条) -------------------------------
    def test_q16_trap_fires(self):
        # cite 第11条 but render 第10条 (税率表) -> same-law 张冠李戴
        v = self._v("11", self.gt10)
        self.assertEqual(v.diff_level, FABRICATED)
        self.assertEqual(v.category, "MISATTRIBUTED")
        self.assertIn("same law", v.note)

    def test_q16_clean_pass(self):
        v = self._v("11", self.gt11)
        self.assertEqual(v.diff_level, EXACT)
        self.assertEqual(v.verdict, "OK")

    # --- Q17: 起征点(第23条) vs 免税项目(第24条) ---------------------------
    def test_q17_trap_fires(self):
        v = self._v("23", self.gt24)
        self.assertEqual(v.category, "MISATTRIBUTED")

    def test_q17_clean_pass(self):
        v = self._v("23", self.gt23)
        self.assertEqual(v.diff_level, EXACT)

    # --- Q18: 不得抵扣(第22条) vs 留抵退税(第21条) -------------------------
    def test_q18_trap_fires(self):
        v = self._v("22", self.gt21)
        self.assertEqual(v.category, "MISATTRIBUTED")

    def test_q18_clean_pass(self):
        v = self._v("22", self.gt22)
        self.assertEqual(v.diff_level, EXACT)


class VatAsOfGateTests(unittest.TestCase):
    """VAT_LAW is effective 2026-01-01. Resolving it at 2025-01-01 (the default
    as_of for the other 15 questions) must NOT find the article — which would
    turn every VAT trap into a bland NOT_FOUND instead of a 张冠李戴. The trap
    questions set as_of_date=2026-01-01 to avoid this."""

    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()

    def test_pre_effective_is_not_found(self):
        v = verify_citation(_c("VAT_LAW", "增值税法", "11"),
                            "2025-01-01", self.laws)
        self.assertEqual(v.verdict, "HALLUCINATION")
        self.assertEqual(v.category, "NOT_FOUND")

    def test_post_effective_resolves(self):
        v = verify_citation(_c("VAT_LAW", "增值税法", "11"),
                            "2026-01-01", self.laws)
        self.assertEqual(v.verdict, "OK")
        self.assertEqual(v.category, "CITATION_OK")


class VatEndToEndTests(unittest.TestCase):
    """The full extract -> verify path must recognise ``《增值税法》`` and flag
    a wrong-article quote. Mirrors how the real pipeline consumes model output
    (citation extracted from free text, candidate window grabbed after it)."""

    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        cls.gt11 = _vat(cls.laws, "11")   # short -> fits in candidate window

    def test_extractor_recognizes_vat_and_flags_misattribution(self):
        # cite 第10条 but render 第11条 text -> MISATTRIBUTED through the pipeline
        passage = "根据《增值税法》第10条，" + self.gt11
        vs = run_answer(passage, "2026-01-01", laws=self.laws, question_id="Q16")
        self.assertTrue(any(v.category == "MISATTRIBUTED" for v in vs),
                        f"expected MISATTRIBUTED, got {[v.category for v in vs]}")

    def test_extractor_clean_exact(self):
        passage = "根据《增值税法》第11条，" + self.gt11
        vs = run_answer(passage, "2026-01-01", laws=self.laws, question_id="Q16")
        self.assertTrue(any(v.diff_level == EXACT for v in vs),
                        f"expected EXACT, got {[v.diff_level for v in vs]}")


if __name__ == "__main__":
    unittest.main()
