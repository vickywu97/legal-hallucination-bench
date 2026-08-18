# -*- coding: utf-8 -*-
"""Rule-based scorer for the instruction-following benchmark.

# 关联难度门版本：GATE_SPEC = "v3_discrimination" (见 difficulty_gate.py)。
# 评分口径 v3（经用户评审授权更新）：三维加权 format0.3/content0.4/closure0.3 不变；
# 其中 format_extraction 的 content 改为「值匹配（不卡键名）+ 数值容错」，
# format 改为「输出合法 JSON 对象即合规」（结构维度），closure 仍对 ```json 围栏零容忍。
# 仍是规则化、确定性、可离线复现，无 LLM judge。

Design guardrails
-----------------
* No LLM judge. Every dimension is computed by rules (regex / value match /
  numeric tolerance), so scoring is deterministic, offline, and reproducible.
* Three dimensions, weighted:
    format  (0.3): output matches the required STRUCTURE
                   (a non-empty JSON object emitted, or an exact allowed token)
    content (0.4): format_extraction -> values match by VALUE (key-name agnostic,
                   numeric tolerance); condition_rule -> eligible boolean; else label
    closure (0.3): NO extra explanatory text beyond the required output
* total = 0.3*format + 0.4*content + 0.3*closure
* violation_rate (per task) = 1 - total

This mirrors the binary "pass/fail" philosophy of legal-hallucination-bench,
but extended to a weighted violation rate so a leaderboard can be ranked.
"""
from __future__ import annotations

import json
import re

# Closure is zero-tolerance and is evaluated purely on *residual text* outside
# the target JSON (see _closure_broken below). An earlier keyword-based variant
# (a list of "explanation" cue words) was intentionally dropped: under the
# frozen scoring rule, ANY residual — even benign — breaks closure, so a soft
# keyword check would contradict the design. Do not re-introduce it.


def _extract_json(text: str):
    """Return (obj, start, end) or (None, -1, -1).

    Tries the shortest ``{...}`` span first (so an output containing more than
    one JSON object still yields the first parseable one), then falls back to a
    greedy match. Avoids false negatives when a model emits two JSON blocks.
    """
    for pat in (r"\{.*?\}", r"\{.*\}"):
        m = re.search(pat, text, re.DOTALL)
        if not m:
            return None, -1, -1
        try:
            obj = json.loads(m.group(0))
        except json.JSONDecodeError:
            continue
        return obj, m.start(), m.end()
    return None, -1, -1


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
    # Do not relax without review. (Keyword-based leniency was deliberately
    # removed; ANY non-empty residual breaks closure, by design.)
    return bool(residual)


def _values_equal(a: str, b: str) -> bool:
    """Exact string match, or numeric match within 1e-9 (so "2270000" == "2270000.0"
    and "13" == "13.0"). Strips whitespace first. Used by value-match content scoring.
    """
    a, b = str(a).strip(), str(b).strip()
    if a == b:
        return True
    try:
        return abs(float(a) - float(b)) < 1e-9
    except (ValueError, TypeError):
        return False


def _content_json_value_match(expected: dict, obj: dict) -> float:
    """format_extraction content: KEY-NAME-AGNOSTIC value match with numeric tolerance.

    Counts how many of the expected reference VALUES appear among the model's
    emitted values (multiset match, order-independent). A model that extracts
    the right values under differently-named keys (or with a ".0" numeric suffix)
    is no longer flat-zeroed on content -- only genuinely missing/wrong values score 0.
    """
    exp_vals = [str(v).strip() for v in expected.values()]
    if not exp_vals:
        return 0.0
    got_vals = [str(v).strip() for v in obj.values()]
    used = set()
    matched = 0
    for ev in exp_vals:
        for i, gv in enumerate(got_vals):
            if i in used:
                continue
            if _values_equal(ev, gv):
                used.add(i)
                matched += 1
                break
    return matched / len(exp_vals)


def _content_json_condition(expected: dict, obj: dict, notes: list) -> float:
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


def score_task(task: dict, model_output: str) -> dict:
    out = (model_output or "").strip()
    ttype = task.get("type")
    expected = task.get("expected")
    notes: list = []

    if ttype == "format_extraction":
        obj, s, e = _extract_json(out)
        if obj is None or not isinstance(obj, dict):
            format_score = 0.0
            content_score = 0.0
            notes.append("no valid JSON object found")
            residual = out
        else:
            # format = structural compliance: a non-empty JSON object was emitted
            # (the required *structure*), independent of the key names used.
            format_score = 1.0 if len(obj) > 0 else 0.0
            # content = value match (key-name agnostic) + numeric tolerance
            content_score = _content_json_value_match(expected, obj)
            if content_score < 1.0:
                notes.append("some expected values missing or mismatched (key-name-agnostic)")
            residual = _residual(out, s, e)
        closure_ok = not _closure_broken(residual)
        if not closure_ok:
            notes.append("extra explanatory text beyond JSON")

    elif ttype == "condition_rule":
        obj, s, e = _extract_json(out)
        if obj is None or not isinstance(obj, dict):
            format_score = 0.0
            content_score = 0.0
            notes.append("no valid JSON object found")
            residual = out
        else:
            required = list(expected.keys())
            present = [k for k in required if k in obj]
            format_score = 1.0 if len(present) == len(required) else len(present) / len(required)
            content_score = _content_json_condition(expected, obj, notes)
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


def score_outputs(task: dict, outputs: list) -> list:
    """Score N repeated model outputs for one task.

    Returns a list of score dicts (one per output). Used for stability /
    variance reporting when the runner is invoked with ``--repeat N``.
    Pure local rule scoring -- no API calls. The caller (difficulty_gate)
    aggregates the per-output totals into mean +/- std.
    """
    return [score_task(task, o) for o in outputs]
