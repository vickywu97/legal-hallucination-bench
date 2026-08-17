# -*- coding: utf-8 -*-
"""Tests for the instruction-following benchmark (project C, v0.1 scaffold).

Covers:
* rule-based scorer dims (format / content / closure) on correct & violating outputs
* the offline dummy pipeline runs and emits a leaderboard with the demo note
* closure dimension is triggered by extra explanatory text (no LLM judge involved)
"""
import json
import os
import tempfile
import unittest

from projects.instruction_following_bench import score, run, report, models


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

    def test_missing_field_lowers_content_not_format(self):
        out = '{"company_name":"云岬智能装备股份有限公司"}'  # amount/date missing
        r = score.score_task(_T_FORMAT, out)
        # format = structural compliance (valid JSON object present) -> 1.0,
        # regardless of which keys are present; only 1 of 3 VALUES matched -> content 1/3.
        self.assertEqual(r["format"], 1.0)
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
                f.write('{"task_id":"T1","model":"DemoModel","answer":"{\\"客户\\":\\"瀚海精密机械有限公司\\",\\"应收净额\\":\\"2270000\\",\\"方向\\":\\"借\\"}"}\n')
            out = os.path.join(d, "lb.csv")
            rows = run.score_answers(ans, out_path=out)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["model"], "DemoModel")
            self.assertEqual(rows[0]["avg_total"], 1.0)


class HiddenSetTests(unittest.TestCase):
    _SAMPLE_HIDDEN = [
        {"id": "TH1", "type": "format_extraction",
         "expected": {"supplier": "瀚海精密机械有限公司", "quantity": "240", "result": "合格"}},
        {"id": "TH2", "type": "condition_rule",
         "expected": {"eligible": True, "reason": "应代扣代缴增值税"}},
    ]

    def _write_temp_hidden(self, d):
        p = os.path.join(d, "tasks_hidden.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(self._SAMPLE_HIDDEN, f, ensure_ascii=False)
        return p

    def test_load_hidden_absent_returns_empty(self):
        self.assertEqual(run.load_hidden("/no/such/file.json"), [])

    def test_hidden_excluded_by_default(self):
        public_n = len(run.load_tasks())
        with tempfile.TemporaryDirectory() as d:
            out = os.path.join(d, "lb.csv")
            rows = run.run_offline(out_path=out)
            for r in rows:
                self.assertNotIn("hidden_total", r)
                self.assertEqual(r["tasks"], public_n)

    def test_hidden_included_with_flag(self):
        public_n = len(run.load_tasks())
        with tempfile.TemporaryDirectory() as d:
            hidden_path = self._write_temp_hidden(d)
            out = os.path.join(d, "lb.csv")
            rows = run.run_offline(out_path=out, hidden=True, hidden_path=hidden_path)
            for r in rows:
                self.assertIn("hidden_total", r)
                self.assertEqual(r["tasks"], public_n)
                self.assertEqual(r["hidden_tasks"], len(self._SAMPLE_HIDDEN))

    def test_score_answers_splits_public_and_hidden(self):
        with tempfile.TemporaryDirectory() as d:
            hidden_path = self._write_temp_hidden(d)
            ans = os.path.join(d, "a.jsonl")
            # one public answer (T1 perfect) + one hidden answer (TH1 perfect)
            with open(ans, "w", encoding="utf-8") as f:
                f.write('{"task_id":"T1","model":"M","answer":"{\\"客户\\":\\"瀚海精密机械有限公司\\",\\"应收净额\\":\\"2270000\\",\\"方向\\":\\"借\\"}"}\n')
                f.write('{"task_id":"TH1","model":"M","answer":"{\\"supplier\\":\\"瀚海精密机械有限公司\\",\\"quantity\\":\\"240\\",\\"result\\":\\"合格\\"}"}\n')
            out = os.path.join(d, "lb.csv")
            rows = run.score_answers(ans, out_path=out, hidden=True, hidden_path=hidden_path)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["model"], "M")
            self.assertEqual(rows[0]["avg_total"], 1.0)
            self.assertIn("hidden_total", rows[0])
            self.assertEqual(rows[0]["hidden_total"], 1.0)  # TH1 also perfect

    def test_html_anonymizes_hidden(self):
        rows = [
            {"model": "M", "tasks": 3, "avg_format": 0.9, "avg_content": 0.8,
             "avg_closure": 1.0, "avg_total": 0.89, "instruction_violation_rate": 0.11,
             "hidden_total": 0.55, "hidden_tasks": 2},
        ]
        h = report.build_html(rows, "real", hidden_count=2)
        self.assertIn("隐藏集", h)
        self.assertIn("防刷分", h)
        # hidden task ids must NEVER appear in the public HTML
        self.assertNotIn("TH1", h)
        self.assertNotIn("TH2", h)

    def test_html_no_hidden_column_when_absent(self):
        rows = [
            {"model": "M", "tasks": 3, "avg_format": 0.9, "avg_content": 0.8,
             "avg_closure": 1.0, "avg_total": 0.89, "instruction_violation_rate": 0.11},
        ]
        h = report.build_html(rows, "real", hidden_count=0)
        self.assertNotIn("隐藏集综合", h)


