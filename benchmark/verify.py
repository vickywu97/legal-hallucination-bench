"""Verification engine (Week 4 + 100% Precision Refactor).

Implements a STRICT BINARY content-diff policy (docs/DIFF_POLICY.md):
  - EXACT      -> N(cand) == N(gt) : OK,            score 1.00
  - FABRICATED -> N(cand) != N(gt) : HALLUCINATION, score 0.00
There is NO partial credit. A statutory citation is either character-for-
character equal to the verified text or it is wrong. In the legal world of
statutory text there is no "almost" — only "correct" or "incorrect".

Each FABRICATED result still carries a diagnostic ``category`` (PARTIAL /
TRUNCATED / MISATTRIBUTED / FABRICATED_GENERIC) so audit reports can explain
*why* it failed, but the score is always 0.0 regardless of sub-category. The
public ``diff_level`` field is therefore strictly binary: EXACT or FABRICATED.

Provenance gate (hard, enforced from Week 4)
--------------------------------------------
The shipped KB contains LLM-generated scaffold text whose nodes carry
``verification_status="unverified"``. Scoring MUST NOT treat unverified text
as ground truth. Any citation that resolves to an *unverified* node is
reported as UNVERIFIABLE — never HALLUCINATION/OK — because there is no
verified fact to compare against. Only an expert (`verified: true` in the
SEED, confirmed against flk.npc.gov.cn) promotes a node to usable ground
truth. This is the one rule this benchmark cannot bend: a hallucination
detector must not run on hallucinated law.
"""
from __future__ import annotations

import difflib
import json
import os
import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional

from knowledge_base.loader import load_laws, resolve_article, ResolveResult, _date_ge
from benchmark.extract import Citation, DEPRECATED_LAW_NAMES


# --- diff thresholds (single source of truth; mirror docs/DIFF_POLICY.md) --- #
# STRICT BINARY content diff (100% precision refactor):
#   EXACT     -> N(cand) == N(gt)                 : OK,            score 1.00
#   FABRICATED-> N(cand) != N(gt) (any deviation) : HALLUCINATION, score 0.00
# NO partial credit. PARTIAL / TRUNCATED / MISATTRIBUTED survive only as
# diagnostic sub-categories of FABRICATED (see `category`); they ALL score 0.0.
COV_PARTIAL = 0.50       # classification-only: cov >= this -> category PARTIAL
                         # (else FABRICATED subclasses); never affects score.
MIS_THRESHOLD = 0.80     # cross-article cov' > this -> MISATTRIBUTED (tightened 0.70->0.80)
TRUNC_LEN_RATIO = 0.70   # cand shorter than this * ground AND rev>=0.9 -> TRUNCATED
CROSS_LAW_MIS_THRESHOLD = 0.90  # 跨法张冠李戴阈值（高于同法 0.80，避免误判）

# Soft 张冠李戴探针（诊断用，不影响评分）：在硬 MISATTRIBUTED 未触发时，
# 对"改写/意译式张冠李戴"做一次宽松比对。落在硬阈值之下的灰色带内即标记，
# 仅写入 Verification.note，不改变 category / score / diff_level。
SOFT_MIS_SAME_LAW = 0.50    # 同法软下界：cov∈[0.50, 0.80) → 疑似改写式张冠李戴
SOFT_MIS_CROSS_LAW = 0.70   # 跨法软下界：cov∈[0.70, 0.90)（高于同法，避免误判）

EXACT = "EXACT"
PARTIAL = "PARTIAL"          # diagnostic sub-category of FABRICATED (score 0.0)
FABRICATED = "FABRICATED"


