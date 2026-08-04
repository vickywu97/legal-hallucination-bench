"""End-to-end offline pipeline (Week 5).

Connects the Week-3 extractor, the Week-4 content-diff verifier, and the
scorer into one runnable product:

    model answer (text)  ->  extract citations  ->  verify each (binary
    verbatim-or-zero content-diff)  ->  score  ->  audit report + leaderboard

Design notes
------------
* **Two fidelity modes** (honest confidence-weighting, see METHODOLOGY §一):
  - *Citation-level* (default, fully reliable): each citation is checked for
    existence + temporal trap + provenance gate. No candidate text needed.
  - *Content-level* (opt-in, stricter): supply a ``candidates`` map
    (citation index -> the model's rendered statute text) in the input record,
    or rely on the built-in ``candidate_window`` heuristic that grabs the
    passage following a 'cite-then-quote' mention. The heuristic is APPROXIMATE;
    gold candidate text yields stricter PARTIAL/FABRICATED/MISATTRIBUTED calls.
* The provenance gate (UNVERIFIED_GT) and temporal trap (TEMPORAL_DEPRECATED)
  are enforced inside verify_citation — the pipeline only forwards results.
* Zero runtime dependencies; deterministic; **model-agnostic** — point it at
  any model's ``answers.jsonl`` and it scores fully offline (no LLM calls).
"""
from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from dataclasses import asdict
from typing import Dict, List, Optional

from knowledge_base.loader import load_laws, normalize_as_of
from benchmark.extract import extract
from benchmark.verify import verify_citation
from benchmark.score import score, ScoreReport


# --------------------------------------------------------------------------- #
# Candidate extraction
# --------------------------------------------------------------------------- #
# A statute quote usually ends at the NEXT legal citation (cite-then-quote
# pattern). Stopping the candidate window there keeps the extracted text equal
# to the single article the model quoted, instead of bleeding into the next
# citation or trailing prose.
_NEXT_CITATION = re.compile(r"《[^》]{1,20}》\s*第[一二三四五六七八九十百千0-9]+条")

# A connective (根据/依据/另，/见/参见/以及/并且/同时/此外/又/而) that bridges the
# quoted statute into the NEXT citation mention is NOT part of the statute the
# model rendered. Drop a trailing one (it must follow a sentence boundary or
# newline, so legitimate statute tails are never stripped) so a verbatim-correct
# quote scores EXACT instead of being penalised for the window boundary.
_TRAIL_CONNECTIVE = re.compile(
    r"(?<=[。；;！？\n])\s*(根据|依据|另[，, ]?|见|参见|以及|并且|同时|此外|又|而)\s*$")


def candidate_window(text: str, span: tuple, max_chars: int = 500) -> str:
    """Extract the model's rendered statute text following a citation.

    Dominant legal-QA pattern is 'cite-then-quote' (e.g. '根据《刑法》第232条，
    故意杀人的处死刑……'). We grab from the end of the citation mention to the
    NEXT law citation (《…》第X条) or ``max_chars``, whichever comes first — the
    statute passage the model actually produced for that article.

    Notes
    -----
    * Stopping at the *next citation* (not a sentence boundary) matters: Chinese
      articles contain multiple ``。``-separated sentences, and ``；`` is an
      intra-clause separator — both would otherwise truncate the quote and
      false-flag it as PARTIAL/TRUNCATED.
    * The punctuation/space immediately after the citation mention (e.g. the
      '，' after '第232条') is skipped so the candidate starts at the statute
      text itself, keeping substring matching sound.
    APPROXIMATE: supply gold ``candidates`` for strict evaluation.
    """
    if not span or span[1] <= span[0] or span[1] > len(text):
        return ""
    start = span[1]
    # skip trailing punctuation/space of the citation mention
    while start < len(text) and text[start] in "，。、：:；;,. \n\t":
        start += 1
    cut = min(len(text), start + max_chars)
    # stop at the next law citation (marks the end of this article's quote)
    m = _NEXT_CITATION.search(text, start, cut)
    end = m.start() if m else cut
    raw = text[start:end]
    # strip a trailing connective that bridges into the next citation mention
    raw = _TRAIL_CONNECTIVE.sub("", raw)
    return raw.strip()


# --------------------------------------------------------------------------- #
# Per-answer verification
# --------------------------------------------------------------------------- #
def run_answer(answer: str, as_of_date: str,
               laws: Optional[Dict] = None,
               gold_candidates: Optional[Dict] = None,
               question_id: str = "") -> List:
    """Extract citations from one model answer and verify each.

    ``gold_candidates`` maps citation index (int or str) -> the model's rendered
    statute text for strict content-diff. When absent, a post-citation window is
    used as an approximate candidate; empty result falls back to citation-level.
    ``question_id`` is threaded onto every Verification for per-question diagnosis.
    """
    if laws is None:
        laws = load_laws()
    citations = extract(answer)
    out = []
    gc = gold_candidates or {}
    for i, c in enumerate(citations):
        cand = gc.get(str(i)) or gc.get(i)
        if cand is None and c.span:
            cand = candidate_window(answer, c.span)
        v = verify_citation(c, as_of_date, laws=laws,
                            candidate_text=cand or None)
        v.question_id = question_id
        out.append(v)
    return out


