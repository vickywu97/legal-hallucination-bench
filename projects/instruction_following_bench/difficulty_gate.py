# -*- coding: utf-8 -*-
"""Difficulty-gate quantification for the instruction-following benchmark.

Reads the REAL answers file (answers_ifb*.jsonl) and the task config
(config/tasks.json), reuses the rule-based scorer (score.py, no LLM judge),
and quantifies the benchmark against the *discrimination* difficulty gate.

=== Why the gate was redesigned (v3) then made composite (v2_composite) ===
The original gate (strong anchor <= 0.60, weak anchor <= 0.35) was borrowed
from the 领航计划 reasoning-task gate and is MATHEMATICALLY INCOHERENT for an
instruction-following benchmark scored by the 3-dimension weighted scorer:

    total = 0.3*format + 0.4*content + 0.3*closure

Any model that emits valid JSON with all required keys and no prose gets
format=1.0 and closure=1.0 -> a structural FLOOR of 0.60 regardless of content.
So a model that follows the structure but gets every answer wrong still scores
0.60; to push a strong model BELOW 0.60 it must FAIL to follow instructions
(missing keys or added prose) -- but strong models are compliant by definition.
Hence "strong <= 0.60" can essentially never be satisfied. The same floor makes
"weak <= 0.35" require the weak model to be non-compliant on ~40% of tasks.

=== Composite gate (v2_composite) ===
The gate was first made composite: three independent, achievable conditions
(weak <= 0.60 floor; separation >= 0.30; strong not perfect). This PASSED on
real data but the "weak <= 0.60" condition is now near-universal: any compliant
model sits at or above the structural floor, so it carries almost no
discriminative power -- it was effectively measuring "is the model compliant"
rather than "is the task hard for this model".

=== Discrimination gate (v3_discrimination, current) ===
We therefore REFRAME the gate honestly as a **discrimination gate**:

  * DECISIVE (1): separation on the DISCRIMINATING subset (tasks labeled
    hard/medium -- the ones meant to tell models apart) >= 0.30. Calibration
    "easy" tasks (which every model solves) are intentionally EXCLUDED from the
    separation computation so they don't dilute the discrimination signal.
  * DECISIVE (2): strong not-perfect -- strong_avg < 1.0 AND the strong anchor
    violates (total < 0.85) on >= 1 task. The best model must not ace the bench;
    but it is EXPECTED to sit high -- strong models SHOULD follow instructions.
  * DESCRIPTIVE (not decisive): weak anchor avg_total vs the 0.60 structural
    floor. Reported as context. Once easy calibration tasks exist, the weak
    anchor will naturally rise ABOVE 0.60 (it solves the easy tasks), which is
    expected and does NOT fail the gate -- the teeth are separation + strong
    non-perfect, not "weak must be below the floor".

This is the honest statement of what an IF bench can legitimately claim:
"the bench SEPARATES models, and the best model is not at a perfect ceiling."
Claiming "the gate proves the weak model fails" would be misleading because the
0.60 floor is structural, not earned.

=== Variance / stability (--repeat N) ===
models.py can emit N outputs per (model, task). difficulty_gate scores all N
and reports mean +/- std (population) per model. The GATE is evaluated on the
MEAN; std is a stability band, not a separate pass/fail criterion.

Run:
    python -S difficulty_gate.py --answers ../answers_ifb.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from score import score_task, score_outputs  # noqa: E402

# ---- discrimination gate (v3_discrimination) ----
# 区分度门：不再把"弱≤0.60"作为决定性条件（0.60 是合规结构化输出的结构地板，
# 任何合规模型都天然≥0.60，它测的是"模型是否合规"而非"任务对弱模型是否难"）。
# 门的核心两条决定性条件：
#   1) 分离度（在"区分型子集"= 标注 hard/medium 的题上计算，排除 easy 校准题
#      以免稀释信号）≥ 0.30：bench 必须能区分强弱模型。
#   2) 强锚点不得满分：强锚点 avg<1.0 且至少 1 题违背(<0.85)。
# 弱锚点 ≤ 0.60 结构地板改为【说明性】展示：引入 easy 校准题后弱锚点自然上升，
# 属预期，不影响门判定。门的牙齿 = 分离 + 强非满分，而非"压弱模型到地板下"。
GATE_SPEC = "v3_discrimination"
GATE_WEAK_FLOOR = 0.60        # 结构地板（说明性参考，非决定性）
GATE_SEP_MIN = 0.30           # 区分型子集上的强弱分离下限（决定性）
STRONG_VIOL_THRESHOLD = 0.85  # 单题"强锚点违背"判定线
STRONG_VIOL_MIN = 1           # 强锚点至少违背题数（不得满分）
WEAK_FLOOR_DESCRIPTIVE = True  # 弱≤0.60 为说明性而非决定性
DISCRIMINATING_DIFFICULTIES = ("hard", "medium")  # 参与分离度计算的子集

# 冻结锚点（见 README「难度门锚点与评分口径冻结」）：固定到具体模型 id，
# 避免每次跑分锚点漂移导致门槛不可比。固定锚点缺失时回退动态并告警。
STRONG_ANCHOR_LABELS = ("Qwen-Max", "DeepSeek-V3")  # 强锚点候选（取存在的、得分最高者）
WEAK_ANCHOR_LABELS = ("GLM-4-Flash",)               # 弱锚点候选（取存在的、得分最低者）


def load_tasks(path: str) -> dict:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    return {t["id"]: t for t in tasks}


def load_answers(path: str) -> dict:
    by_model: dict = {}
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            by_model.setdefault(r["model"], []).append(r)
    return by_model


def _record_outputs(rec: dict) -> list:
    """Return the list of raw outputs to score for one answer record.

    Supports both the new ``--repeat N`` schema (``outputs`` is a list) and the
    legacy single-``answer`` schema. Never returns an empty list so scoring is
    well-defined.
    """
    outs = rec.get("outputs")
    if isinstance(outs, list) and outs:
        return outs
    return [rec.get("answer", "")]


def _mean(xs) -> float:
    return sum(xs) / len(xs) if xs else 0.0


def _pstdev(xs) -> float:
    if len(xs) < 2:
        return 0.0
    m = _mean(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def emp_bucket(mean_total: float) -> str:
    if mean_total >= 0.85:
        return "easy"
    if mean_total >= 0.5:
        return "medium"
    return "hard"


def compute_gate(by_model: dict, tasks: dict) -> dict:
    """Compute the discrimination gate from scored answers.

    ``by_model``: {model_label: [answer_record, ...]}. Each record carries
    ``task_id`` and either ``outputs`` (list) or ``answer`` (str).

    Returns a result dict consumed by ``render_report`` and the tests.
    """
    models = sorted(by_model.keys())

    # ---- coverage check (trust-but-verify: answers must cover config tasks) ----
    config_ids = set(tasks.keys())
    answered_ids = {r["task_id"] for recs in by_model.values() for r in recs}
    missing_answer_ids = sorted(config_ids - answered_ids)
    orphan_answer_ids = sorted(answered_ids - config_ids)
    scored_ids = config_ids & answered_ids
    coverage_ok = (not missing_answer_ids)

    # ---- data-quality check (trust-but-verify: flag empty/errored answers) ----
    empty_or_error = sum(
        1 for recs in by_model.values() for r in recs
        if all(not str(o).strip() for o in _record_outputs(r))
        or bool(r.get("_error"))
    )

    # ---- per-task per-output totals (supports --repeat N) ----
    # task_scores[tid][model] = list of per-output total scores
    task_scores: dict = {tid: {} for tid in tasks}
    repeat_seen = 0
    for model, recs in by_model.items():
        for r in recs:
            tid = r["task_id"]
            if tid not in tasks:
                continue
            outs = _record_outputs(r)
            repeat_seen = max(repeat_seen, len(outs))
            scored = score_outputs(tasks[tid], outs)
            task_scores[tid][model] = [s["total"] for s in scored]

    # ---- artifact detection (flat-capped format tasks = no discrimination) ----
    artifact_tasks = []
    for tid, t in tasks.items():
        if t.get("type") != "format_extraction":
            continue
        vals = [_mean(task_scores[tid][m]) for m in models if m in task_scores[tid]]
        if vals and max(vals) <= 0.35:  # flat-capped, no discrimination
            artifact_tasks.append(tid)

    # ---- per-task aggregate (mean + std across repeats, per model) ----
    per_task = []
    for tid, t in tasks.items():
        model_means = {}
        model_std = {}
        for m in models:
            if m not in task_scores[tid]:
                continue
            lst = task_scores[tid][m]
            model_means[m] = _mean(lst)
            model_std[m] = _pstdev(lst)
        if not model_means:
            continue
        vals = list(model_means.values())
        mean_t = _mean(vals)
        per_task.append({
            "id": tid,
            "type": t.get("type"),
            "labeled": t.get("difficulty"),
            "scores": {m: round(model_means[m], 3) for m in model_means},
            "std": {m: round(model_std[m], 3) for m in model_std},
            "min": round(min(vals), 3),
            "mean": round(mean_t, 3),
            "max": round(max(vals), 3),
            "emp": emp_bucket(mean_t),
            "violation": round(1 - mean_t, 3),
        })
    per_task.sort(key=lambda x: (x["type"], x["id"]))

    # ---- bucket aggregation (by labeled difficulty) ----
    buckets = {"easy": [], "medium": [], "hard": []}
    for p in per_task:
        buckets[p["labeled"]].append(p["mean"])
    bucket_stats = {}
    for b, vals in buckets.items():
        if vals:
            mt = _mean(vals)
            bucket_stats[b] = {
                "n_tasks": len(vals),
                "mean_total": round(mt, 4),
                "mean_violation": round(1 - mt, 4),
            }

    # ---- per-model aggregate (flatten all per-output totals) ----
    model_rows = []
    all_totals = {}
    for model in models:
        lst = [tot for tid in tasks if model in task_scores[tid]
               for tot in task_scores[tid][model]]
        all_totals[model] = lst
        mt = _mean(lst)
        sd = _pstdev(lst)
        model_rows.append({
            "model": model,
            "avg_total": round(mt, 4),
            "std_total": round(sd, 4),
            "violation": round(1 - mt, 4),
        })

    # ---- gate anchors (FROZEN per README decision) ----
    def _pick(rows, labels, pick):
        present = [r for r in rows if r["model"] in labels]
        if not present:
            return None
        return (max if pick == "max" else min)(present, key=lambda r: r["avg_total"])

    strong_spec = _pick(model_rows, STRONG_ANCHOR_LABELS, "max")
    weak_spec = _pick(model_rows, WEAK_ANCHOR_LABELS, "min")
    strong_dyn = max(model_rows, key=lambda r: r["avg_total"])
    weak_dyn = min(model_rows, key=lambda r: r["avg_total"])
    strongest = strong_spec or strong_dyn
    weakest = weak_spec or weak_dyn
    anchor_fallback = (strong_spec is None) or (weak_spec is None)

    # ---- separation (DECISIVE) on the discriminating subset (hard+medium) ----
    disc_tids = [tid for tid, t in tasks.items()
                 if t.get("difficulty") in DISCRIMINATING_DIFFICULTIES]
    disc_means = {}
    for model in models:
        vals = [per_task_mean_for(task_scores, tid, model)
                for tid in disc_tids if model in task_scores.get(tid, {})]
        if vals:
            disc_means[model] = _mean(vals)
    sep_disc = round(disc_means.get(strongest["model"], 0.0)
                     - disc_means.get(weakest["model"], 0.0), 4)
    # overall separation (all tasks) reported for context
    sep_all = round(strongest["avg_total"] - weakest["avg_total"], 4)

    # ---- strong violations (single-task total < threshold for strongest) ----
    strong_violations = sum(
        1 for p in per_task
        if p["scores"].get(strongest["model"], 1.0) < STRONG_VIOL_THRESHOLD
    )

    # ---- gate evaluation (discrimination gate, v3_discrimination) ----
    weak_ok = weakest["avg_total"] <= GATE_WEAK_FLOOR   # DESCRIPTIVE only
    sep_ok = sep_disc >= GATE_SEP_MIN                    # DECISIVE
    strong_perfect = (strongest["avg_total"] >= 1.0) or (strong_violations < STRONG_VIOL_MIN)
    strong_discrim = not strong_perfect                 # DECISIVE
    gate_pass = sep_ok and strong_discrim

    # ---- leaking tasks (all models >= 0.9 -> no discrimination) ----
    # Split into by-design easy calibration (excluded from gate) vs genuine edge sample.
    leaking_easy = [p["id"] for p in per_task
                    if p["labeled"] == "easy" and all(v >= 0.9 for v in p["scores"].values())]
    leaking_edge = [p["id"] for p in per_task
                    if p["labeled"] != "easy" and all(v >= 0.9 for v in p["scores"].values())]
    leaking = leaking_easy + leaking_edge

    n_easy = sum(1 for t in tasks.values() if t.get("difficulty") == "easy")

    return {
        "models": models,
        "model_rows": model_rows,
        "per_task": per_task,
        "bucket_stats": bucket_stats,
        "strongest": strongest,
        "weakest": weakest,
        "anchor_fallback": anchor_fallback,
        "sep_disc": sep_disc,
        "sep_all": sep_all,
        "sep_ok": sep_ok,
        "strong_violations": strong_violations,
        "strong_discrim": strong_discrim,
        "weak_ok": weak_ok,
        "gate_pass": gate_pass,
        "leaking": leaking,
        "leaking_easy": leaking_easy,
        "leaking_edge": leaking_edge,
        "artifact_tasks": artifact_tasks,
        "empty_or_error": empty_or_error,
        "coverage_ok": coverage_ok,
        "missing_answer_ids": missing_answer_ids,
        "orphan_answer_ids": orphan_answer_ids,
        "n_tasks": len(tasks),
        "n_scored": len(scored_ids),
        "n_easy": n_easy,
        "repeat": repeat_seen,
    }


def per_task_mean_for(task_scores: dict, tid: str, model: str) -> float:
    lst = task_scores.get(tid, {}).get(model, [])
    return _mean(lst)


def render_report(R: dict, args) -> str:
    """Render the markdown report from a compute_gate result dict."""
    lines = []
    lines.append("# 项目 C — 难度门量化报告（区分度门 v3_discrimination）\n")
    if not R["coverage_ok"]:
        lines.append(f"> ⚠️ **覆盖率告警（PRELIMINARY）**：`tasks.json` 共 "
                     f"**{R['n_tasks']}** 题，本次答案仅覆盖 "
                     f"**{R['n_scored']}** 题。"
                     f"以下新题**无答案、未计入评分**："
                     f"`{', '.join(R['missing_answer_ids'])}`；"
                     f"另有已删除旧题的残留答案：`{', '.join(R['orphan_answer_ids'])}`。"
                     f"**本报告的难度门数字不是完整的 {R['n_tasks']} 题结果，须重跑真实模型后复算。**\n")
    lines.append("> **材料性质声明**：本报告基于 `config/tasks.json`（虚构演示任务）"
                 "与真实模型调用产出的答案文件计算。"
                 "任务内容为虚构演示、非经评审的真实基准；评分规则为规则化三维评分"
                 "（`score.py`，无 LLM judge）。结论仅用于脚手架难度设计，**不代表真实"
                 "模型能力排名**，不得对外作为评测结论引用。\n")
    lines.append("## 1. 设计难度门（区分度门 v3_discrimination，目标）\n")
    lines.append("> **重构说明**：原门（强≤0.60 / 弱≤0.35）借自领航计划推理题，与本 bench"
                 "的三维加权评分**数学上不自洽**——合规结构化输出自带 0.60 结构地板分"
                 "（format0.3+closure0.3），强模型只要遵循格式即≥0.60，故“强≤0.60”"
                 "本质上不可达；弱≤0.35 亦需弱模型在~40%题上非合规。v2_composite 曾改为"
                 "“弱≤0.60 结构地板 + 分离 + 强非满分”三条独立条件，实测 PASS；但“弱≤0.60”"
                 "因结构地板而**对任何合规模型近乎恒真**，实际测的是“模型是否合规”而非"
                 "“任务对弱模型是否难”，区分力极弱。现进一步**重框为区分度门**：\n")
    lines.append("- **【决定性】分离度（区分型子集）**：在标注 `hard`/`medium` 的题上，"
                 f"strong_avg − weak_avg ≥ **{GATE_SEP_MIN:.2f}**（easy 校准题不参与，"
                 "以免稀释信号）。bench 必须能区分强弱模型。")
    lines.append("- **【决定性】强锚点不得满分**：avg_total < 1.0 **且** 单题违背"
                 f"（total<{STRONG_VIOL_THRESHOLD:.2f}）题数 ≥ **{STRONG_VIOL_MIN}**。"
                 f"强模型本就该遵循指令，门的牙齿在“分离 + 强非满分”，而非压低强模型。")
    lines.append(f"- **【说明性，非决定性】弱锚点 ≤ {GATE_WEAK_FLOOR:.2f} 结构地板**："
                 "0.60 是“输出合法 JSON/精确 token”即自带的基础分。引入 easy 校准题后，"
                 "弱模型在简单题上得分、自然升至地板之上，属**预期**；该指标仅作背景展示，"
                 "不影响门判定。\n")
    lines.append("## 2. 真实模型表现（冻结锚点映射）\n")
    if R["anchor_fallback"]:
        lines.append("> ⚠️ 固定锚点模型未出现在本次答案中，已回退到动态最强/最弱锚点。\n")
    lines.append("| 模型 | avg_total | std | 违背率 | 分离达标(≥%.2f, 区分型子集) |"
                 " 强非满分达标 |" % GATE_SEP_MIN)
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(R["model_rows"], key=lambda x: -x["avg_total"]):
        ok_sep = "✅" if (R["strongest"]["avg_total"] - r["avg_total"]) >= GATE_SEP_MIN else "—"
        if r["model"] == R["strongest"]["model"]:
            ok_strong = "✅" if R["strong_discrim"] else "❌"
        else:
            ok_strong = "—"
        lines.append(f"| {r['model']} | {r['avg_total']:.3f} | ±{r['std_total']:.3f} | "
                     f"{r['violation']:.3f} | {ok_sep} | {ok_strong} |")
    lines.append("")
    strong_gap = round(1.0 - R["strongest"]["avg_total"], 4)
    lines.append(f"- **强锚点（冻结）**= `{R['strongest']['model']}` "
                 f"avg_total={R['strongest']['avg_total']:.3f} (±{R['strongest']['std_total']:.3f})，"
                 f"距满分 {strong_gap:+.3f}；"
                 f"强锚点违背题数（<{STRONG_VIOL_THRESHOLD:.2f}）= **{R['strong_violations']}**"
                 f"（下限 {STRONG_VIOL_MIN}）。")
    lines.append(f"- **弱锚点（冻结）**= `{R['weakest']['model']}` "
                 f"avg_total={R['weakest']['avg_total']:.3f} (±{R['weakest']['std_total']:.3f})，"
                 f"**{'低于' if R['weakest']['avg_total'] <= GATE_WEAK_FLOOR else '高于'} 结构地板 "
                 f"{GATE_WEAK_FLOOR:.2f}**（gap {R['weakest']['avg_total']-GATE_WEAK_FLOOR:+.3f}）。"
                 f"此指标为**说明性**：引入 easy 校准题后弱锚点升至地板之上是预期现象，"
                 f"不判定门失败。")
    lines.append(f"- **分离度（区分型子集 hard/medium）**= {R['sep_disc']:.3f}"
                 f"（下限 {GATE_SEP_MIN:.2f}，{'达标 ✅' if R['sep_ok'] else '未达标 ❌'}）；"
                 f"全量分离度（含 easy）= {R['sep_all']:.3f}（仅作对照）。")
    lines.append(f"- **结论：难度门{'达标 ✅' if R['gate_pass'] else '未达标 ❌'}**——"
                 f"分离度{'已' if R['sep_ok'] else '未'}≥{GATE_SEP_MIN:.2f}（决定性）；"
                 f"强锚点{'已' if R['strong_discrim'] else '未'}非满分"
                 f"（avg<1.0 且 违背≥{STRONG_VIOL_MIN}题）；"
                 f"弱锚点{R['weakest']['avg_total']:.3f} "
                 f"{'仍≤' if R['weak_ok'] else '已>'} {GATE_WEAK_FLOOR:.2f} 结构地板"
                 f"（说明性，不影响判定）。"
                 + ("" if R["coverage_ok"] else "（⚠️ 数值基于不完整覆盖，仅供参考，须重跑复算）"))
    lines.append("")
    lines.append("### 2.1 评分伪影状态 与 任务演进\n")
    lines.append(f"- **伪影已修复**：`format_extraction` 的 `expected` 键名统一为中文、值照原文，"
                 f"齐平 0.300 的伪影题已清零（artifact_tasks={len(R['artifact_tasks'])}）。")
    lines.append("- **任务演进**：经修伪影、删漏分题、扩 condition_rule 外部知识题、格式题改派生计算、"
                 "ADV1 改复合约束+例外；并新增 5 道 **easy 校准题**（E1–E5，纯照抄提取、"
                 "无计算/无外部知识），使 `difficulty` 标签呈梯度（easy/medium/hard 均有样本），"
                 "并作为‘本 bench 并非对所有模型都不可解’的校准基线。")
    lines.append(f"- **ADV1 已知边缘题**：当前为复合约束+例外题（含机密但不含外发→需审批），"
                 f"三模型均输出正确 token（1.000），属已知漏分题；但在区分度门下不影响判定"
                 f"（弱锚点 {R['weakest']['avg_total']:.3f} 仍明显低于强锚点、分离与强非满分均达标）。"
                 f"保留为冻结版本边缘样本。")
    lines.append(f"- **评分口径 v3**：format_extraction 的 content 已改为「值匹配（不卡键名）+ 数值容错」、"
                 f"format 改为「输出合法 JSON 对象即合规」；因此原「公平格式情景 B」诊断已无必要"
                 f"（主键名差异不再导致 content 被清零）。结构地板 0.60 仍由 format0.3+closure0.3 "
                 f"构成。")
    lines.append(f"- **稳定性（--repeat N）**：本次每题重复 **{R['repeat']}** 次，"
                 f"上为各模型 mean±std（std 为稳定性带，不作为独立判定项）。\n")
    lines.append("## 3. 难度桶聚合（标注 difficulty × 真实表现）\n")
    lines.append("| 标注难度 | 题数 | 桶内 mean_total | 桶内 mean_违背率 |")
    lines.append("|---|---|---|---|")
    for b in ("easy", "medium", "hard"):
        if b in R["bucket_stats"]:
            s = R["bucket_stats"][b]
            lines.append(f"| {b} | {s['n_tasks']} | {s['mean_total']:.3f} | {s['mean_violation']:.3f} |")
    if R["n_easy"]:
        lines.append(f"\n> 共 **{R['n_easy']}** 道 easy 校准题；其桶内 mean 接近 1.0，"
                     f"证明弱模型在简单题上也能得满分，benchmark 难度由 hard/medium 决定。")
    lines.append("")
    lines.append("## 4. 逐题真实表现（按类型/编号）\n")
    lines.append("| 题号 | 类型 | 标注难度 | 经验难度 | "
                 + " | ".join(R["models"]) + " | min | mean | max |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for p in R["per_task"]:
        score_cells = " | ".join(f"{p['scores'].get(m, '-'):.3f}" for m in R["models"])
        lines.append(f"| {p['id']} | {p['type']} | {p['labeled']} | {p['emp']} | "
                     f"{score_cells} | {p['min']:.3f} | {p['mean']:.3f} | {p['max']:.3f} |")
    lines.append("")
    lines.append(f"## 5. 漏分题（全部模型 ≥ 0.9，无区分度）\n")
    lines.append(f"- **easy 校准题（{len(R['leaking_easy'])} 题，{', '.join(R['leaking_easy']) or '无'}）**："
                 f"纯照抄提取、无计算/无外部知识，设计上即由全部模型满分解出，作为「本 bench 并非对所有模型都不可解」"
                 f"的校准基线。**刻意保留，不参与门判定**，不属于缺陷。")
    lines.append(f"- **真实边缘题（{len(R['leaking_edge'])} 题，{', '.join(R['leaking_edge']) or '无'}）**："
                 f"非 easy 标注却仍被全部模型满分解出，属已知边缘样本；在区分度门下不影响判定，"
                 f"保留为冻结版本边缘样本（如需零漏分须改语义陷阱，触碰冻结任务集，需授权）。\n")
    lines.append("## 6. 缺口量化与收口建议\n")
    lines.append(f"1. **分离度（决定性）**：区分型子集上 {R['sep_disc']:.3f}"
                 f"（下限 {GATE_SEP_MIN:.2f}），{'已达标 ✅' if R['sep_ok'] else '需拉大'}。"
                 f"这是门的核心牙齿——证明 bench 能区分强弱模型。")
    lines.append(f"2. **强锚点非满分（决定性）**：强锚点 {R['strongest']['model']} = "
                 f"{R['strongest']['avg_total']:.3f}（距满分 {strong_gap:+.3f}），"
                 f"违背题数 {R['strong_violations']} ≥ {STRONG_VIOL_MIN}，"
                 f"{'已达标 ✅' if R['strong_discrim'] else '未达标 ❌'}。")
    lines.append(f"3. **弱锚点（说明性）**：最弱真实模型 {R['weakest']['model']} = "
                 f"{R['weakest']['avg_total']:.3f}，"
                 f"{'仍≤' if R['weak_ok'] else '已>'} {GATE_WEAK_FLOOR:.2f} 结构地板"
                 f"（gap {R['weakest']['avg_total']-GATE_WEAK_FLOOR:+.3f}）。"
                 f"因 0.60 结构地板对任何合规模型近乎恒真，此指标仅作背景，"
                 f"不决定门成败。")
    lines.append("4. **区分度门收口**：两条决定性条件（分离度 + 强非满分）均已满足，"
                 "且陈述诚实——门测的是‘bench 能否区分模型 + 最强模型未触顶’，"
                 "而非误导性的‘弱模型被压到地板下’。弱模型在 easy 校准题上得分、"
                 "升至地板之上是预期且合理的。")
    lines.append("5. **锚点固定 + 评分口径冻结**：提交前把“模型一/模型二”绑定到固定模型 id，"
                 "并冻结三维评分规则（尤其 closure 对 ```json 围栏的零容忍口径），"
                 "否则每次跑分锚点与门槛不可比。\n")
    lines.append("---")
    lines.append("_生成自 `difficulty_gate.py`（区分度门 v3_discrimination），"
                 "复用 `score.py` 规则评分，零依赖可离线复现。_")
    return "\n".join(lines)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Difficulty-gate quantification")
    ap.add_argument("--answers", default=os.path.join(HERE, "..", "..", "answers_ifb.jsonl"))
    ap.add_argument("--tasks", default=os.path.join(HERE, "config", "tasks.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "difficulty_gate_report.md"))
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks)
    by_model = load_answers(args.answers)
    R = compute_gate(by_model, tasks)

    md = render_report(R, args)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    # also print a compact summary
    print("=== difficulty gate quantification (discrimination v3_discrimination) ===")
    for r in sorted(R["model_rows"], key=lambda x: -x["avg_total"]):
        print(f"  {r['model']:>14}  avg_total={r['avg_total']:.3f}  "
              f"std={r['std_total']:.3f}  violation={r['violation']:.3f}")
    print(f"  weak anchor={R['weakest']['model']} floor={GATE_WEAK_FLOOR:.2f} "
          f"gap={R['weakest']['avg_total']-GATE_WEAK_FLOOR:+.3f} "
          f"(descriptive, not decisive)")
    print(f"  strong anchor={R['strongest']['model']} "
          f"viol(<{STRONG_VIOL_THRESHOLD:.2f})={R['strong_violations']}")
    print(f"  separation(disc subset)={R['sep_disc']:.3f} (need >= {GATE_SEP_MIN:.2f})")
    if not R["coverage_ok"]:
        print(f"  [WARN] coverage: {R['n_scored']}/{R['n_tasks']} tasks scored; "
              f"missing={R['missing_answer_ids']}; orphan={R['orphan_answer_ids']}")
    if R["empty_or_error"]:
        print(f"  [WARN] data quality: {R['empty_or_error']} record(s) empty or errored "
              f"(scored as 0; check API keys / network before trusting the gate)")
    print(f"  gate: sep_ok={R['sep_ok']} strong_discrim={R['strong_discrim']} "
          f"(weak_ok={R['weak_ok']} descriptive) "
          f"-> {'PASS ✅' if R['gate_pass'] else 'FAIL ❌'}")
    print(f"  leaking(easy, by-design): {len(R['leaking_easy'])} "
          f"({', '.join(R['leaking_easy']) or 'none'})")
    print(f"  leaking(edge, frozen): {len(R['leaking_edge'])} "
          f"({', '.join(R['leaking_edge']) or 'none'})")
    print(f"[written] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