# --------------------------------------------------------------------------- #
# Verification record
# --------------------------------------------------------------------------- #
@dataclass
class Verification:
    tier: int
    verdict: str             # HALLUCINATION | OK | ANOMALY | UNVERIFIABLE
    hardness: str            # hard | soft | transparent
    detail: str = ""
    note: str = ""
    # Week 4 extensions (all optional, defaults keep prior callers working)
    score: float = 0.0       # 0..1 (OK=1, HALLUCINATION=0; UNVERIFIABLE -> n/a)
    diff_level: str = ""     # EXACT/FABRICATED (binary; non-exact is always FABRICATED) ("" if n/a)
    category: str = ""       # failure/quality category (NOT_FOUND, TEMPORAL_*,
                             # TRUNCATED, MISATTRIBUTED, FABRICATED_GENERIC,
                             # CITATION_OK, UNVERIFIED_GT, ...)
    domain: str = ""         # law_code (for per-domain HR)
    citation_raw: str = ""   # original cited text
    candidate: str = ""      # model's rendered statute text (content-level)
    ground_truth: str = ""   # verified official text compared against (if any)
    question_id: str = ""    # source question id (for per-question diagnosis)


def ground_truth_verified(resolved: ResolveResult) -> bool:
    """True only if the resolved node is expert-verified ground truth."""
    return getattr(resolved, "verification_status", None) == "verified"


def refuse_unverified_ground_truth(resolved, citation, as_of_date) -> Optional[Verification]:
    """Provenance gate. If a citation resolves to an unverified node, return an
    UNVERIFIABLE verdict instead of letting it be scored. Returns None when the
    node IS verified (so the caller proceeds to real verification)."""
    if resolved is None or not resolved.found:
        return None
    if not ground_truth_verified(resolved):
        return Verification(
            tier=1,
            verdict="UNVERIFIABLE",
            hardness="transparent",
            detail="resolved node is verification_status=unverified; "
                   "LLM-generated scaffold cannot serve as ground truth",
            note="expert verification required before this citation can be scored",
            category="UNVERIFIED_GT",
            domain=getattr(citation, "law_code", "") or "",
            citation_raw=getattr(citation, "raw", "") or "",
        )
    return None


# --------------------------------------------------------------------------- #
# Normalization + segmentation (docs/DIFF_POLICY.md §二 / §三)
# --------------------------------------------------------------------------- #
_ZW = re.compile(r"[\u200b\u200c\u200d\ufeff]")           # zero-width chars
_BRACKET = re.compile(r"【[^】]*】")                       # 【罪名】 titles
_LEAD_ART = re.compile(r"^第[一二三四五六七八九十百千零两0-9]+条(?:之[一二三四五六七八九])?\s*")
_WS = re.compile(r"\s+")
_TRAIL = re.compile(r"[。；;！？\s]+$")
_PUNCT_MAP = {
    "“": '"', "”": '"', "‘": "'", "’": "'",
    "（": "(", "）": ")",
    "。": ".", "；": ";", "，": ",", "、": ",", "：": ":", "？": "?", "！": "!",
}


def normalize(text: str) -> str:
    """Normalize a statute text for content diff: strip title brackets, leading
    article labels, zero-width chars, unify punctuation variants, collapse ws."""
    if not text:
        return ""
    t = _ZW.sub("", text)
    t = _BRACKET.sub("", t)
    t = _LEAD_ART.sub("", t)
    t = "".join(_PUNCT_MAP.get(ch, ch) for ch in t)
    t = _WS.sub("", t)
    t = _TRAIL.sub("", t)
    return t


def segment(text: str) -> List[str]:
    """Split normalized text into sentence units on [。；;！？\\n]."""
    parts = re.split(r"[。；;！？\n]", text)
    return [p for p in parts if p]


@dataclass
class DiffResult:
    level: str               # EXACT / FABRICATED (PARTIAL kept as a FABRICATED subclass)
    cov: float               # forward coverage of ground by candidate
    rev: float               # reverse coverage
    sim: float               # global char similarity
    reason: str = ""


