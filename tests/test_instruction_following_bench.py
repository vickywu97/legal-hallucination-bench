# -*- coding: utf-8 -*-
"""Tests for the instruction-following benchmark (project C, v0.1 scaffold).

Covers:
* rule-based scorer dims (format / content / closure) on correct & violating outputs
* the offline dummy pipeline runs and emits a leaderboard with the demo note
* closure dimension is triggered by extra explanatory text (no LLM judge involved)
"""
import os
import tempfile
import unittest

from projects.instruction_following_bench import score, run, report


# ---- fixtures (fictional demo data, mirrors config/tasks.json) ----
_T_FORMAT = {
    "id": "T1",
    "type": "format_extraction",
    "expected": {
        "company_name": "云岬智能装备股份有限公司",
        "amount": "1,280,000",
        "date": "2026-07-15",
    },
}
_T_COND = {
    "id": "T2",
    "type": "condition_rule",
    "expected": {"eligible": False, "reason": "餐饮服务进项税额不得抵扣"},
}
_T_FEW = {"id": "T3", "type": "fewshot_classify", "expected": "B"}
_T_MULTI = {
    "id": "T4",
    "type": "multi_turn_constraint",
    "allowed": ["同意", "拒绝"],
    "expected": "拒绝",
}


class ScorerFormatExtractionTests(unittest.TestCase):
    def test_perfect_json_gets_full_score(self):
        out = '{"company_name":"云岬智能装备股份有限公司","amount":"1,280,000","date":"2026-07-15"}'
        r = score.score_task(_T_FORMAT, out)
        self.assertEqual(r["format"], 1.0)
        self.assertEqual(r["content"], 1.0)
        self.assertEqual(r["closure"], 1.0)
        self.assertEqual(r["total"], 1.0)
        self.assertEqual(r["violation_rate"], 0.0)

    def test_missing_field_lowers_format_and_content(self):
        out = '{"company_name":"云岬智能装备股份有限公司"}'  # amount/date missing
        r = score.score_task(_T_FORMAT, out)
        # 1 of 3 fields present -> 1/3, rounded to 4 decimals by the scorer
        self.assertEqual(r["format"], round(1 / 3, 4))
        self.assertEqual(r["content"], round(1 / 3, 4))
        self.assertEqual(r["closure"], 1.0)

    def test_extra_explanation_breaks_closure(self):
        out = '根据文本，{"company_name":"云岬智能装备股份有限公司","amount":"1,280,000","date":"2026-07-15"}'
        r = score.score_task(_T_FORMAT, out)
        self.assertEqual(r["format"], 1.0)
        self.assertEqual(r["content"], 1.0)
        self.assertEqual(r["closure"], 0.0)  # closure violated by leading text
        self.assertAlmostEqual(r["total"], 0.7, places=4)
        self.assertIn("extra explanatory text beyond JSON", r["notes"])


class ScorerConditionRuleTests(unittest.TestCase):
    def test_correct_eligible_false(self):
        out = '{"eligible": false, "reason": "餐饮服务进项税额不得抵扣"}'
        r = score.score_task(_T_COND, out)
        self.assertEqual(r["content"], 1.0)
        self.assertEqual(r["closure"], 1.0)

    def test_empty_reason_drops_content(self):
        # eligible flag correct but required reason empty -> partial (0.5),
        # not full; the scorer awards half credit for the correct boolean.
        out = '{"eligible": false, "reason": ""}'
        r = score.score_task(_T_COND, out)
        self.assertEqual(r["content"], 0.5)

    def test_wrong_eligible_zero_content(self):
        out = '{"eligible": true, "reason": "可抵扣"}'
        r = score.score_task(_T_COND, out)
        self.assertEqual(r["content"], 0.0)


