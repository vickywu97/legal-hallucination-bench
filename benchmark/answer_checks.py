"""Answer-level hallucination detectors — the three new trap dimensions (v1.3).

These operate on the WHOLE model answer (not a single statutory citation) and
return ``Verification`` records with ``hardness="answer"`` so they NEVER pollute
the statutory HVI (which only counts ``hardness=="hard"`` in score.py). The
pipeline accumulates them alongside the per-citation verifications.

Dimensions
----------
1. 编造判例 (fabricated case law)
   A model that name-drops a specific guiding case (指导案例第N号) or a case
   number ((YYYY)……号) is asserting a real-world fact. We verify against a
   curated, expert-checked registry (knowledge_base/cases.json):
     - guiding case N in registry        -> CASE_OK   (OK)
     - guiding case N NOT in registry     -> FABRICATED_CASE (HALLUCINATION, hard)
     - bare case number (案号)            -> UNVERIFIABLE_CASE (transparent, unscored)
   The hard FABRICATED_CASE metric is the benchmark's "guiding-case HR" — the
   point is to penalize ungrounded case citations, exactly the failure mode a
   legal hallucination benchmark exists to catch.

2. 循环引注 (circular citation)
   Build a directed graph over the cited statutory articles: edge A->B when
   article A's verified text references article B (第X条) AND B is also in the
   cited set. If the cited subgraph contains a cycle, the justification is
   circular — no cited article carries independent authority -> CIRCULAR_CITATION
   (HALLUCINATION, hard). Real statutes are a DAG, so this fires only on
   pathological outputs (high precision; a latent trap dimension).

3. 自相矛盾 (self-contradiction)
   Heuristic flag: the same legal 'head' is asserted with opposing predicates in
   different clauses, or an explicit '但/然而' reversal negates an earlier claim
   about the same head without resolution. LOW precision by nature, so this is
   DIAGNOSTIC ONLY (verdict OK, never HALLUCINATION) and requires expert
   confirmation. The dimension is primarily carried by trap-question design +
   expert annotation; the heuristic is a supporting automated nudge.
"""
from __future__ import annotations

import json
import os
import re
from typing import Dict, List, Optional

from benchmark.verify import Verification
from benchmark.extract import cn2int, Citation
from knowledge_base.loader import load_laws, resolve_article


# --- paths / constants ----------------------------------------------------- #
_CASES_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge_base", "cases.json")

CASE_OK = "CASE_OK"
FABRICATED_CASE = "FABRICATED_CASE"
UNVERIFIABLE_CASE = "UNVERIFIABLE_CASE"
CIRCULAR_CITATION = "CIRCULAR_CITATION"
SELF_CONTRADICTION = "SELF_CONTRADICTION"

_GUIDE_NO_RE = re.compile(r"指导?性?案例\s*第?\s*(\d+)\s*号")
_ART_REF_RE = re.compile(r"第\s*([一二三四五六七八九十百千零两0-9]+)\s*条")

_CASES_CACHE: Optional[dict] = None


# --------------------------------------------------------------------------- #
# Case-law verification (编造判例)
# --------------------------------------------------------------------------- #
def load_cases() -> dict:
    """Load the verified guiding-case registry (memoized)."""
    global _CASES_CACHE
    if _CASES_CACHE is None:
        with open(_CASES_PATH, encoding="utf-8") as f:
            _CASES_CACHE = json.load(f)
    return _CASES_CACHE


def _guide_numbers(registry: dict) -> set:
    return {c["guide_no"] for c in registry.get("cases", [])}


def verify_cases(citations: List[Citation],
                 registry: Optional[dict] = None) -> List[Verification]:
    """Verify case-law citations (guiding_case / case_no) from one answer.

    Returns one Verification per case citation (hardness="answer"). A guiding
    case outside the verified registry is a HARD FABRICATED_CASE; a bare case
    number is transparently UNVERIFIABLE_CASE (not scored).
    """
    if registry is None:
        registry = load_cases()
    valid = _guide_numbers(registry)
    out: List[Verification] = []
    for c in citations:
        if c.cit_type == "guiding_case":
            m = _GUIDE_NO_RE.search(c.raw)
            num = m.group(1) if m else ""
            if num in valid:
                out.append(Verification(
                    tier=2, verdict="OK", hardness="answer",
                    detail=f"指导案例第{num}号为已核验真实指导案例",
                    note=f"matched registry guide_no={num}",
                    category=CASE_OK, domain="CASE_LAW",
                    citation_raw=c.raw))
            else:
                out.append(Verification(
                    tier=2, verdict="HALLUCINATION", hardness="answer",
                    detail=f"引注指导案例第{num}号不在已核验基准（编造判例/超范围）",
                    note="out-of-registry guiding case -> fabricated-case trap "
                         "(benchmark policy; expand cases.json to reduce false negatives)",
                    score=0.0, category=FABRICATED_CASE, domain="CASE_LAW",
                    citation_raw=c.raw))
        elif c.cit_type == "case_no":
            out.append(Verification(
                tier=2, verdict="UNVERIFIABLE", hardness="answer",
                detail="个案案号不在已核验基准（事实敏感，需专家核验）",
                note="case_no registry not maintained; transparent, not scored "
                     "(provenance-gate analog)",
                category=UNVERIFIABLE_CASE, domain="CASE_LAW",
                citation_raw=c.raw))
    return out


# --------------------------------------------------------------------------- #
# Circular citation detection (循环引注)
# --------------------------------------------------------------------------- #
def _code_to_name_safe(law_code: str) -> str:
    from benchmark.verify import _code_to_name
    return _code_to_name(law_code)