def content_diff(candidate: str, ground: str) -> DiffResult:
    """Internal classifier between a model's rendered statute text and the
    verified ground truth. Pure, deterministic, zero-dep. See DIFF_POLICY.md.

    EXACT     : normalized texts identical -> OK, score 1.00.
    PARTIAL   : not identical but forward coverage >= COV_PARTIAL. This is a
                diagnostic sub-category of FABRICATED; verify_citation maps it
                to diff_level=FABRICATED, score 0.0 (no partial credit).
    FABRICATED: forward coverage < COV_PARTIAL -> FABRICATED, score 0.0.
    """
    nc, ng = normalize(candidate), normalize(ground)
    if nc == ng:
        return DiffResult(EXACT, 1.0, 1.0, 1.0, "normalized texts identical")
    G, C = segment(ng), segment(nc)
    if not G:
        # ground truth empty -> any non-empty candidate is fabricated
        cov = 1.0 if not C else 0.0
        return DiffResult(FABRICATED if C else EXACT, cov, 1.0 if not C else 0.0,
                          1.0 if not C else 0.0, "empty ground truth")
    cov = sum(1 for g in G if g in nc) / len(G)
    rev = (sum(1 for c in C if c in ng) / len(C)) if C else 1.0
    sim = difflib.SequenceMatcher(None, nc, ng).ratio()

    if cov >= COV_PARTIAL:
        return DiffResult(PARTIAL, cov, rev, sim,
                          f"partial (non-exact): {cov:.0%} of ground clauses "
                          f"present; counts as HALLUCINATION")
    return DiffResult(FABRICATED, cov, rev, sim,
                      f"fabricated: {cov:.0%} ground coverage")


# --------------------------------------------------------------------------- #
# Resolution helper
# --------------------------------------------------------------------------- #
_INDEX_CACHE: Optional[dict] = None


def _load_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        idx_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "knowledge_base", "laws", "laws_index.json")
        with open(idx_path, encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)  # noqa: F821  (json imported below)
    return _INDEX_CACHE


def _code_to_name(law_code: str) -> str:
    """Map a normalized law_code (e.g. COMPANY_LAW) to a loader key (canonical
    Chinese name). Falls back to the code itself if unknown."""
    idx = _load_index()
    meta = idx.get(law_code)
    if meta:
        return meta.get("name", law_code)
    return law_code


def _resolve_citation(laws: Dict, citation: Citation, as_of_date: str) -> ResolveResult:
    """Resolve a Citation to a ground-truth node via the loader's temporal
    resolver. Prefers the matched Chinese name (keeps deprecated-alias trap
    signal intact); falls back to law_code -> canonical name."""
    name = getattr(citation, "law_name", "") or ""
    if name not in laws:
        name = _code_to_name(getattr(citation, "law_code", ""))
    article_no = getattr(citation, "article_no", "") or ""
    if name not in laws or not article_no:
        return ResolveResult(found=False, law_name=name or None,
                             as_of=as_of_date, note="UNKNOWN_LAW_OR_ARTICLE")
    return resolve_article(laws, name, article_no, as_of_date)


