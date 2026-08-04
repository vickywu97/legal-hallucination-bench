"""Tests for the Week-5/6 end-to-end offline pipeline (benchmark/pipeline.py).

Verifies the extract -> verify -> score -> report chain on synthetic model
answers: a careful model (EXACT, HR=0%), a hallucinating model
(MISATTRIBUTED + TEMPORAL_DEPRECATED + NOT_FOUND, HR=100%), and a partial model
(cites 232 but omits the last clause -> PARTIAL, HR=100%). Also covers the
candidate_window heuristics and the audit/report artifacts (with temp cleanup).
"""
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import extract
from benchmark.pipeline import (
    candidate_window, run_answer, audit, build_report,
)


class CandidateWindowTests(unittest.TestCase):
    def test_skips_leading_punctuation(self):
        text = "根据《刑法》第232条，故意杀人的处死刑。"
        c = extract(text)[0]
        self.assertTrue(candidate_window(text, c.span).startswith("故意杀人的"))

    def test_stops_at_next_citation(self):
        text = "根据《刑法》第232条，故意杀人。\n《民法典》第584条，损失赔偿。"
        c = extract(text)[0]
        w = candidate_window(text, c.span)
        self.assertIn("故意杀人", w)
        self.assertNotIn("损失赔偿", w)

    def test_no_next_citation_uses_window(self):
        text = "根据《刑法》第232条，故意杀人的处死刑、无期徒刑。"
        c = extract(text)[0]
        w = candidate_window(text, c.span)
        self.assertIn("故意杀人的处死刑", w)


class PipelineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()
        rev = cls.laws["刑法"].revisions[list(cls.laws["刑法"].revisions)[-1]]
        cls.gt232 = rev.articles["232"].content
        cls.gt234 = rev.articles["234"].content

    def setUp(self):
        self._tmp = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self._tmp, ignore_errors=True)

    def test_good_answer_exact(self):
        ans = "根据《刑法》第232条，" + self.gt232
        vs = run_answer(ans, "2025-01-01", laws=self.laws)
        self.assertTrue(vs)
        self.assertTrue(all(v.verdict == "OK" for v in vs))
        self.assertTrue(any(v.diff_level == "EXACT" for v in vs))
        # candidate + ground_truth flow into the Verification (for reporting)
        v = vs[0]
        self.assertTrue(v.candidate)
        self.assertTrue(v.ground_truth)

    def test_partial_scenario(self):
        # cite 232 correctly but drop the last clause -> partial omission.
        # Under the binary policy this is FABRICATED (still HALLUCINATION,
        # diagnostic category PARTIAL), score 0.0 -- no partial credit.
        partial = "；".join(self.gt232.split("；")[:-1])
        ans = "根据《刑法》第232条，" + partial
        vs = run_answer(ans, "2025-01-01", laws=self.laws)
        v232 = [v for v in vs if "232" in v.citation_raw][0]
        self.assertEqual(v232.verdict, "HALLUCINATION")
        self.assertEqual(v232.category, "PARTIAL")
        self.assertEqual(v232.diff_level, "FABRICATED")
        self.assertEqual(v232.score, 0.0)
        self.assertTrue(v232.candidate and v232.ground_truth)

    def test_misattributed_detected(self):
        ans = "根据《刑法》第232条，" + self.gt234
        vs = run_answer(ans, "2025-01-01", laws=self.laws)
        v232 = [v for v in vs if "232" in v.citation_raw][0]
        self.assertEqual(v232.verdict, "HALLUCINATION")
        self.assertEqual(v232.category, "MISATTRIBUTED")

    def test_temporal_and_not_found(self):
        ans = ("《旧公司法》第3条规定公司是企业法人。"
               "\n《公司法》第13条，法定代表人由董事会选举产生。")
        vs = run_answer(ans, "2025-01-01", laws=self.laws)
        cats = {v.category for v in vs}
        self.assertIn("TEMPORAL_DEPRECATED", cats)
        self.assertIn("NOT_FOUND", cats)

    def test_audit_and_report(self):
        records = [
            {"model": "A", "as_of_date": "2025-01-01",
             "answer": "根据《刑法》第232条，" + self.gt232},
            {"model": "B", "as_of_date": "2025-01-01",
             "answer": ("根据《刑法》第232条，" + self.gt234 +
                        "\n《旧公司法》第3条规定公司是企业法人。")},
            {"model": "C", "as_of_date": "2025-01-01",
             "answer": "根据《刑法》第232条，" +
                       "；".join(self.gt232.split("；")[:-1])},  # partial omission (now FABRICATED, score 0.0)
        ]
        res = audit(records, laws=self.laws)
        self.assertEqual(res["A"]["report"].metrics["hr_statutory"], 0.0)
        # B cites 旧公司法第3条 (TEMPORAL_DEPRECATED) + 刑法232 w/ wrong text
        # (MISATTRIBUTED, content-only) -> HVI = 1/2 = 0.5
        self.assertEqual(res["B"]["report"].metrics["hr_statutory"], 0.5)
        # C's only citation is a content truncation (no existence/temporal error)
        # -> HVI = 0.0
        self.assertEqual(res["C"]["report"].metrics["hr_statutory"], 0.0)
        self.assertEqual(res["C"]["report"].metrics["hr_content"], 1.0)
        # CRFI isolates MISATTRIBUTED: only B has one (刑法232 + gt234)
        self.assertEqual(res["A"]["report"].metrics["crfi"], 0.0)
        self.assertEqual(res["B"]["report"].metrics["crfi"], 1.0)
        self.assertEqual(res["C"]["report"].metrics["crfi"], 0.0)
        # build_report writes the artifacts
        build_report(res, self._tmp)
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "leaderboard.json")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "leaderboard.md")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "verifications.jsonl")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "audit_A.md")))
        self.assertTrue(os.path.exists(os.path.join(self._tmp, "audit_C.md")))
        # report carries candidate vs ground_truth comparison
        with open(os.path.join(self._tmp, "audit_C.md"), encoding="utf-8") as f:
            ctxt = f.read()
        self.assertIn("逐条对照", ctxt)
        self.assertIn("模型输出（候选）", ctxt)
        self.assertIn("官方原文（基准）", ctxt)


class NullDateRobustnessTests(unittest.TestCase):
    """P0: a record with as_of_date=None (or non-ISO) must not crash and must
    resolve through pipeline.normalize_as_of (defaulting to a post-repeal date
    for deprecated-law citations)."""
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()

    def test_null_as_of_date_deprecated_flagged(self):
        # None -> normalize_as_of(None) -> default 2025-01-01 (post-repeal)
        rec = {"model": "X", "as_of_date": None,
               "answer": "根据旧公司法第3条，公司是企业法人。"}
        res = audit([rec], laws=self.laws)
        vs = res["X"]["verifications"]
        self.assertTrue(any(v.category == "TEMPORAL_DEPRECATED" for v in vs),
                        "deprecated citation under null as_of_date must be flagged")

    def test_non_iso_as_of_date_no_crash(self):
        rec = {"model": "Y", "as_of_date": "2024/06/01",
               "answer": "根据《民法典》第584条，损失赔偿。"}
        res = audit([rec], laws=self.laws)
        vs = res["Y"]["verifications"]
        # citation resolves (no crash); date parsing did not blow up. The
        # heuristic candidate_window text is not verbatim -> FABRICATED, which
        # still proves the non-ISO date survived the diff path.
        self.assertEqual(len(vs), 1)
        self.assertEqual(vs[0].domain, "CIVIL_CODE")
        self.assertNotEqual(vs[0].category, "NOT_FOUND")


if __name__ == "__main__":
    unittest.main()