class ScorerFewshotTests(unittest.TestCase):
    def test_exact_label_full_score(self):
        r = score.score_task(_T_FEW, "B")
        self.assertEqual(r["total"], 1.0)
        self.assertEqual(r["closure"], 1.0)

    def test_label_with_rationale_breaks_closure(self):
        r = score.score_task(_T_FEW, "B（服务类）")
        self.assertEqual(r["content"], 1.0)   # core label correct
        self.assertEqual(r["closure"], 0.0)   # extra text beyond label
        self.assertAlmostEqual(r["total"], 0.7, places=4)


class ScorerMultiTurnTests(unittest.TestCase):
    def test_exact_token_full_score(self):
        r = score.score_task(_T_MULTI, "拒绝")
        self.assertEqual(r["total"], 1.0)

    def test_sentence_output_violates(self):
        r = score.score_task(_T_MULTI, "我拒绝你的请求。")
        self.assertEqual(r["format"], 0.0)
        self.assertEqual(r["closure"], 0.0)


class TasksFileTests(unittest.TestCase):
    def test_coverage_minimums(self):
        tasks = run.load_tasks()
        self.assertGreaterEqual(len(tasks), 15)
        types = {t["type"] for t in tasks}
        self.assertEqual(types, {
            "format_extraction", "condition_rule",
            "fewshot_classify", "multi_turn_constraint",
        })
        # every task must carry an explicit difficulty label
        for t in tasks:
            self.assertIn("difficulty", t)


class ReportTests(unittest.TestCase):
    _ROWS = [
        {"model": "DemoA", "tasks": 3, "avg_format": 0.9, "avg_content": 0.8,
         "avg_closure": 1.0, "avg_total": 0.89, "instruction_violation_rate": 0.11},
        {"model": "DemoB", "tasks": 3, "avg_format": 0.2, "avg_content": 0.1,
         "avg_closure": 0.3, "avg_total": 0.18, "instruction_violation_rate": 0.82},
    ]

    def test_demo_html_has_banner_and_models(self):
        h = report.build_html(self._ROWS, "demo")
        self.assertIn("DEMO", h)
        self.assertIn("DemoA", h)
        self.assertIn("DemoB", h)
        self.assertIn("不构成", h)  # disclaimer footer present
        self.assertIn("<html", h)

    def test_real_html_banner(self):
        h = report.build_html(self._ROWS, "real")
        self.assertIn("真实排行榜", h)
        self.assertNotIn("DEMO 脚手架", h)

    def test_write_html_creates_file(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = os.path.join(d, "lb.csv")
            html_path = report.write_html(self._ROWS, "demo", csv_path)
            self.assertTrue(os.path.exists(html_path))
            self.assertTrue(html_path.endswith(".html"))
            with open(html_path, encoding="utf-8") as f:
                self.assertIn("DemoA", f.read())


class OfflinePipelineTests(unittest.TestCase):
    def test_offline_emits_two_dummy_rows(self):
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "leaderboard.csv")
            rows = run.run_offline(out_path=out)
            self.assertEqual(len(rows), 2)
            models = {r["model"] for r in rows}
            self.assertEqual(models, {"RandomBaseline", "EmptyBaseline"})
            self.assertTrue(os.path.exists(out))
            # every row must carry the violation-rate column
            for r in rows:
                self.assertIn("instruction_violation_rate", r)

    def test_score_answers_real_path(self):
        # a tiny real-answers file: one model, one perfect answer
        with tempfile.TemporaryDirectory() as d:
            ans = os.path.join(d, "a.jsonl")
            with open(ans, "w", encoding="utf-8") as f:
                f.write('{"task_id":"T1","model":"DemoModel","answer":"{\\"company_name\\":\\"云岬智能装备股份有限公司\\",\\"amount\\":\\"1,280,000\\",\\"date\\":\\"2026-07-15\\"}"}\n')
            out = os.path.join(d, "lb.csv")
            rows = run.score_answers(ans, out_path=out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["model"], "DemoModel")
            self.assertEqual(rows[0]["avg_total"], 1.0)


if __name__ == "__main__":
    unittest.main()