# --------------------------------------------------------------------------- #
# Misattribution cross-check (张冠李戴)
# --------------------------------------------------------------------------- #
def _cross_check_misattribution(laws: Dict, resolved: ResolveResult,
                                candidate: str, cited_article_no: str) -> Optional[str]:
    """Detect 张冠李戴: the candidate text matches a DIFFERENT verified article
    better than the cited one.

    Returns a label identifying the misattributed article:
      - ``"<ano>"``             -> a different article in the SAME law
                                   (MIS_THRESHOLD)
      - ``"<LawName> 第<ano>条"`` -> a different article in a DIFFERENT law
                                   (CROSS_LAW_MIS_THRESHOLD, higher bar)
    Returns None when no misattribution is detected. Verified nodes only.

    ``laws`` is keyed by law_code (e.g. ``"CRIMINAL_LAW"``) while
    ``resolved.law_name`` is the canonical Chinese name (e.g. ``"刑法"``); the
    cited law_code is resolved by name match so both scans key consistently.
    """
    cited_name = resolved.law_name
    cited_law = None
    for code, lw in laws.items():
        if code == cited_name or getattr(lw, "name", None) == cited_name \
                or cited_name in getattr(lw, "aliases", []):
            cited_law = lw
            break
    # load_laws() registers each Law under several keys (law_code, full name,
    # and every alias), so we skip the cited law by its canonical .name rather
    # than by a single key — otherwise the cited law's other keys (e.g. its
    # law_code / alias) would be re-scanned and mis-flagged as "foreign".
    cited_law_name = getattr(cited_law, "name", None) if cited_law else None

    # --- same-law scan (tight threshold) ---
    best: Optional[str] = None
    best_cov = MIS_THRESHOLD
    if cited_law is not None:
        for rev in cited_law.revisions.values():
            for ano, art in rev.articles.items():
                if ano == cited_article_no:
                    continue
                if getattr(art, "verification_status", "unverified") != "verified":
                    continue
                d = content_diff(candidate, art.content)
                if d.cov > best_cov:
                    best_cov = d.cov
                    best = ano

    # --- cross-law scan (higher threshold, avoid false positives) ---
    cross_best: Optional[str] = None
    cross_cov = CROSS_LAW_MIS_THRESHOLD
    for code, lw in laws.items():
        if cited_law_name is not None and getattr(lw, "name", None) == cited_law_name:
            continue
        short = lw.aliases[0] if getattr(lw, "aliases", None) else lw.name
        for rev in lw.revisions.values():
            for ano, art in rev.articles.items():
                if getattr(art, "verification_status", "unverified") != "verified":
                    continue
                d = content_diff(candidate, art.content)
                if d.cov > cross_cov:
                    cross_cov = d.cov
                    cross_best = f"{short} 第{ano}条"

    if cross_best is not None:
        return cross_best
    return best


def _soft_misattribution_check(laws: Dict, resolved: ResolveResult,
                               candidate: str, cited_article_no: str
                               ) -> Optional[tuple]:
    """Soft 张冠李戴 probe — runs ONLY when the HARD misattribution check
    (_cross_check_misattribution) did NOT trigger.

    Real models often PARAPHRASE the wrong article instead of quoting it
    verbatim; the hard check (cov>=0.80 same-law / >=0.90 cross-law) misses
    those, and they slip through as FABRICATED_GENERIC/PARTIAL, leaving CRFI
    blind. This probe scans the loose band *below* the hard threshold
    (same-law [SOFT_MIS_SAME_LAW, MIS_THRESHOLD); cross-law
    [SOFT_MIS_CROSS_LAW, CROSS_LAW_MIS_THRESHOLD)) and flags a near-miss.

    Returns ``(label, cov)`` where ``label`` mirrors the hard check
    (``"<ano>"`` same-law, ``"<LawName> 第<ano>条"`` cross-law), or None.
    DIAGNOSTIC ONLY: the caller appends it to Verification.note and NEVER
    changes score/category/diff_level. Verified nodes only.
    """
    if not candidate:
        return None
    cited_name = resolved.law_name
    cited_law = None
    for code, lw in laws.items():
        if code == cited_name or getattr(lw, "name", None) == cited_name \
                or cited_name in getattr(lw, "aliases", []):
            cited_law = lw
            break
    cited_law_name = getattr(cited_law, "name", None) if cited_law else None

    # --- same-law scan (lower band) ---
    soft_same: Optional[str] = None
    soft_same_cov = -1.0  # start strictly below the lower bound
    if cited_law is not None:
        for rev in cited_law.revisions.values():
            for ano, art in rev.articles.items():
                if ano == cited_article_no:
                    continue
                if getattr(art, "verification_status", "unverified") != "verified":
                    continue
                d = content_diff(candidate, art.content)
                if (SOFT_MIS_SAME_LAW <= d.cov < MIS_THRESHOLD
                        and d.cov > soft_same_cov):
                    soft_same_cov = d.cov
                    soft_same = ano

    # --- cross-law scan (lower band, higher floor) ---
    soft_cross: Optional[str] = None
    soft_cross_cov = -1.0
    for code, lw in laws.items():
        if cited_law_name is not None and getattr(lw, "name", None) == cited_law_name:
            continue
        short = lw.aliases[0] if getattr(lw, "aliases", None) else lw.name
        for rev in lw.revisions.values():
            for ano, art in rev.articles.items():
                if getattr(art, "verification_status", "unverified") != "verified":
                    continue
                d = content_diff(candidate, art.content)
                if (SOFT_MIS_CROSS_LAW <= d.cov < CROSS_LAW_MIS_THRESHOLD
                        and d.cov > soft_cross_cov):
                    soft_cross_cov = d.cov
                    soft_cross = f"{short} 第{ano}条"

    if soft_cross is not None:
        return (soft_cross, soft_cross_cov)
    if soft_same is not None:
        return (soft_same, soft_same_cov)
    return None


