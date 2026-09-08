"""Tests for the expanded trap dimensions (v1.4): tampered article number,
tampered figure inside a correct citation, and citing a repealed law whose
content is still correct.

All assertions run fully offline against the verified KB — no model, no API.
"""
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from knowledge_base.loader import load_laws  # noqa: E402
from benchmark.pipeline import run_answer  # noqa: E402


class TestExpandedTraps(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.laws = load_laws()

    def _cats(self, answer):
        vs = run_answer(answer, "2025-01-01", laws=self.laws, question_id="QA")
        return [(v.verdict, v.category) for v in vs]

    _HALLUC = "HALLUCINATION"
    _FAB_CATS = ("PARTIAL", "TRUNCATED", "MISATTRIBUTED", "FABRICATED_GENERIC")

    # ---- Q27: tampered article number (real but wrong article) -------------
    def test_tampered_article_number_caught(self):
        ans = ("根据《民法典》第585条，当事人一方不履行合同义务或者履行合同义务"
               "不符合约定，给对方造成损失的，损失赔偿额应当相当于因违约所造成"
               "的损失，包括合同履行后可以获得的利益。")
        vs = run_answer(ans, "2025-01-01", laws=self.laws, question_id="Q27")
        # 585 is about liquidated-damages agreements, not damages measurement;
        # quoting 584's text under 585's number is a content mismatch -> caught.
        self.assertTrue(
            any(v.verdict == self._HALLUC for v in vs),
            f"篡改条号未被捕获: {[(v.verdict, v.category) for v in vs]}")
        self.assertTrue(
            any(v.category in self._FAB_CATS for v in vs),
            f"篡改条号未归为内容失真类: {[(v.verdict, v.category) for v in vs]}")

    # ---- Q28: tampered figure inside a correctly-cited article -------------
    def test_tampered_figure_caught(self):
        ans = ("根据《民法典》第584条，当事人一方不履行合同义务或者履行合同义务"
               "不符合约定，给对方造成损失的，损失赔偿额应当相当于因违约所造成"
               "的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立"
               "合同时预见到或者应当预见到的因违约可能造成的损失的千分之三。")
        vs = run_answer(ans, "2025-01-01", laws=self.laws, question_id="Q28")
        # 千分之三 (3‰) tampered from the official 30%; same article number,
        # distorted quote -> caught as a content fabrication.
        self.assertTrue(
            any(v.verdict == self._HALLUC for v in vs),
            f"篡改数字未被捕获: {[(v.verdict, v.category) for v in vs]}")
        self.assertTrue(
            any(v.category in self._FAB_CATS for v in vs),
            f"篡改数字未归为内容失真类: {[(v.verdict, v.category) for v in vs]}")

    # ---- Q29: repealed law with correct content -> still temporal ----------
    def test_repealed_law_content_correct_still_temporal(self):
        ans = ("根据《合同法》第107条，当事人一方不履行合同义务或者履行合同义务"
               "不符合约定的，应当承担继续履行、采取补救措施或者赔偿损失等"
               "违约责任。")
        cats = self._cats(ans)
        self.assertIn("TEMPORAL_DEPRECATED", [cat for _, cat in cats],
                      f"引用失效法未被判时序幻觉: {cats}")

    # ---- sanity: the genuine gold answers for the 3 new traps pass --------
    def test_gold_answers_pass(self):
        from knowledge_base.loader import resolve_article
        from benchmark.verify import _code_to_name
        cases = [("CIVIL_CODE", "584"), ("CIVIL_CODE", "584"), ("CIVIL_CODE", "577")]
        for code, ano in cases:
            name = _code_to_name(code)
            r = resolve_article(self.laws, name, ano, "2025-01-01")
            self.assertTrue(r.found and r.verification_status == "verified",
                            f"{name}{ano} 未核验")
            gold = f"根据《{name}》第{ano}条，{r.content}"
            cats = self._cats(gold)
            self.assertIn("EXACT", [cat for _, cat in cats],
                          f"金标准未判 EXACT: {name}{ano} -> {cats}")


if __name__ == "__main__":
    unittest.main()