# --------------------------------------------------------------------------- #
# Batch audit
# --------------------------------------------------------------------------- #
def audit(records: List[dict], laws: Optional[Dict] = None) -> Dict:
    """Run the full pipeline over a list of model-answer records.

    Each record: ``{"model": str, "as_of_date": str, "answer": str,
    "question_id": str (optional), "candidates": {idx: str} (optional)}``.

    A model may appear in many records (one per question); verifications are
    **accumulated** per model (not overwritten), so the leaderboard aggregates
    every citation the model produced across all questions. Per-citation
    ``question_id`` is preserved for the per-question diagnosis matrix.

    Returns ``{model: {"verifications", "report": ScoreReport, "n_citations"}}``.
    """
    if laws is None:
        laws = load_laws()
    result: Dict = {}
    for rec in records:
        model = rec.get("model", "unknown")
        qid = rec.get("question_id", "")
        vs = run_answer(rec.get("answer", ""),
                        normalize_as_of(rec.get("as_of_date")) or "2025-01-01",
                        laws=laws, gold_candidates=rec.get("candidates"),
                        question_id=qid)
        if model not in result:
            result[model] = {"verifications": [], "n_citations": 0}
        result[model]["verifications"].extend(vs)
        result[model]["n_citations"] += len(vs)
    for model, d in result.items():
        d["report"] = score(d["verifications"])
    return result


# --------------------------------------------------------------------------- #
# Reporting
# --------------------------------------------------------------------------- #
def _verif_dict(v) -> dict:
    return asdict(v)


def _write_model_md(model: str, data: dict, out_dir: str) -> str:
    rep: ScoreReport = data["report"]
    m = rep.metrics
    path = os.path.join(out_dir, f"audit_{model}.md")
    lines = [f"# 审计报告：{model}", ""]
    lines.append(f"- 引注数：{data['n_citations']}")
    ci_stat = rep.ci.get("hr_statutory", (0.0, 0.0))
    lines.append(f"- 引注幻觉率 HVI(hr_statutory)：{m.get('hr_statutory', 0):.1%} "
                 f"（bootstrap 95% CI {ci_stat[0]:.1%}–{ci_stat[1]:.1%}；仅统计存在性/时序性幻觉）")
    lines.append(f"- 内容级幻觉率 HR_content：{m.get('hr_content', 0):.1%}（仅逐字 diff 子集；反映是否照抄法条）")
    lines.append(f"- 张冠李戴率 CRFI：{m.get('crfi', 0):.1%}（逐字 diff 子集中 MISATTRIBUTED 占比；专抓'条号对、内容错'）")
    lines.append(f"- 时序幻觉率 rate_deprecated：{m.get('rate_deprecated', 0):.1%}")
    lines.append(f"- 不可验率 rate_unverifiable：{m.get('rate_unverifiable', 0):.1%}")
    if rep.per_domain:
        lines.append("- 分域 HR：")
        for dom, hr in rep.per_domain.items():
            lines.append(f"  - {dom}：{hr:.1%}")
    lines.append("")
    lines.append("## 逐条核验")
    lines.append("")
    lines.append("| 题号 | 引注 | 判定 | 子类 | 级别 | 得分 | 说明 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- |")
    for v in data["verifications"]:
        lines.append(
            f"| {v.question_id or '-'} | {v.citation_raw} | {v.verdict} | "
            f"{v.category} | {v.diff_level or '-'} | {v.score:.2f} | {v.note} |")
    lines.append("")
    lines.append("## 逐条对照（模型输出 vs 已核验基准）")
    lines.append("")
    for v in data["verifications"]:
        cand = v.candidate or "（引注级，未提供候选文本）"
        gt = v.ground_truth or "（无可用已核验基准 / 条文未找到）"
        lines.append(f"### {v.citation_raw}")
        lines.append(f"- 判定：{v.verdict} ｜ 子类：{v.category} ｜ "
                     f"级别：{v.diff_level or '-'} ｜ 得分：{v.score:.2f}")
        lines.append(f"- 模型输出（候选）：{cand}")
        lines.append(f"- 官方原文（基准）：{gt}")
        lines.append("")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return path


