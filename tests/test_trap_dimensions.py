"""Tests for the v1.3 answer-level trap dimensions (benchmark/answer_checks.py).

Covers the three new dimensions end-to-end:
  - 编造判例  (fabricated case law): FABRICATED_CASE / CASE_OK / UNVERIFIABLE_CASE
  - 循环引注  (circular citation):   CIRCULAR_CITATION
  - 自相矛盾  (self-contradiction):  SELF_CONTRADICTION (diagnostic only)
plus pipeline integration (run_answer / audit -> hr_case metric).
"""
import os
import sys
import unittest
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import extract, Citation
from benchmark.answer_checks import (
    verify_cases, detect_circular_citation, detect_self_contradiction,
    run_answer_checks, CASE_OK, FABRICATED_CASE, UNVERIFIABLE_CASE,
    CIRCULAR_CITATION, SELF_CONTRADICTION,
)
from benchmark.pipeline import run_answer, audit
from benchmark.score import score


class TestFabricatedCase(unittest.TestCase):
    def test_guiding_case_in_registry_is_ok(self):
        cites = extract("可参见指导案例第1号确立的规则。")
        vs = verify_cases(cites)
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].category, CASE_OK)
        self.assertEqual(vs[0].verdict, "OK")
        self.assertEqual(vs[0].hardness, "answer")

    def test_guiding_case_out_of_registry_is_fabricated(self):
        cites = extract("参见指导案例第999号支持本观点。")
        vs = verify_cases(cites)
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].category, FABRICATED_CASE)
        self.assertEqual(vs[0].verdict, "HALLUCINATION")
        self.assertEqual(vs[0].score, 0.0)

    def test_case_number_is_unverifiable_transparent(self):
        cites = extract("（2021）最高法民终12345号案亦持相同观点。")
        vs = verify_cases(cites)
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].category, UNVERIFIABLE_CASE)
        self.assertEqual(vs[0].verdict, "UNVERIFIABLE")

    def test_mixed_answer(self):
        cites = extract("指导案例第1号与（2020）京01民初5号均支持；另见指导案例第888号。")
        cats = {v.category for v in verify_cases(cites)}
        self.assertEqual(cats, {CASE_OK, UNVERIFIABLE_CASE, FABRICATED_CASE})


class TestCircularCitation(unittest.TestCase):
    def _fake_resolve(self, cycle):
        def _resolve(laws, name, ano, as_of_date):
            # content references the OTHER article in the cycle -> closed loop
            ref = cycle[1] if ano == cycle[0] else cycle[0]
            content = f"依照本法第{ref}条的规定处理。" if cycle else ""
            return SimpleNamespace(found=True, verification_status="verified",
                                   content=content, note="", article_no=ano)
        return _resolve

    def test_cycle_detected(self):
        from benchmark import answer_checks
        orig = answer_checks.resolve_article
        answer_checks.resolve_article = self._fake_resolve(("15", "16"))
        try:
            cites = [Citation(cit_type="law", raw="公司法第15条", law_name="公司法",
                              article_no="15", law_code="COMPANY_LAW"),
                     Citation(cit_type="law", raw="公司法第16条", law_name="公司法",
                              article_no="16", law_code="COMPANY_LAW")]
            v = detect_circular_citation(cites, load_laws())
            self.assertIsNotNone(v)
            self.assertEqual(v.category, CIRCULAR_CITATION)
            self.assertEqual(v.verdict, "HALLUCINATION")
        finally:
            answer_checks.resolve_article = orig

    def test_no_cycle_is_none(self):
        from benchmark import answer_checks
        orig = answer_checks.resolve_article

        def _resolve(laws, name, ano, as_of_date):
            # no cross-reference into the cited set
            return SimpleNamespace(found=True, verification_status="verified",
                                   content="本条自为一体，不援引他条。",
                                   note="", article_no=ano)
        answer_checks.resolve_article = _resolve
        try:
            cites = [Citation(cit_type="law", raw="公司法第15条", law_name="公司法",
                              article_no="15", law_code="COMPANY_LAW")]
            self.assertIsNone(detect_circular_citation(cites, load_laws()))
        finally:
            answer_checks.resolve_article = orig

    def test_deprecated_alias_excluded(self):
        cites = [Citation(cit_type="law", raw="旧公司法第3条", law_name="旧公司法",
                          article_no="3", law_code="COMPANY_LAW", deprecated_alias=True)]
        self.assertIsNone(detect_circular_citation(cites, load_laws()))


