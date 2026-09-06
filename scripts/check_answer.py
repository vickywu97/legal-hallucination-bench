#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Offline answer checker for legal-hallucination-bench (v1.3).

A model-agnostic, **zero-API** diagnostic: point it at any model's answer text
and get a full hallucination diagnosis — statutory citations (existence /
temporal / content / 张冠李戴) **plus** the three answer-level trap dimensions
(编造判例 / 循环引注 / 自相矛盾). No LLM calls, no network, fully reproducible.

This is the product-facing counterpart to the unit-tested detectors in
``benchmark/answer_checks.py``: it lets a user drop in their own model output
and read a plain-language report, offline, in seconds.

Modes
-----
  Single:
    python scripts/check_answer.py --question Q24 --answer "根据《民法典》第584条……另可参见指导案例第999号佐证。"
    python scripts/check_answer.py --question Q24 --answer-file ans.txt
    python scripts/check_answer.py --question Q24 --answer "…" --format json --out q24.json

  Batch (one JSON record per line: {"question_id","answer","model"?,"as_of_date"?}):
    python scripts/check_answer.py --batch answers.jsonl --out report/

Exit code is always 0 — this is a diagnostic, not a test runner. Gate your own
CI on the printed markers / JSON.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict
from typing import Dict, List, Optional

# Make the bench modules importable whether run as `python scripts/check_answer.py`
# or `python -m scripts.check_answer`.
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

from benchmark.pipeline import run_answer, audit, build_report  # noqa: E402
from benchmark.score import score  # noqa: E402
from knowledge_base.loader import load_laws  # noqa: E402

QUESTIONS_PATH = os.path.join(REPO_ROOT, "questions.json")

# Symbol map: (verdict, hardness) -> glyph
_SYMBOL = {
    ("OK", "hard"): "✓",
    ("HALLUCINATION", "hard"): "✗",
    ("UNVERIFIABLE", "transparent"): "?",
    ("UNVERIFIABLE", "answer"): "?",
    ("OK", "answer"): "✓",
    ("HALLUCINATION", "answer"): "✗A",
}


def _symbol(v) -> str:
    return _SYMBOL.get((getattr(v, "verdict", ""), getattr(v, "hardness", "")), "·")


def load_questions() -> dict:
    with open(QUESTIONS_PATH, encoding="utf-8") as f:
        return json.load(f)


def check_single(question_id: str, answer: str,
                 laws: Optional[Dict] = None,
                 questions: Optional[dict] = None):
    """Run the full pipeline on one answer. Returns (verifications, as_of_date)."""
    if laws is None:
        laws = load_laws()
    if questions is None:
        questions = load_questions()
    qmap = {q["id"]: q for q in questions.get("questions", [])}
    q = qmap.get(question_id)
    as_of = (q or {}).get("as_of_date") or "2025-01-01"
    vs = run_answer(answer, as_of, laws=laws, question_id=question_id)
    return vs, as_of


def render_single(question_id: str, answer: str, vs: List, as_of: str) -> str:
    lines = [f"# 答案级幻觉诊断 · {question_id or '(无题号)'}",
             f"- 评估基准日 as_of：{as_of}",
             f"- 引注/检测项总数：{len(vs)}",
             "",
             "| 符号 | 引注/检测 | 子类 | 判定 | 说明 |",
             "| --- | --- | --- | --- | --- |"]
    for v in vs:
        lines.append(
            f"| {_symbol(v)} | {getattr(v, 'citation_raw', '') or '(答案级)'} | "
            f"{getattr(v, 'category', '')} | {getattr(v, 'verdict', '')} | "
            f"{getattr(v, 'detail', '')} |")
    # summary metrics
    rep = score(vs)
    m = rep.metrics
    lines += [
        "",
        "## 小结",
        f"- 条文级引注幻觉率 HVI：{m.get('hr_statutory', 0):.1%}",
        f"- 内容级幻觉率：{m.get('hr_content', 0):.1%} ｜ 张冠李戴率 CRFI：{m.get('crfi', 0):.1%}",
        f"- 编造判例率 hr_case：{m.get('hr_case', 0):.1%}（指导案例号不在已核验基准）",
        f"- 循环引注率 rate_circular：{m.get('rate_circular', 0):.1%}",
        f"- 自相矛盾标记 flag_self_contradiction：{m.get('flag_self_contradiction', 0):.1%}（诊断，待专家确认）",
    ]
    return "\n".join(lines)


def run_batch(path: str, out_dir: Optional[str], laws: Dict) -> int:
    records = []
    with open(path, encoding="utf-8") as f:
        for ln, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except json.JSONDecodeError as e:
                print(f"[warn] 第{ln}行 JSON 解析失败，跳过：{e}", file=sys.stderr)
                continue
            answer = rec.get("answer", "")
            qid = rec.get("question_id", "")
            as_of = rec.get("as_of_date") or "2025-01-01"
            records.append({
                "model": rec.get("model", qid or "unknown"),
                "as_of_date": as_of,
                "answer": answer,
                "question_id": qid,
                "candidates": rec.get("candidates"),
            })
    if not records:
        print("[error] 批处理文件无有效记录。", file=sys.stderr)
        return 1
    result = audit(records, laws=laws)
    print("批量诊断完成，覆盖记录数：%d，模型数：%d" % (len(records), len(result)))
    for model, d in result.items():
        m = d["report"].metrics
        print(f"  - {model}: 引注数={d['n_citations']}  HVI={m.get('hr_statutory',0):.1%}"
              f"  hr_case={m.get('hr_case',0):.1%}  rate_circular={m.get('rate_circular',0):.1%}")
    if out_dir:
        build_report(result, out_dir)
        print(f"完整报告已写入：{out_dir}")
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    p = argparse.ArgumentParser(
        description="离线法律引注幻觉答案检查器（v1.3，无需 API）")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--question", help="题号，例如 Q24（用于取 as_of_date 与题面上下文）")
    g.add_argument("--batch", help="批量 JSONL 文件路径（每行一个 {question_id,answer,...}）")
    p.add_argument("--answer", help="待检答案文本（与 --question 配合）")
    p.add_argument("--answer-file", help="待检答案文本文件（utf-8）")
    p.add_argument("--format", choices=["text", "json"], default="text",
                   help="单题输出格式（默认 text）")
    p.add_argument("--out", help="输出文件路径（单题 json）或目录（批处理报告）")
    p.add_argument("--quiet", action="store_true", help="单题仅输出小结，省略逐条表")
    args = p.parse_args(argv)

    laws = load_laws()

    if args.batch:
        return run_batch(args.batch, args.out, laws)

    # single mode requires --answer or --answer-file
    if not args.answer and not args.answer_file:
        p.error("单题模式需提供 --answer 或 --answer-file")
    if args.answer_file:
        with open(args.answer_file, encoding="utf-8") as f:
            answer = f.read()
    else:
        answer = args.answer

    vs, as_of = check_single(args.question, answer, laws=laws)

    if args.format == "json":
        out = {
            "question_id": args.question,
            "as_of": as_of,
            "verifications": [asdict(v) for v in vs],
            "metrics": score(vs).metrics,
        }
        text = json.dumps(out, ensure_ascii=False, indent=2)
    else:
        text = render_single(args.question, answer, vs, as_of)
        if args.quiet:
            # keep only the summary block
            text = "\n".join(
                l for l in text.splitlines()
                if l.startswith(("## 小结", "- ")) or l.startswith("# "))

    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text + "\n")
        print(f"已写入：{args.out}")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