def detect_circular_citation(citations: List[Citation], laws: Dict,
                             as_of_date: str = "2025-01-01"
                             ) -> Optional[Verification]:
    """Detect a circular citation chain among cited statutory articles.

    Edge A->B exists when article A's verified text references 第B条 AND B is
    also in the cited set. A cycle in the cited subgraph => CIRCULAR_CITATION.
    """
    cited = [c for c in citations
             if c.cit_type == "law" and c.article_no and not c.deprecated_alias]
    if not cited:
        return None

    def name_of(c: Citation) -> str:
        return c.law_name or _code_to_name_safe(c.law_code)

    cited_keys = {(name_of(c), c.article_no.split("-")[0]) for c in cited}
    if not cited_keys:
        return None

    def gt_text(name: str, ano: str) -> str:
        r = resolve_article(laws, name, ano, as_of_date)
        if getattr(r, "found", False) and \
                getattr(r, "verification_status", None) == "verified":
            return r.content or ""
        return ""

    adj: Dict[tuple, set] = {k: set() for k in cited_keys}
    for (name, ano) in cited_keys:
        txt = gt_text(name, ano)
        if not txt:
            continue
        for ref in _ART_REF_RE.findall(txt):
            rano = str(cn2int(ref))
            if rano != ano and (name, rano) in cited_keys:
                adj[(name, ano)].add((name, rano))

    # DFS cycle detection
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {k: WHITE for k in adj}
    found = [False]

    def dfs(u: tuple) -> None:
        color[u] = GRAY
        for v in adj[u]:
            if color[v] == GRAY:
                found[0] = True
                return
            if color[v] == WHITE:
                dfs(v)
                if found[0]:
                    return
        color[u] = BLACK

    for k in adj:
        if color[k] == WHITE:
            dfs(k)
            if found[0]:
                break

    if found[0]:
        chain = " -> ".join(f"{n}第{a}条" for (n, a) in cited_keys)
        return Verification(
            tier=2, verdict="HALLUCINATION", hardness="answer",
            detail="引注形成闭环（循环引注），任一被引条文均无独立权威依据",
            note=f"cited cycle among: {chain}",
            score=0.0, category=CIRCULAR_CITATION, domain="CIRCULAR")
    return None


# --------------------------------------------------------------------------- #
# Self-contradiction heuristic (自相矛盾, DIAGNOSTIC ONLY)
# --------------------------------------------------------------------------- #
# Opposite predicate lexemes that, when applied to the SAME legal head in two
# different clauses, signal a contradiction.
_OPP = {
    "有效": "无效", "无效": "有效",
    "成立": "不成立", "不成立": "成立",
    "属于": "不属于", "不属于": "属于",
    "承担": "不承担", "不承担": "承担",
    "应当": "无需", "必须": "无需",
    "应当": "不得", "必须": "不得",
}
_CLAUSE_SPLIT = re.compile(r"[。；;！？\n]")


def _shared_head(a: str, b: str) -> bool:
    """Crude shared 'head' check: any >=3-char Chinese substring common to both
    clauses (a real shared subject). Good enough for a diagnostic flag."""
    for n in range(3, min(len(a), len(b)) + 1):
        for s in range(0, len(a) - n + 1):
            sub = a[s:s + n]
            if sub in b and re.search(r"[一-鿿]", sub):
                return True
    return False


def _clause_pair_contradicts(a: str, b: str) -> bool:
    for pos, neg in _OPP.items():
        if pos in a and neg in b and _shared_head(a, b):
            return True
        if neg in a and pos in b and _shared_head(a, b):
            return True
    return False


def detect_self_contradiction(text: str) -> Optional[Verification]:
    """Heuristic self-contradiction detector (DIAGNOSTIC ONLY, not scored).

    Flags when the same legal head is asserted with opposing predicates across
    clauses, or an explicit reversal negates an earlier claim about the same
    head without resolution. Returns verdict=OK (never HALLUCINATION); the
    pipeline treats it as a soft signal requiring expert confirmation.
    """
    if not text:
        return None
    clauses = [c.strip() for c in _CLAUSE_SPLIT.split(text) if c.strip()]
    flagged: List[str] = []
    for i in range(len(clauses)):
        for j in range(i + 1, len(clauses)):
            if _clause_pair_contradicts(clauses[i], clauses[j]):
                flagged.append(f"「{clauses[i]}」 vs 「{clauses[j]}」")
                break
        if len(flagged) >= 3:
            break
    if flagged:
        return Verification(
            tier=2, verdict="OK", hardness="answer",
            detail="答案内疑似自相矛盾（诊断信号，待专家确认）",
            note="; ".join(flagged),
            category=SELF_CONTRADICTION, domain="CONTRADICTION")
    return None


# --------------------------------------------------------------------------- #
# Orchestrator
# --------------------------------------------------------------------------- #
def run_answer_checks(answer: str, citations: List[Citation],
                      as_of_date: str, laws: Optional[Dict] = None,
                      question_id: str = "") -> List[Verification]:
    """Run all three answer-level detectors on one model answer.

    Returns the list of answer-level Verifications (each tagged with
    ``question_id``). The pipeline appends these to the per-citation results.
    """
    if laws is None:
        laws = load_laws()
    out: List[Verification] = []
    for v in verify_cases(citations):
        v.question_id = question_id
        out.append(v)
    cc = detect_circular_citation(citations, laws, as_of_date)
    if cc is not None:
        cc.question_id = question_id
        out.append(cc)
    sc = detect_self_contradiction(answer)
    if sc is not None:
        sc.question_id = question_id
        out.append(sc)
    return out