class TestSelfContradiction(unittest.TestCase):
    def test_contradictory_flagged(self):
        text = "买方应当先付款。但买方无需先付款，出卖人不得拒绝发货。"
        v = detect_self_contradiction(text)
        self.assertIsNotNone(v)
        self.assertEqual(v.category, SELF_CONTRADICTION)
        # diagnostic only: never a hallucination verdict
        self.assertEqual(v.verdict, "OK")

    def test_consistent_is_none(self):
        text = "买方应当先付款。出卖人收到款后方可发货。"
        self.assertIsNone(detect_self_contradiction(text))

    def test_empty_is_none(self):
        self.assertIsNone(detect_self_contradiction(""))


class TestPipelineIntegration(unittest.TestCase):
    def test_run_answer_appends_answer_level(self):
        laws = load_laws()
        rev = laws["民法典"].revisions[list(laws["民法典"].revisions)[-1]]
        gt584 = rev.articles["584"].content
        answer = ("根据《民法典》第584条，" + gt584 +
                  " 另可参见指导案例第999号佐证。")
        # map each statutory (law) citation index -> the verbatim article text
        # so the content-diff can score it EXACT.
        cs = extract(answer)
        gc = {i: gt584 for i, c in enumerate(cs) if c.cit_type == "law"}
        vs = run_answer(answer, "2025-01-01", laws=laws,
                        gold_candidates=gc, question_id="Q24")
        cats = {v.category for v in vs}
        self.assertIn("EXACT", cats)            # 584 verbatim
        self.assertIn(FABRICATED_CASE, cats)    # 指导案例999号
        # guiding-case citations must NOT leak a spurious statutory NOT_FOUND
        self.assertNotIn("NOT_FOUND",
                         {v.category for v in vs if v.hardness == "hard"})

    def test_audit_hr_case_metric(self):
        laws = load_laws()
        rev = laws["民法典"].revisions[list(laws["民法典"].revisions)[-1]]
        gt584 = rev.articles["584"].content
        records = [
            {"model": "BadModel", "question_id": "Q24", "as_of_date": "2025-01-01",
             "answer": "根据《民法典》第584条，" + gt584 + " 参见指导案例第999号。"},
            {"model": "GoodModel", "question_id": "Q24", "as_of_date": "2025-01-01",
             "answer": "根据《民法典》第584条，" + gt584 + " 参见指导案例第1号。"},
        ]
        result = audit(records, laws=laws)
        bad = result["BadModel"]["report"].metrics
        good = result["GoodModel"]["report"].metrics
        self.assertEqual(bad["hr_case"], 1.0)    # 999 -> fabricated
        self.assertEqual(good["hr_case"], 0.0)   # 1 -> ok
        # statutory HVI must stay clean (answer-level findings excluded)
        self.assertNotIn("FABRICATED_CASE", {
            v.category for v in result["BadModel"]["verifications"]
            if v.hardness == "hard"})

    def test_run_answer_checks_helper_sets_question_id(self):
        laws = load_laws()
        answer = "参见指导案例第7号与（2019）沪02民终1号。"
        cites = extract(answer)
        vs = run_answer_checks(answer, cites, "2025-01-01", laws=laws,
                               question_id="QX")
        self.assertTrue(vs)
        self.assertTrue(all(v.question_id == "QX" for v in vs))


if __name__ == "__main__":
    unittest.main()