# --------------------------------------------------------------------------- #
# Range citations (第20条至第22条 -> 20/21/22)
# --------------------------------------------------------------------------- #
_RANGE_RE = re.compile(r"^(\d+)\s*[-—~]\s*(\d+)$")
_RANGE_MAX_SPAN = 50  # sanity bound; reject pathological ranges


def _expand_range(article_no: str) -> Optional[List[str]]:
    """If ``article_no`` is a range (``20-22`` / ``20—22`` / ``20~22``) return
    the expanded list ``['20','21','22']``; else None. Bounds-checked."""
    if not article_no:
        return None
    m = _RANGE_RE.match(article_no)
    if not m:
        return None
    a, b = int(m.group(1)), int(m.group(2))
    if a > b or (b - a) > _RANGE_MAX_SPAN:
        return None
    return [str(n) for n in range(a, b + 1)]


def _verify_range(laws: Dict, citation: Citation, as_of_date: str,
                  sub_articles: List[str], cand: str) -> Verification:
    """Verify a range citation by resolving each sub-article and (when a
    candidate is supplied) diffing against the concatenation of all verified
    texts. ANY sub-article that fails to resolve, is unverified, or is missing
    from the candidate text escalates the whole range to HALLUCINATION."""
    dom = getattr(citation, "law_code", "") or ""
    raw = getattr(citation, "raw", "") or ""
    resolved_list = []
    missing = []
    for ano in sub_articles:
        sub = Citation(cit_type=citation.cit_type, raw=citation.raw,
                       law_code=citation.law_code, law_name=citation.law_name,
                       article_no=ano, article_sort_key=0,
                       deprecated_alias=citation.deprecated_alias)
        r = _resolve_citation(laws, sub, as_of_date)
        if not r.found:
            missing.append(ano)
        else:
            resolved_list.append(r)

    if missing:
        return Verification(
            tier=1, verdict="HALLUCINATION", hardness="hard",
            detail=f"range 第{citation.article_no}条 includes "
                   f"non-existent article(s): {', '.join(missing)}",
            note="model cited a range containing a non-existent article",
            score=0.0, category="NOT_FOUND", domain=dom,
            citation_raw=raw, candidate=cand, ground_truth="")

    # provenance gate: any unverified sub-article -> transparent, never scored
    for r in resolved_list:
        if not ground_truth_verified(r):
            return Verification(
                tier=1, verdict="UNVERIFIABLE", hardness="transparent",
                detail=f"range 第{citation.article_no}条 includes an "
                       f"unverified node (article {r.article_no})",
                note="expert verification required before this citation can be scored",
                category="UNVERIFIED_GT", domain=dom,
                citation_raw=raw, candidate=cand, ground_truth="")

    gt = "\n".join((r.content or "") for r in resolved_list)
    if cand is None or cand == "":
        return Verification(
            tier=1, verdict="OK", hardness="hard",
            detail=f"range 第{citation.article_no}条 resolves to "
                   f"{len(sub_articles)} verified article(s)",
            note="citation-level check only; supply candidate_text for content diff",
            score=1.0, diff_level="", category="CITATION_OK",
            domain=dom, citation_raw=raw, candidate=cand, ground_truth=gt)

    d = content_diff(cand, gt)
    if d.level == EXACT:
        return Verification(tier=1, verdict="OK", hardness="hard",
                            detail="range content matches ground truth exactly",
                            note=d.reason, score=1.0, diff_level=EXACT,
                            category="EXACT", domain=dom, citation_raw=raw,
                            candidate=cand, ground_truth=gt)
    cat = PARTIAL if d.level == PARTIAL else "FABRICATED_GENERIC"
    return Verification(tier=1, verdict="HALLUCINATION", hardness="hard",
                        detail=f"fabricated range content ({cat})",
                        note=d.reason, score=0.0, diff_level=FABRICATED,
                        category=cat, domain=dom, citation_raw=raw,
                        candidate=cand, ground_truth=gt)


