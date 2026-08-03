"""KB integrity gate (Week 2 — the credibility firewall, #1).

This is the single hard gate that must stay green after every new article:
  * every node has non-empty content, a valid effective_date, a valid
    article_sort_key matching its article_number, a source_url + accessed_at;
  * every revision_of points to an existing node id;
  * per (law_code, article_sort_key) version chains are gap-free and
    non-overlapping (left-closed, right-open windows derived from revision_of).

The validation logic lives in ``knowledge_base.build_statute.validate`` and is
shared with the CLI, so CI and the command line can never drift.
"""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws  # noqa: E402
from knowledge_base.build_statute import (  # noqa: E402
    _load_statutes,
    validate,
    STATUTES_FILE,
    LAWS_DIR,
)


class TestLawMetadata(unittest.TestCase):
    """laws_index.json metadata must be complete for every canonical law."""

    def setUp(self):
        self.laws = load_laws()

    def test_laws_loaded(self):
        canonical = [k for k in self.laws if self.laws[k].name == k]
        self.assertGreaterEqual(len(canonical), 5)

    def test_law_metadata(self):
        for name, law in self.laws.items():
            if name != law.name:  # skip alias entries
                continue
            self.assertTrue(law.source_url, f"{name}: missing source_url")
            self.assertTrue(law.source_accessed_at, f"{name}: missing source_accessed_at")
            self.assertTrue(law.effective_date, f"{name}: missing effective_date")
            for rid, rev in law.revisions.items():
                self.assertTrue(rev.effective_date, f"{name}/{rid}: missing effective_date")
            for ano, art in rev.articles.items():
                self.assertTrue(art.content.strip(), f"{name}/{rid}/{ano}: empty content")
                self.assertTrue(art.article_no, f"{name}/{rid}: bad article_no")


class TestStatuteIntegrity(unittest.TestCase):
    """The full-node hard gate, imported from build_statute.validate."""

    def setUp(self):
        self.nodes = _load_statutes(STATUTES_FILE)

    def test_zero_errors(self):
        errors = validate(self.nodes)
        self.assertEqual(errors, [], msg="\n".join(errors))

    def test_every_law_code_in_index(self):
        import json
        with open(os.path.join(LAWS_DIR, "laws_index.json"), encoding="utf-8") as f:
            index = json.load(f)
        codes = set(index.keys())
        for n in self.nodes:
            self.assertIn(n["law_code"], codes, f"{n['id']}: law_code not in index")


if __name__ == "__main__":
    unittest.main()
