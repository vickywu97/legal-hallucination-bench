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
        }
    return {
        "verdict": getattr(v, "verdict", ""),
        "hardness": getattr(v, "hardness", ""),
        "category": getattr(v, "category", ""),
        "domain": getattr(v, "domain", ""),
        "score": getattr(v, "score", 0.0),
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


def score(verifications: List) -> ScoreReport:
    """Aggregate a list of Verification records into HR metrics."""
    vs = [_attrs(v) for v in verifications]
    total = len(vs)
    statutory = [v for v in vs if v["hardness"] == "hard"]
    cited = [v for v in statutory if v["verdict"] in ("HALLUCINATION", "OK")]

    # content-diff subset (citations that supplied candidate_text -> diff_level set)
    content_subset = [v for v in statutory if v["category"] not in ("CITATION_OK", "")
                      and v["verdict"] in ("HALLUCINATION", "OK")]

    metrics: Dict[str, float] = {}
    ci: Dict[str, tuple] = {}

    hr_stat = _hr(statutory)
    metrics["hr_statutory"] = hr_stat
    ci["hr_statutory"] = _bootstrap_ci([0 if v["verdict"] == "HALLUCINATION" else 1
                                        for v in cited])

    hr_content = _hr(content_subset)
    metrics["hr_content"] = hr_content
    ci["hr_content"] = _bootstrap_ci([0 if v["verdict"] == "HALLUCINATION" else 1
                                      for v in content_subset])

    n_cited = len(cited)
    n_dep = sum(1 for v in statutory if v["category"] == "TEMPORAL_DEPRECATED")
    metrics["rate_deprecated"] = (n_dep / n_cited) if n_cited else 0.0

    n_unver = sum(1 for v in vs if v["verdict"] == "UNVERIFIABLE")
    metrics["rate_unverifiable"] = (n_unver / total) if total else 0.0

    # per-domain HR
    per_domain: Dict[str, float] = {}
    domains = sorted({v["domain"] for v in statutory})
    for dom in domains:
        dom_vs = [v for v in statutory if v["domain"] == dom
                  and v["verdict"] in ("HALLUCINATION", "OK")]
        if dom_vs:
            per_domain[dom] = _hr(dom_vs)

    return ScoreReport(metrics=metrics, ci=ci, per_domain=per_domain)
