"""Scoring (Week 4).

Computes the hallucination-rate metrics defined in archive/MVP_DESIGN.md §5 and
docs/DIFF_POLICY.md §七:
  - statutory citation HR (hard)            -> headline 跑分
  - statutory content HR (hard, headline)   -> only citations with candidate_text
  - abolished-article misuse rate (hard, temporal)
  - guiding-case HR (hard)
  - case-number structural anomaly rate (soft)
  - unverifiable rate (transparent, excluded from HR)
  - per-domain HR (civil / criminal / admin / tax / ip)
plus bootstrap 95% confidence intervals (1000 resamples, fixed seed) and
paired McNemar significance between models (lands with multi-model runs).

Accepts either a list of ``Verification`` objects or plain dicts (duck-typed
on .verdict / .hardness / .category / .domain / .score).
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass
class ScoreReport:
    metrics: Dict[str, float] = field(default_factory=dict)
    ci: Dict[str, tuple] = field(default_factory=dict)
    per_domain: Dict[str, float] = field(default_factory=dict)


def _attrs(v) -> dict:
    """Extract verdict fields from a Verification or dict."""
    if isinstance(v, dict):
        return {
            "verdict": v.get("verdict", ""),
            "hardness": v.get("hardness", ""),
            "category": v.get("category", ""),
            "domain": v.get("domain", ""),
            "score": v.get("score", 0.0),
            "diff_level": v.get("diff_level", ""),
        }
    return {
        "verdict": getattr(v, "verdict", ""),
        "hardness": getattr(v, "hardness", ""),
        "category": getattr(v, "category", ""),
        "domain": getattr(v, "domain", ""),
        "score": getattr(v, "score", 0.0),
        "diff_level": getattr(v, "diff_level", ""),
    }


def _hr(verifications: List[dict]) -> float:
    """Hallucination rate = #HALLUCINATION / (#HALLUCINATION + #OK)."""
    hal = sum(1 for v in verifications if v["verdict"] == "HALLUCINATION")
    ok = sum(1 for v in verifications if v["verdict"] == "OK")
    denom = hal + ok
    return (hal / denom) if denom else 0.0


def _bootstrap_ci(flags: List[int], n: int = 1000, seed: int = 42) -> tuple:
    """95% CI for a proportion via bootstrap resampling (fixed seed)."""
    if len(flags) < 2:
        p = (sum(flags) / len(flags)) if flags else 0.0
        return (p, p)
    rng = random.Random(seed)
    vals = []
    for _ in range(n):
        sample = [rng.choice(flags) for _ in flags]
        vals.append(sum(sample) / len(sample))
    vals.sort()
    # defensive index bounds: protect against rounding/truncation if n changes
    lo_i = max(0, min(n - 1, int(0.025 * (n - 1))))
    hi_i = max(0, min(n - 1, int(0.975 * (n - 1))))
    return (vals[lo_i], vals[hi_i])


# HVI = citation existence + temporal traps ONLY (the airtight, paraphrase-proof
# headline metric). Content mismatches (FABRICATED / PARTIAL / TRUNCATED /
# MISATTRIBUTED) are deliberately excluded from HVI and reported separately as
# hr_content / CRFI — a model that cites the right article but merely
# paraphrases it must NOT inflate the existence/temporal hallucination rate.
_HVI_CATEGORIES = frozenset({"NOT_FOUND", "TEMPORAL_DEPRECATED"})


def score(verifications: List) -> ScoreReport:
    """Aggregate a list of Verification records into HR metrics.

    Metric semantics (see docs/DIFF_POLICY.md §七 and questions.json ``_meta``):
      * ``hr_statutory`` (HVI) — the airtight, paraphrase-proof headline
        metric. Fraction of *hard* citations that are existence/temporal
        hallucinations (``NOT_FOUND`` or ``TEMPORAL_DEPRECATED``). Content
        mismatches are excluded by design.
      * ``hr_content`` — fraction of *content-diffed* citations (those that
        supplied candidate text and went through the binary diff) that are
        HALLUCINATION. Encompasses FABRICATED_GENERIC / PARTIAL / TRUNCATED /
        MISATTRIBUTED. This is the "verbatim compliance" signal.
      * ``rate_deprecated`` — ``TEMPORAL_DEPRECATED`` / cited (subset of HVI).
      * ``rate_unverifiable`` — ``UNVERIFIABLE`` / total (transparent, never
        scored).
    """
    vs = [_attrs(v) for v in verifications]
    total = len(vs)
    statutory = [v for v in vs if v["hardness"] == "hard"]

    # --- HVI: existence / temporal traps only ---------------------------------
    n_stat = len(statutory)
    n_hvi = sum(1 for v in statutory if v["category"] in _HVI_CATEGORIES)
    hr_stat = (n_hvi / n_stat) if n_stat else 0.0
    metrics: Dict[str, float] = {}
    ci: Dict[str, tuple] = {}
    metrics["hr_statutory"] = hr_stat
    ci["hr_statutory"] = _bootstrap_ci(
        [0 if v["category"] in _HVI_CATEGORIES else 1 for v in statutory])

    # --- content subset: only citations that actually went through the binary
    #     content diff (diff_level is set to EXACT or FABRICATED there). This
    #     excludes NOT_FOUND / TEMPORAL_DEPRECATED / UNVERIFIABLE / CITATION_OK,
    #     which never carry a diff_level — fixing the prior bug where a
    #     non-existent article was miscounted toward hr_content. ---
    content_subset = [v for v in statutory
                      if v["diff_level"] in ("EXACT", "FABRICATED")]
    hr_content = _hr(content_subset)
    metrics["hr_content"] = hr_content
    ci["hr_content"] = _bootstrap_ci(
        [0 if v["verdict"] == "HALLUCINATION" else 1 for v in content_subset])

    # --- CRFI: misattribution rate (张冠李戴) — a focused slice of hr_content
    #     isolating "right article number, wrong statute text" (MISATTRIBUTED)
    #     from generic paraphrase / truncation failures. ---
    n_mis = sum(1 for v in content_subset if v["category"] == "MISATTRIBUTED")
    metrics["crfi"] = (n_mis / len(content_subset)) if content_subset else 0.0

    n_cited = sum(1 for v in statutory if v["verdict"] in ("HALLUCINATION", "OK"))
    n_dep = sum(1 for v in statutory if v["category"] == "TEMPORAL_DEPRECATED")
    metrics["rate_deprecated"] = (n_dep / n_cited) if n_cited else 0.0

    n_unver = sum(1 for v in vs if v["verdict"] == "UNVERIFIABLE")
    metrics["rate_unverifiable"] = (n_unver / total) if total else 0.0

    # per-domain HVI (consistent with hr_statutory)
    per_domain: Dict[str, float] = {}
    domains = sorted({v["domain"] for v in statutory})
    for dom in domains:
        dom_stat = [v for v in statutory if v["domain"] == dom]
        dom_hvi = sum(1 for v in dom_stat if v["category"] in _HVI_CATEGORIES)
        if dom_stat:
            per_domain[dom] = dom_hvi / len(dom_stat)

    return ScoreReport(metrics=metrics, ci=ci, per_domain=per_domain)
