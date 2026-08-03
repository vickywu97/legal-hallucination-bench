"""JSONL adapter tests (Week 1 verification gate).

Three things must hold for the locked ``laws_index.json`` + ``statutes.jsonl``
schema to be trustworthy:

1. The adapter-synthesized in-memory model is *functionally equivalent* to the
   documented temporal-resolution behaviour (same queries -> same conclusions).
2. Time windows are left-closed / right-open and **gap-free / overlap-free**
   along each ``(law_code, article_sort_key)`` timeline.
3. Every ``revision_of`` back-pointer resolves to an existing node, and a
   successor is always strictly later in time (no inverted / dangling chains).
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import (  # noqa: E402
    load_laws,
    load_from_jsonl,
    resolve_article,
)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LAWS_DIR = os.path.join(ROOT, "knowledge_base", "laws")
INDEX_PATH = os.path.join(LAWS_DIR, "laws_index.json")
JSONL_PATH = os.path.join(LAWS_DIR, "statutes.jsonl")


# --------------------------------------------------------------------------- #
# 1. Functional equivalence
# --------------------------------------------------------------------------- #
class TestAdapterEquivalence(unittest.TestCase):
    def setUp(self):
        self.laws = load_laws()

    def test_load_from_jsonl_matches_load_laws(self):
        alt = load_from_jsonl(INDEX_PATH, JSONL_PATH)
        self.assertEqual(set(alt.keys()), set(self.laws.keys()))

    def test_civil_584_current(self):
        r = resolve_article(self.laws, "民法典", "584", "2025-01-01")
        self.assertTrue(r.found)
        self.assertIn("损失赔偿额", r.content)

    def test_repealed_law_alias_resolves(self):
        # "合同法" is an alias of CIVIL_CODE (repealed-law name capture).
        r = resolve_article(self.laws, "合同法", "584", "2025-01-01")
        self.assertTrue(r.found)
        self.assertIn("损失赔偿额", r.content)

    def test_old_company_law_article_purged_even_pre_repeal(self):
        # The 2018 Company Law revision (incl. old art.13) was purged, so there
        # is no Company Law revision in force at 2020-01-01 in the KB -> the law
        # is not in force at that date (not silently resolved to a stale node).
        r = resolve_article(self.laws, "公司法", "13", "2020-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "LAW_NOT_IN_FORCE_AT_DATE")

    def test_relocated_article_absent_in_new_revision(self):
        # Old art.13 relocated to art.10; citing art.13 against the new law
        # must NOT silently resolve — it is "not in this revision".
        r = resolve_article(self.laws, "公司法", "13", "2025-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "ARTICLE_NOT_IN_THIS_REVISION")

    def test_new_company_law_in_force_2025(self):
        r = resolve_article(self.laws, "公司法", "10", "2025-01-01")
        self.assertTrue(r.found)
        self.assertEqual(r.revision_id, "COMPANY_LAW@2024-07-01")
        self.assertIn("代表公司执行公司事务", r.content)

    def test_boundary_2024_07_01_new_law_wins(self):
        # At the exact effective date the new Company Law is in force.
        r = resolve_article(self.laws, "公司法", "3", "2024-07-01")
        self.assertTrue(r.found)
        self.assertIn("公司的合法权益受法律保护", r.content)

    def test_unknown_law(self):
        r = resolve_article(self.laws, "不存在的法律", "1", "2025-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "UNKNOWN_LAW")


# --------------------------------------------------------------------------- #
# 2 & 3. Source-data integrity (independent of the loader synthesis)
# --------------------------------------------------------------------------- #
def _read_nodes():
    import json as _json
    with open(JSONL_PATH, "r", encoding="utf-8") as f:
        return [_json.loads(line) for line in f if line.strip()]


class TestStatutesIntegrity(unittest.TestCase):
    def setUp(self):
        self.nodes = _read_nodes()
        self.by_id = {n["id"]: n for n in self.nodes}

    def test_revision_of_targets_exist(self):
        for n in self.nodes:
            if n.get("revision_of") is not None:
                self.assertIn(
                    n["revision_of"], self.by_id,
                    f"{n['id']}: revision_of {n['revision_of']!r} not found",
                )

    def test_revision_of_points_to_earlier_predecessor(self):
        # revision_of points BACKWARD to the superseded (earlier) version.
        for n in self.nodes:
            pred_id = n.get("revision_of")
            if pred_id is not None:
                pred = self.by_id[pred_id]
                self.assertLess(
                    pred["effective_date"], n["effective_date"],
                    f"{n['id']}: revision_of must point to an EARLIER predecessor",
                )

    def test_windows_gap_free_and_non_overlapping(self):
        # Group by (law_code, article_sort_key); within a group, consecutive
        # versions must have contiguous, left-closed/right-open windows.
        groups = {}
        for n in self.nodes:
            groups.setdefault((n["law_code"], n["article_sort_key"]), []).append(n)
        for (law_code, sk), grp in groups.items():
            grp = sorted(grp, key=lambda x: x["effective_date"])
            effs = [g["effective_date"] for g in grp]
            # strictly increasing effective dates (no same-day collision)
            self.assertEqual(
                len(effs), len(set(effs)),
                f"{law_code}#{sk}: duplicate effective_date in same version line",
            )
            for i in range(len(grp) - 1):
                # window end of node i must equal effective_date of node i+1
                succ_eff = None
                for m in self.nodes:
                    if m.get("revision_of") == grp[i]["id"]:
                        succ_eff = m["effective_date"]
                        break
                self.assertEqual(
                    succ_eff, effs[i + 1],
                    f"{law_code}#{sk}: gap/overlap between v{i} and v{i+1} "
                    f"(window_end={succ_eff}, next_eff={effs[i + 1]})",
                )
            # last version in a same-key line has no same-key successor
            last = grp[-1]
            has_same_key_successor = any(
                m.get("revision_of") == last["id"]
                and m["article_sort_key"] == sk
                and m["law_code"] == law_code
                for m in self.nodes
            )
            self.assertFalse(
                has_same_key_successor,
                f"{law_code}#{sk}: trailing version must have no same-key successor",
            )


if __name__ == "__main__":
    unittest.main()
