# -*- coding: utf-8 -*-
"""Rule-based scorer for the instruction-following benchmark.

Design guardrails
-----------------
* No LLM judge. Every dimension is computed by rules (regex / exact match),
  so scoring is deterministic, offline, and reproducible.
* Three dimensions, weighted:
    format  (0.3): output matches the required structure
                   (JSON with all required fields, or an exact allowed token)
    content (0.4): extracted / judged / classified values match the reference
    closure (0.3): NO extra explanatory text beyond the required output
* total = 0.3*format + 0.4*content + 0.3*closure
* violation_rate (per task) = 1 - total

This mirrors the binary "pass/fail" philosophy of legal-hallucination-bench,
but extended to a weighted violation rate so a leaderboard can be ranked.
"""
from __future__ import annotations

import json
import re

# Keywords that, if present outside the required structured output, mean the
# model violated the "closed / no extra explanation" instruction.
_CLOSURE_KEYWORDS = (
    "解释", "说明", "因此", "因为", "注：", "注:", "分析",
    "我的回答", "以下是", "如下", "温馨提示", "提示：", "提示:", "理由如下",
)
_EXPLAIN_RE = re.compile("|".join(re.escape(k) for k in _CLOSURE_KEYWORDS))


def _extract_json(text: str):
    """Return (obj, start, end) or (None, -1, -1)."""
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        return None, -1, -1
    try:
        obj = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None, -1, -1
    return obj, m.start(), m.end()


def _residual(text: str, start: int, end: int) -> str:
    if start < 0:
        return text
    return (text[:start] + text[end:]).strip()


def _closure_broken(residual: str) -> bool:
    # FROZEN SCORING RULE (see README "难度门锚点与评分口径冻结"):
    # closure is zero-tolerance. Any residual text outside the target JSON
    # (including ```json fences, leading/trailing prose, explanatory sentences)
    # breaks closure -> this dimension scores 0. Intentional: the benchmark
    # measures *closed* instruction following and tolerates no free elaboration.
    # Do not relax without review.
    if residual:
        return True
    if _EXPLAIN_RE.search(residual):
        return True
    return False


def _content_json(ttype: str, expected: dict, obj: dict, notes: list) -> float:
    if ttype == "condition_rule":
        exp_eligible = expected.get("eligible")
        got_eligible = obj.get("eligible")
        if isinstance(exp_eligible, bool) and isinstance(got_eligible, bool):
            elig_ok = exp_eligible == got_eligible
        else:
            elig_ok = str(got_eligible).strip() == str(exp_eligible).strip()
        reason = str(obj.get("reason", "")).strip()
        reason_ok = bool(reason)
        if not elig_ok:
            notes.append("eligible flag mismatch")
        if not reason_ok:
            notes.append("reason empty")
        if elig_ok and reason_ok:
            return 1.0
        return 0.5 if elig_ok else 0.0
    # format_extraction: per-field exact (normalized) match
    fields = list(expected.keys())
    if not fields:
        return 0.0
    ok = 0
    for k in fields:
        ev = str(expected[k]).strip()
        gv = str(obj.get(k, "")).strip()
        if ev == gv:
            ok += 1
        else:
            notes.append(f"field {k}: expected {ev!r} got {gv!r}")
    return ok / len(fields)


def score_task(task: dict, model_output: str) -> dict:
    out = (model_output or "").strip()
    ttype = task.get("type")
    expected = task.get("expected")
    notes: list = []

    if ttype in ("format_extraction", "condition_rule"):
        obj, s, e = _extract_json(out)
        if obj is None:
            format_score = 0.0
            content_score = 0.0
            notes.append("no valid JSON found")
            residual = out
        else:
            required = list(expected.keys())
            present = [k for k in required if k in obj]
            format_score = 1.0 if len(present) == len(required) else len(present) / len(required)
            content_score = _content_json(ttype, expected, obj, notes)
            residual = _residual(out, s, e)
        closure_ok = not _closure_broken(residual)
        if not closure_ok:
            notes.append("extra explanatory text beyond JSON")

    elif ttype == "fewshot_classify":
        label = out.strip().lstrip("→").strip()
        core = re.split(r"[\s（(]", label)[0].strip()
        format_score = 1.0 if core else 0.0
        content_score = 1.0 if core == str(expected).strip() else 0.0
        closure_ok = (core == out.strip())
        residual = "" if closure_ok else out
        if not closure_ok:
            notes.append("extra text beyond the required label")

    elif ttype == "multi_turn_constraint":
        allowed = task.get("allowed", [])
        core = out.strip()
        exact = core in allowed
        format_score = 1.0 if exact else 0.0
        content_score = 1.0 if core == str(expected).strip() else 0.0
        closure_ok = exact and (core == out)
        residual = "" if closure_ok else out
        if not closure_ok:
            notes.append("output is not exactly the required token")

    else:
        format_score = content_score = 0.0
        closure_ok = False
        notes.append(f"unknown task type: {ttype}")
        residual = out

    closure_score = 1.0 if closure_ok else 0.0
    total = 0.3 * format_score + 0.4 * content_score + 0.3 * closure_score
    return {
        "task_id": task.get("id"),
        "type": ttype,
        "format": round(format_score, 4),
        "content": round(content_score, 4),
        "closure": round(closure_score, 4),
        "total": round(total, 4),
        "violation_rate": round(1 - total, 4),
        "notes": notes,
    }
