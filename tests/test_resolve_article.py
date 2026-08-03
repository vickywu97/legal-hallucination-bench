"""Temporal resolution tests — the technical validation point of Week 1.

Proves article-level versioning works: old Company Law art.13 (legal rep)
is relocated to art.10 after 2024-07-01, and resolving at different dates
yields the correct version. This is what detects "time-displaced"
hallucinations.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws, resolve_article  # noqa: E402


class TestResolveArticle(unittest.TestCase):
    def setUp(self):
        self.laws = load_laws()

    def test_civil_584_found(self):
        r = resolve_article(self.laws, "民法典", "584", "2025-01-01")
        self.assertTrue(r.found)
        self.assertIn("损失赔偿额", r.content)

    def test_company_old_13_purged(self):
        # The 2018 Company Law revision (incl. old art.13) was purged, so there
        # is no Company Law revision in force at 2020-01-01 in the KB -> the law
        # is not in force at that date (not silently resolved to a stale node).
        r = resolve_article(self.laws, "公司法", "13", "2020-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "LAW_NOT_IN_FORCE_AT_DATE")

    def test_company_13_relocated_after_2024(self):
        # Old art.13 was relocated to art.10 in the 2023 revision; it no
        # longer exists as art.13 in the current revision -> not found.
        r = resolve_article(self.laws, "公司法", "13", "2025-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "ARTICLE_NOT_IN_THIS_REVISION")

    def test_company_new_10_in_force_2025(self):
        r = resolve_article(self.laws, "公司法", "10", "2025-01-01")
        self.assertTrue(r.found)
        self.assertEqual(r.revision_id, "COMPANY_LAW@2024-07-01")
        self.assertIn("代表公司执行公司事务", r.content)

    def test_unknown_law(self):
        r = resolve_article(self.laws, "不存在的法律", "1", "2025-01-01")
        self.assertFalse(r.found)
        self.assertEqual(r.note, "UNKNOWN_LAW")

    # --- Deprecated-law-name trap (temporal hallucination detection) -------- #
    def test_deprecated_contract_law_flagged_post_2021(self):
        # 合同法 was repealed 2021-01-01. Citing it in 2023 must be flagged
        # as a repealed-name citation even though article resolution fails.
        r = resolve_article(self.laws, "合同法", "113", "2023-01-01")
        self.assertTrue(r.used_deprecated_alias)
        self.assertEqual(r.deprecated_repealed_date, "2021-01-01")
        self.assertEqual(r.note, "ARTICLE_NOT_IN_THIS_REVISION")

    def test_current_alias_not_flagged(self):
        r = resolve_article(self.laws, "民法典", "584", "2023-01-01")
        self.assertFalse(r.used_deprecated_alias)
        self.assertIsNone(r.deprecated_repealed_date)

    def test_deprecated_name_pre_repeal_not_flagged(self):
        # Before its repeal date the name was still valid -> not a trap.
        r = resolve_article(self.laws, "合同法", "113", "2020-06-01")
        self.assertFalse(r.used_deprecated_alias)
        self.assertIsNone(r.deprecated_repealed_date)

    def test_deprecated_old_company_law_flagged_post_2024(self):
        r = resolve_article(self.laws, "旧公司法", "13", "2025-01-01")
        self.assertTrue(r.used_deprecated_alias)
        self.assertEqual(r.deprecated_repealed_date, "2024-07-01")


if __name__ == "__main__":
    unittest.main()
