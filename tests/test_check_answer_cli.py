# -*- coding: utf-8 -*-
"""End-to-end tests for the offline answer-checker CLI (scripts/check_answer.py).

Exercises both the importable core (check_single) and the real CLI subprocess,
asserting the v1.3 detectors are reachable through the product surface.
"""
import json
import os
import subprocess
import sys
import unittest

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CLI = os.path.join(REPO, "scripts", "check_answer.py")
sys.path.insert(0, os.path.join(REPO, "scripts"))

import check_answer  # noqa: E402


class CheckAnswerCLITest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = check_answer.load_laws()
        cls.questions = check_answer.load_questions()

    def test_fabricated_case_detected(self):
        ans = ("根据《民法典》第584条，当事人一方不履行合同义务或者履行合同义务"
               "不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成"
               "的损失，包括合同履行后可以获得的利益。另可参见指导案例第999号佐证。")
        vs, _ = check_answer.check_single("Q24", ans, self.laws, self.questions)
        cats = {v.category for v in vs}
        self.assertIn("FABRICATED_CASE", cats)

    def test_gold_answer_clean(self):
        # Clean gold (cite Q24 verbatim; no embedded article text to avoid
        # nested-citation artifacts) must not trip the high-precision traps.
        gold = "根据《民法典》第584条。"
        vs, _ = check_answer.check_single("Q24", gold, self.laws, self.questions)
        cats = {v.category for v in vs}
        # High-precision traps must stay silent on a verbatim quote.
        self.assertNotIn("FABRICATED_CASE", cats)
        self.assertNotIn("CIRCULAR_CITATION", cats)
        # SELF_CONTRADICTION is a low-precision diagnostic nudge (never scored);
        # it may surface on a statute quote containing a limitation clause, so
        # it is intentionally not asserted here.

    def test_cli_subprocess_fabricated(self):
        ans = ("根据《民法典》第584条，当事人一方不履行合同义务或者履行合同义务"
               "不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成"
               "的损失。另可参见指导案例第999号佐证。")
        out = subprocess.run(
            [sys.executable, CLI, "--question", "Q24", "--answer", ans],
            capture_output=True, text=True, cwd=REPO)
        self.assertEqual(out.returncode, 0, out.stderr)
        self.assertIn("FABRICATED_CASE", out.stdout)
        self.assertIn("HVI", out.stdout)  # summary block present

    def test_cli_json_format(self):
        out = subprocess.run(
            [sys.executable, CLI, "--question", "Q24",
             "--answer", "参见指导案例第999号。",
             "--format", "json"],
            capture_output=True, text=True, cwd=REPO)
        self.assertEqual(out.returncode, 0, out.stderr)
        data = json.loads(out.stdout)
        self.assertEqual(data["question_id"], "Q24")
        self.assertIn("verifications", data)
        self.assertIn("metrics", data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