# --------------------------------------------------------------------------- #
# Public API
# --------------------------------------------------------------------------- #
def verify_citation(citation: Citation, as_of_date: str,
                    laws: Optional[Dict] = None,
                    candidate_text: Optional[str] = None) -> Verification:
    """Strict binary content-diff verification for a single citation.

    Without ``candidate_text``: citation-level only (existence + temporal trap
    + provenance gate). With ``candidate_text``: adds the binary content diff
    (EXACT -> OK; anything else -> FABRICATED, score 0.0) and a diagnostic
    failure category.
    """
    if laws is None:
        laws = load_laws()
    dom = getattr(citation, "law_code", "") or ""
    raw = getattr(citation, "raw", "") or ""
    cand = candidate_text or ""

    # --- temporal trap (repealed-law name, e.g. 旧公司法 / 合同法) ----------
    # A citation the extractor tagged deprecated_alias (set from the single
    # source of truth benchmark.extract.DEPRECATED_LAW_NAMES) must never be
    # scored against current-law text. Flag it TEMPORAL_DEPRECATED whenever
    # as_of is on/after the repeal date. The loader's resolve_article reaches
    # the same verdict on the resolver side via the same DEPRECATED_LAW_NAMES.
    if getattr(citation, "deprecated_alias", False):
        rep = DEPRECATED_LAW_NAMES.get(getattr(citation, "law_name", "") or "")
        if rep is not None and _date_ge(as_of_date, rep[1]):
            return Verification(
                tier=1, verdict="HALLUCINATION", hardness="hard",
                detail=f"cited repealed law name '{citation.law_name}' "
                       f"(repealed {rep[1]})",
                note="temporal hallucination: abolished-law name used after repeal",
                score=0.0, category="TEMPORAL_DEPRECATED", domain=dom,
                citation_raw=raw, candidate=cand, ground_truth="")

    # --- range citation (第20条至第22条 -> 20/21/22) ----------------------
    sub_articles = _expand_range(getattr(citation, "article_no", "") or "")
    if sub_articles is not None:
        return _verify_range(laws, citation, as_of_date, sub_articles, cand)

    resolved = _resolve_citation(laws, citation, as_of_date)

    # --- provenance gate (unverified node -> transparent, never scored) ---
    gate = refuse_unverified_ground_truth(resolved, citation, as_of_date)
    if gate is not None:
        gate.candidate = cand
        return gate

    # ground-truth text when a verified node is available
    gt_text = ""
    if resolved.found and ground_truth_verified(resolved):
        gt_text = resolved.content or ""

    # --- resolution failure -> hallucination (NOT_FOUND) ---
    if not resolved.found:
        return Verification(
            tier=1, verdict="HALLUCINATION", hardness="hard",
            detail="citation resolves to no article at as_of_date "
                   f"({resolved.note})",
            note="model cited a non-existent / relocated article",
            score=0.0, category="NOT_FOUND", domain=dom, citation_raw=raw,
            candidate=cand, ground_truth=gt_text)

    # --- temporal trap: deprecated alias cited post-repeal -> hallucination ---
    if resolved.used_deprecated_alias:
        return Verification(
            tier=1, verdict="HALLUCINATION", hardness="hard",
            detail=f"cited repealed law name; repealed {resolved.deprecated_repealed_date}",
            note="temporal hallucination: abolished-law name used after repeal",
            score=0.0, category="TEMPORAL_DEPRECATED", domain=dom,
            citation_raw=raw, candidate=cand, ground_truth=gt_text)

    # --- citation-level pass (no candidate text supplied) ---
    if candidate_text is None:
        return Verification(
            tier=1, verdict="OK", hardness="hard",
            detail="resolved to verified article; existence confirmed "
                   f"(rev={resolved.revision_id})",
            note="citation-level check only; supply candidate_text for content diff",
            score=1.0, diff_level="", category="CITATION_OK",
            domain=dom, citation_raw=raw, candidate=cand, ground_truth=gt_text)

    # --- content diff (binary: EXACT vs FABRICATED) ---
    gt = resolved.content or ""
    d = content_diff(candidate_text, gt)
    if d.level == EXACT:
        return Verification(tier=1, verdict="OK", hardness="hard",
                            detail="content matches ground truth exactly",
                            note=d.reason, score=1.0, diff_level=EXACT,
                            category="EXACT", domain=dom, citation_raw=raw,
                            candidate=cand, ground_truth=gt)
    # Binary policy: any non-EXACT output is FABRICATED and scores 0.0.
    # PARTIAL survives only as a diagnostic sub-category (cov >= COV_PARTIAL).
    cited_ano = resolved.article_no or ""
    if d.level == PARTIAL:
        note = d.reason
        soft = _soft_misattribution_check(laws, resolved, candidate_text, cited_ano)
        if soft is not None:
            label, cov = soft
            tag = (f"{label} (cross-law)" if " " in label
                   else f"same-law article {label}")
            note = (f"{note} | SOFT_MISATTRIBUTED: text also partially matches "
                    f"{tag} (cov={cov:.0%}) — possible paraphrased 张冠李戴")
        return Verification(tier=1, verdict="HALLUCINATION", hardness="hard",
                            detail="partial omission of statutory text "
                                   "(still wrong -> FABRICATED, score 0.0)",
                            note=note, score=0.0, diff_level=FABRICATED,
                            category="PARTIAL", domain=dom, citation_raw=raw,
                            candidate=cand, ground_truth=gt)

    # FABRICATED -> sub-classify
    if d.rev >= 0.90 and len(normalize(candidate_text)) < TRUNC_LEN_RATIO * max(1, len(normalize(gt))):
        cat = "TRUNCATED"
        note = f"truncated: candidate is a prefix of ground truth ({d.reason})"
    else:
        mis = _cross_check_misattribution(laws, resolved, candidate_text, cited_ano)
        if mis:
            cat = "MISATTRIBUTED"
            if " " in mis:   # cross-law marker "LawName 第X条"
                note = (f"misattributed: candidate text matches {mis} "
                        f"in a DIFFERENT law (cov={d.cov:.0%} vs cited {cited_ano})")
            else:
                note = (f"misattributed: candidate text matches article {mis} "
                        f"in same law (cov={d.cov:.0%} vs cited {cited_ano})")
        else:
            cat = "FABRICATED_GENERIC"
            note = f"fabricated: {d.reason}"
            soft = _soft_misattribution_check(laws, resolved, candidate_text, cited_ano)
            if soft is not None:
                label, cov = soft
                tag = (f"{label} (cross-law)" if " " in label
                       else f"same-law article {label}")
                note = (f"{note} | SOFT_MISATTRIBUTED: text also partially matches "
                        f"{tag} (cov={cov:.0%}) — possible paraphrased 张冠李戴")
    return Verification(tier=1, verdict="HALLUCINATION", hardness="hard",
                        detail=f"fabricated content ({cat})", note=note,
                        score=0.0, diff_level=FABRICATED, category=cat,
                        domain=dom, citation_raw=raw,
                        candidate=cand, ground_truth=gt)


def verify_batch(citations: List[Citation], as_of_date: str,
                 laws: Optional[Dict] = None,
                 candidate_map: Optional[Dict[int, str]] = None) -> List[Verification]:
    """Verify a list of citations. ``candidate_map`` maps citation index -> the
    model's rendered statute text for that citation (optional)."""
    if laws is None:
        laws = load_laws()
    out: List[Verification] = []
    for i, c in enumerate(citations):
        cand = candidate_map.get(i) if candidate_map else None
        out.append(verify_citation(c, as_of_date, laws=laws, candidate_text=cand))
    return out
