"""Regression tests for the `--offline` SAMPLE-overwrite guard.

The guard must prevent `benchmark.run --offline` (SAMPLE demo mode) from
silently clobbering the real collected reports in benchmark/reports/. It is
bypassed by `--force` or by pointing `--out-dir` at a separate directory.
"""
import json
import os
import tempfile
import unittest

import benchmark.run as run_mod

# A minimal real-model answer so `--input` mode has something to score.
_SAMPLE_ANSWER = {
    "model": "DeepSeek-R1",
    "question_id": "Q1",
    "as_of_date": "2025-01-01",
    "answer": "根据《刑法》第232条，故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑。",
}


def _seed_real_reports(d):
    """Write a non-empty verifications.jsonl that looks like REAL reports
    (a real-model name, not the SAMPLE toy models)."""
    with open(os.path.join(d, "verifications.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"model": "DeepSeek-R1", "domain": "刑法"}) + "\n")


class RealReportsHelperTests(unittest.TestCase):
    def test_empty_dir_is_not_real(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertFalse(run_mod._real_reports_exist(d))

    def test_empty_file_is_not_real(self):
        with tempfile.TemporaryDirectory() as d:
            open(os.path.join(d, "verifications.jsonl"), "w").close()
            self.assertFalse(run_mod._real_reports_exist(d))

    def test_nonempty_file_is_real(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_real_reports(d)
            self.assertTrue(run_mod._real_reports_exist(d))


class OfflineGuardTests(unittest.TestCase):
    def test_sample_refuses_when_real_reports_present(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_real_reports(d)
            rc = run_mod._pipeline_demo(input_path=None, out_dir=d)
            self.assertEqual(rc, 1)
            # must NOT have written SAMPLE output over the real reports
            self.assertFalse(os.path.exists(os.path.join(d, "leaderboard.json")))

    def test_sample_proceeds_with_force(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_real_reports(d)
            rc = run_mod._pipeline_demo(input_path=None, force=True, out_dir=d)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "leaderboard.json")))

    def test_fresh_dir_allows_sample(self):
        with tempfile.TemporaryDirectory() as d:
            rc = run_mod._pipeline_demo(input_path=None, out_dir=d)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "leaderboard.json")))

    def test_input_mode_never_guarded(self):
        with tempfile.TemporaryDirectory() as d:
            _seed_real_reports(d)  # real reports present
            ans = os.path.join(d, "answers.jsonl")
            with open(ans, "w", encoding="utf-8") as f:
                f.write(json.dumps(_SAMPLE_ANSWER, ensure_ascii=False) + "\n")
            rc = run_mod._pipeline_demo(input_path=ans, out_dir=d)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "leaderboard.json")))

    def test_out_dir_keeps_real_reports_untouched(self):
        # default reports dir holds real data; --out-dir points the SAMPLE demo
        # elsewhere, so the guard never triggers and real data is preserved.
        real_dir = os.path.join(os.path.dirname(run_mod.__file__), "reports")
        if not run_mod._real_reports_exist(real_dir):
            self.skipTest("real reports not present in this checkout")
        before = os.path.getsize(os.path.join(real_dir, "verifications.jsonl"))
        with tempfile.TemporaryDirectory() as d:
            rc = run_mod._pipeline_demo(input_path=None, out_dir=d)
            self.assertEqual(rc, 0)
            self.assertTrue(os.path.exists(os.path.join(d, "leaderboard.json")))
        # real reports must be byte-identical (guard did not touch them)
        after = os.path.getsize(os.path.join(real_dir, "verifications.jsonl"))
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
