"""Tests for the Week-3 citation extractor.

Two kinds of checks:
  1. Behavioural unit tests (cn2int, ranges, deprecated-alias trap,
     no false positives, suspected heuristic).
  2. Labelled-set recall/precision gates: on benchmark/fixtures/extract_sample.json
     the extractor MUST reach recall >= 95% and precision >= 90%. Suspected
     (heuristic-only) citations are excluded from both denominators — they are
     an audit signal, not part of the strict pass/fail budget.
"""
import json
import os
import unittest

from benchmark.extract import extract, cn2int

FIXTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "benchmark", "fixtures", "extract_sample.json")


def _match(c, g) -> bool:
    if c.cit_type != g["type"]:
        return False
    if g["type"] == "law":
        return c.law_code == g.get("law_code", "") and c.article_no == g.get("article_no", "")
    if g["type"] == "interpretation":
        return c.doc_no == g.get("doc_no", "")
    if g["type"] in ("guiding_case", "case_no"):
        return c.case_no == g.get("case_no", "")
    return False


class TestCn2Int(unittest.TestCase):
    def test_basic(self):
        self.assertEqual(cn2int("五百八十四"), 584)
        self.assertEqual(cn2int("一千一百六十五"), 1165)
        self.assertEqual(cn2int("十"), 10)
        self.assertEqual(cn2int("一百零八"), 108)

    def test_arabic(self):
        self.assertEqual(cn2int("113"), 113)


class TestExtraction(unittest.TestCase):
    def test_range(self):
        cs = extract("依据《公司法》第20条至第22条。")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].article_no, "20-22")
        self.assertEqual(cs[0].law_code, "COMPANY_LAW")

    def test_deprecated_alias_flag(self):
        cs = extract("原告依据合同法第107条主张违约责任。")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].law_code, "CIVIL_CODE")
        self.assertTrue(cs[0].deprecated_alias)

    def test_old_company_law_trap(self):
        cs = extract("旧公司法第13条曾规定此事。")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].law_code, "COMPANY_LAW")
        self.assertTrue(cs[0].deprecated_alias)

    def test_no_false_positive(self):
        self.assertEqual(extract("今天天气真好，我们去吃饭吧。"), [])
        self.assertEqual(extract("我们讨论了项目进度。"), [])

    def test_suspected_heuristic(self):
        cs = extract("民法典规定了违约责任的相关条款，应予适用。")
        susp = [c for c in cs if c.suspected]
        self.assertTrue(susp)
        self.assertEqual(susp[0].cit_type, "suspected")
        self.assertEqual(susp[0].law_code, "CIVIL_CODE")

    def test_no_suspected_without_token(self):
        cs = extract("根据刑法，故意杀人的应受处罚。")
        self.assertEqual(cs, [])

    def test_bare_numeral(self):
        cs = extract("参见第五百八十四条关于损害赔偿。")
        self.assertEqual(len(cs), 1)
        self.assertEqual(cs[0].article_no, "584")
        self.assertEqual(cs[0].law_code, "")


class TestLabelledRecallPrecision(unittest.TestCase):
    def setUp(self):
        with open(FIXTURE, encoding="utf-8") as f:
            self.fixtures = json.load(f)

    def _metrics(self):
        total_gold = 0
        matched_gold = 0
        total_strict_extracted = 0
        matched_extracted = 0
        for fx in self.fixtures:
            gold = fx["expect"]
            cs = extract(fx["text"])
            strict = [c for c in cs if not c.suspected]
            total_gold += len(gold)
            total_strict_extracted += len(strict)
            for g in gold:
                if any(_match(c, g) for c in strict):
                    matched_gold += 1
            for c in strict:
                if any(_match(c, g) for g in gold):
                    matched_extracted += 1
        recall = matched_gold / total_gold if total_gold else 1.0
        precision = matched_extracted / total_strict_extracted if total_strict_extracted else 1.0
        return recall, precision, total_gold, total_strict_extracted

    def test_recall(self):
        recall, precision, g, e = self._metrics()
        print(f"\n[extract] gold={g} strict_extracted={e} recall={recall:.3f} precision={precision:.3f}")
        self.assertGreaterEqual(recall, 0.95)

    def test_precision(self):
        recall, precision, g, e = self._metrics()
        self.assertGreaterEqual(precision, 0.90)


if __name__ == "__main__":
    unittest.main()
