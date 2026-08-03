"""KB coverage gate (Week 2 — coverage report + threshold floor).

Per-law thresholds are intentionally set as a *floor* to keep CI green today.
During expert curation (build_statute.py) these should be RAISED toward the
~200-article target. The coverage report is also printed as a CI artifact so
the curated snapshot's breadth is visible at a glance.
"""
import os
import sys
import json
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.build_statute import (  # noqa: E402
    _load_statutes,
    coverage,
    print_coverage,
    STATUTES_FILE,
)

# Floor thresholds (nodes per law). Raise as curation grows toward ~200/250.
MIN_NODES = {
    "CIVIL_CODE": 20,
    "COMPANY_LAW": 15,
    "CRIMINAL_LAW": 20,
    "PATENT_LAW": 12,
    "TAX_ADMIN_LAW": 12,
}
MIN_TOTAL = 99


class TestCoverage(unittest.TestCase):
    def setUp(self):
        self.nodes = _load_statutes(STATUTES_FILE)
        self.cov = coverage(self.nodes)

    def test_floor_per_law(self):
        for code, floor in MIN_NODES.items():
            self.assertIn(code, self.cov, f"{code}: missing in coverage")
            self.assertGreaterEqual(
                self.cov[code]["nodes"], floor,
                f"{code}: {self.cov[code]['nodes']} nodes < floor {floor}",
            )

    def test_total_floor(self):
        total = sum(c["nodes"] for c in self.cov.values())
        self.assertGreaterEqual(total, MIN_TOTAL, f"total {total} < {MIN_TOTAL}")

    def test_temporal_trap_present(self):
        # The bench's versioning signal is the temporal-hallucination trap:
        # citing a repealed law name post-repeal must be flagged as a
        # hallucination (旧公司法 / 合同法 / 民法总则 / 侵权责任法 ->
        # TEMPORAL_DEPRECATED). Repealed-law names are kept OUT of
        # laws_index.json (KB stays 100% current-law) and trapped at code level
        # via benchmark.extract.DEPRECATED_LAW_NAMES instead.
        from benchmark.extract import DEPRECATED_LAW_NAMES
        self.assertGreaterEqual(
            len(DEPRECATED_LAW_NAMES), 1,
            "no code-level deprecated-law temporal trap found")
        expected = {
            # Company Law family (repealed 2024-07-01):
            "旧公司法",
            # Civil Code predecessors (all repealed 2021-01-01):
            "合同法", "民法总则", "侵权责任法",
            "物权法", "担保法", "婚姻法", "继承法", "收养法", "民法通则",
        }
        self.assertTrue(
            expected.issubset(set(DEPRECATED_LAW_NAMES)),
            f"missing repealed-law traps: {expected - set(DEPRECATED_LAW_NAMES)}")
        index_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge_base", "laws", "laws_index.json")
        with open(index_path, encoding="utf-8") as f:
            index = json.load(f)
        # Single source of truth for repealed-law names is now code-level
        # benchmark.extract.DEPRECATED_LAW_NAMES — the index must NOT carry a
        # deprecated_aliases field at all (KB stays 100% current-law).
        has_dep_key = any("deprecated_aliases" in meta for meta in index.values())
        self.assertFalse(
            has_dep_key,
            "laws_index.json must not carry deprecated_aliases; "
            "repealed-law traps live in DEPRECATED_LAW_NAMES")

    def test_report_prints(self):
        print_coverage(self.nodes)  # CI artifact


if __name__ == "__main__":
    unittest.main()