class ModelsCLITests(unittest.TestCase):
    def test_generate_answers_skips_without_keys(self):
        # No API keys in env -> every model skipped, empty records returned.
        tasks = [{"id": "T1", "type": "format_extraction", "instruction": "x",
                  "input": "y", "expected": {}}]
        recs = models.generate_answers(tasks, out_path="/tmp/_ifb_none.jsonl")
        self.assertEqual(recs, [])
        self.assertTrue(os.path.exists("/tmp/_ifb_none.jsonl"))
        with open("/tmp/_ifb_none.jsonl", encoding="utf-8") as f:
            self.assertEqual(f.read().strip(), "")
        os.remove("/tmp/_ifb_none.jsonl")

    def test_generate_answers_respects_model_filter(self):
        # Filter to a non-existent label -> selected set empty, no calls/no keys.
        tasks = [{"id": "T1", "type": "format_extraction", "instruction": "x",
                  "input": "y", "expected": {}}]
        recs = models.generate_answers(
            tasks, models=["NotARealModel"], out_path="/tmp/_ifb_filter.jsonl")
        self.assertEqual(recs, [])
        os.remove("/tmp/_ifb_filter.jsonl")


class HiddenTaskTests(unittest.TestCase):
    """Validation of the REAL held-out set (hidden_tasks.json), not the
    pipeline mechanism (that is covered by HiddenSetTests above).

    The hidden file is git-ignored and only exists locally; on a fresh clone
    without it the suite must not hard-fail, so we skip when the file is absent.
    """
    HIDDEN_PATH = os.path.join(run.HERE, "hidden_tasks.json")

    def _load(self):
        if not os.path.exists(self.HIDDEN_PATH):
            self.skipTest(f"hidden_tasks.json absent (git-ignored local file): {self.HIDDEN_PATH}")
        with open(self.HIDDEN_PATH, encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else data.get("tasks", [])

    def test_hidden_count_and_type_coverage(self):
        hidden = self._load()
        self.assertGreaterEqual(len(hidden), 5)
        types = {t["type"] for t in hidden}
        self.assertGreaterEqual(len(types), 3)  # at least 3 of the 4 task types

    def test_every_hidden_marked_and_has_difficulty(self):
        hidden = self._load()
        for t in hidden:
            self.assertTrue(t.get("hidden"), f"{t.get('id')} missing hidden:true")
            self.assertIn("difficulty", t, f"{t.get('id')} missing difficulty")
            self.assertIn("demo_note", t, f"{t.get('id')} missing demo_note")

    def test_hidden_ids_disjoint_from_public(self):
        hidden = self._load()
        public = run.load_tasks()
        public_ids = {t["id"] for t in public}
        hidden_ids = {t["id"] for t in hidden}
        self.assertTrue(hidden_ids, "hidden set is empty")
        overlap = public_ids & hidden_ids
        self.assertEqual(overlap, set(), f"hidden ids leaked into public set: {overlap}")

    def test_default_load_excludes_hidden(self):
        # Default load_tasks() must only read config/tasks.json and never touch
        # the hidden file (physical isolation).
        public = run.load_tasks()
        self.assertFalse(any(t.get("hidden") for t in public),
                         "public tasks.json must not carry any hidden flag")
        ids = {t["id"] for t in public}
        self.assertNotIn("TH1", ids)  # a known hidden id must not appear publicly


if __name__ == "__main__":
    unittest.main()