def _write_leaderboard(per_model: dict, out_dir: str) -> str:
    # rank by HR_statutory ascending (lower hallucination = better)
    ranked = sorted(per_model.items(),
                    key=lambda kv: kv[1]["metrics"].get("hr_statutory", 1.0))
    md_path = os.path.join(out_dir, "leaderboard.md")
    json_path = os.path.join(out_dir, "leaderboard.json")
    lines = ["# 法律引注幻觉排行榜 (Leaderboard)", "",
             "| 排名 | 模型 | 引注幻觉率(HVI) | 内容级幻觉率 | 张冠李戴率(CRFI) | "
             "时序幻觉率 | 不可验率 | 引注数 |",
             "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    board = []
    for rank, (model, d) in enumerate(ranked, 1):
        m = d["metrics"]
        lines.append(
            f"| {rank} | {model} | {m.get('hr_statutory', 0):.1%} | "
            f"{m.get('hr_content', 0):.1%} | {m.get('crfi', 0):.1%} | "
            f"{m.get('rate_deprecated', 0):.1%} | "
            f"{m.get('rate_unverifiable', 0):.1%} | {d['n_citations']} |")
        board.append({"rank": rank, "model": model, "metrics": m,
                      "n_citations": d["n_citations"]})
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(board, f, ensure_ascii=False, indent=2)
    return md_path


_CAT_ABBR = {
    "TEMPORAL_DEPRECATED": "T", "NOT_FOUND": "NF", "MISATTRIBUTED": "MA",
    "FABRICATED_GENERIC": "F", "TRUNCATED": "TR", "UNVERIFIED_GT": "UG",
}


def _write_question_matrix(flat: List[dict], per_model: dict, out_dir: str) -> str:
    """Append a question x model diagnosis matrix to leaderboard.md.

    Each cell summarises how a model fared on a specific question:
    ✓ OK ｜ ✗ HALLUCINATION (with category abbrevs) ｜ ? UNVERIFIABLE ｜ · none.
    This is the "name-and-shame" view: which model failed which question.
    """
    cells = defaultdict(list)
    for r in flat:
        q = r.get("question_id") or "-"
        cells[(q, r.get("model"))].append((r.get("verdict"), r.get("category")))

    def _qkey(x):
        # natural order: Q1..Q9 before Q10..Q15
        return (len(x), x)
    questions = sorted({r.get("question_id") or "-" for r in flat}, key=_qkey)
    # order models by HR_statutory ascending (best -> worst), consistent w/ board
    models = sorted(per_model.keys(),
                    key=lambda m: per_model[m]["metrics"].get("hr_statutory", 1.0))

    lines = ["", "## 逐题诊断矩阵 (Question × Model)", ""]
    lines.append("图例：✓ 通过(OK) ｜ ✗ 幻觉(HALLUCINATION) ｜ ? 不可验(UNVERIFIABLE) "
                 "｜ · 该题无引注")
    lines.append("")
    lines.append("| 题号 | " + " | ".join(models) + " |")
    lines.append("| --- | " + " | ".join(["---"] * len(models)) + " |")
    for q in questions:
        row = [q]
        for m in models:
            vs = cells.get((q, m), [])
            if not vs:
                row.append("·")
                continue
            if any(v == "HALLUCINATION" for v, _ in vs):
                cats = {c for v, c in vs if v == "HALLUCINATION" and c}
                ab = "/".join(_CAT_ABBR.get(c, c) for c in sorted(cats))
                row.append("✗" + ab)
            elif any(v == "UNVERIFIABLE" for v, _ in vs):
                row.append("?")
            elif all(v == "OK" for v, _ in vs):
                row.append("✓")
            else:
                row.append("·")
        lines.append("| " + " | ".join(row) + " |")
    lines.append("")
    lines.append("子类缩写：T=时序幻觉 NF=条文不存在 MA=张冠李戴 "
                 "F=内容编造 TR=截断 UG=未核验基准")
    md_path = os.path.join(out_dir, "leaderboard.md")
    with open(md_path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return md_path


def build_report(audit_result: Dict, out_dir: str) -> str:
    """Write the audit report, per-model markdown, leaderboard, and a flat
    verifications.jsonl. Returns the output directory."""
    os.makedirs(out_dir, exist_ok=True)
    flat = []
    per_model = {}
    for model, data in audit_result.items():
        recs = [_verif_dict(v) for v in data["verifications"]]
        flat.extend([dict(r, model=model) for r in recs])
        per_model[model] = {
            "n_citations": data["n_citations"],
            "metrics": data["report"].metrics,
            "per_domain": data["report"].per_domain,
        }
    with open(os.path.join(out_dir, "verifications.jsonl"), "w",
              encoding="utf-8") as f:
        for r in flat:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    for model, data in audit_result.items():
        _write_model_md(model, data, out_dir)
    _write_leaderboard(per_model, out_dir)
    _write_question_matrix(flat, per_model, out_dir)
    return out_dir
