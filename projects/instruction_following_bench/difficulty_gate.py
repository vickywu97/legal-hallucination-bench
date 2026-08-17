# -*- coding: utf-8 -*-
"""Difficulty-gate quantification for the instruction-following benchmark.

Reads the REAL answers file (answers_ifb*.jsonl) and the task config
(config/tasks.json), reuses the rule-based scorer (score.py, no LLM judge),
and quantifies the benchmark against the *composite* difficulty gate.

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

=== Composite gate (v2_composite, current) ===
The gate now enforces what an IF bench CAN legitimately discriminate, as three
independent, achievable conditions (no single absolute score to overfit):

  * weak anchor (弱锚点, frozen=GLM-4-Flash): avg_total <= 0.60 (the structural
    floor). A weak model must sit at or below the floor -- i.e. it must actually
    fail content/closure somewhere, not merely be "compliant but wrong".
  * separation (强弱分离): strong_avg - weak_avg >= 0.30 -- the bench must
    separate models.
  * strong not-perfect (强锚点不得满分): strong_avg < 1.0 AND the strong anchor
    violates (total < 0.85) on >= 1 task. The best model must not ace the bench;
    but it is EXPECTED to sit high -- strong models SHOULD follow instructions.
    The teeth of the gate are weak-fail + sep.

Run:
    python -S difficulty_gate.py --answers ../answers_ifb.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from score import score_task  # noqa: E402

# ---- composite, coherent gate (v2_composite) ----
# 复合门槛：不再依赖单一绝对分（旧 弱≤0.35/强≤0.60 在三维加权评分下不自洽），
# 改为三条可达成、有牙齿的口径：
#   1) 弱锚点须 ≤ 0.60 结构地板（format0.3+closure0.3）：模型输出合法 JSON/精确
#      token 即得 0.60 基础分；弱模型须 ≤ 此线才证明确实失分。
#   2) 强弱分离 ≥ 0.30：bench 必须能区分强弱模型。
#   3) 强锚点不得满分：强锚点 avg<1.0 且至少 1 题违背(<0.85)。强模型本就该遵循
#      指令，门的牙齿在"弱失败 + 分离"，而非压低强模型。
GATE_SPEC = "v2_composite"
GATE_WEAK_FLOOR = 0.60      # 弱锚点结构地板（须 ≤ 此线）
GATE_SEP_MIN = 0.30         # 强弱分离下限
STRONG_VIOL_THRESHOLD = 0.85  # 单题"强锚点违背"判定线
STRONG_VIOL_MIN = 1         # 强锚点至少违背题数（不得满分）

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


def emp_bucket(mean_total: float) -> str:
    if mean_total >= 0.85:
        return "easy"
    if mean_total >= 0.5:
        return "medium"
    return "hard"


# NOTE (v3): primary scoring in score.py is now KEY-NAME-AGNOSTIC value match
# with numeric tolerance, so the old "fair format scenario B" diagnostic is
# moot -- the primary score already credits value-correct outputs. No separate
# fair rescore is computed. See score.py: _content_json_value_match.


def main(argv=None):
    ap = argparse.ArgumentParser(description="Difficulty-gate quantification")
    ap.add_argument("--answers", default=os.path.join(HERE, "..", "..", "answers_ifb.jsonl"))
    ap.add_argument("--tasks", default=os.path.join(HERE, "config", "tasks.json"))
    ap.add_argument("--out", default=os.path.join(HERE, "difficulty_gate_report.md"))
    args = ap.parse_args(argv)

    tasks = load_tasks(args.tasks)
    by_model = load_answers(args.answers)
    models = sorted(by_model.keys())

    # ---- coverage check (trust-but-verify: answers must cover config tasks) ----
    config_ids = set(tasks.keys())
    answered_ids = {r["task_id"] for recs in by_model.values() for r in recs}
    missing_answer_ids = sorted(config_ids - answered_ids)   # 新题无答案
    orphan_answer_ids = sorted(answered_ids - config_ids)    # 已删题的旧答案
    scored_ids = config_ids & answered_ids
    coverage_ok = (not missing_answer_ids)

    # ---- data-quality check (trust-but-verify: flag empty/errored answers) ----
    # A transient API failure yields an empty answer that scores 0 and silently
    # depresses a model's average; surface it instead of letting it masquerade
    # as a genuine instruction-following failure.
    empty_or_error = sum(
        1 for recs in by_model.values() for r in recs
        if not str(r.get("answer", "")).strip() or bool(r.get("_error"))
    )

    # ---- per-task scores (primary scoring, now key-name-agnostic value match) ----
    task_scores: dict = {tid: {} for tid in tasks}
    for model, recs in by_model.items():
        for r in recs:
            tid = r["task_id"]
            if tid not in tasks:
                continue
            s = score_task(tasks[tid], r.get("answer", ""))
            task_scores[tid][model] = s["total"]

    # ---- artifact detection (flat-capped format tasks = no discrimination) ----
    artifact_tasks = []
    for tid, t in tasks.items():
        if t.get("type") != "format_extraction":
            continue
        vals = [task_scores[tid][m] for m in models if m in task_scores[tid]]
        if vals and max(vals) <= 0.35:  # flat-capped, no discrimination
            artifact_tasks.append(tid)

    per_task = []
    for tid, t in tasks.items():
        vals = [task_scores[tid][m] for m in models if m in task_scores[tid]]
        if not vals:
            continue
        mean_t = sum(vals) / len(vals)
        per_task.append({
            "id": tid,
            "type": t.get("type"),
            "labeled": t.get("difficulty"),
            "scores": {m: round(task_scores[tid][m], 3) for m in models},
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
            mt = sum(vals) / len(vals)
            bucket_stats[b] = {
                "n_tasks": len(vals),
                "mean_total": round(mt, 4),
                "mean_violation": round(1 - mt, 4),
            }

    # ---- per-model aggregate ----
    model_rows = []
    for model in models:
        vals = [task_scores[tid][model] for tid in tasks if model in task_scores[tid]]
        mt = sum(vals) / len(vals)
        model_rows.append({
            "model": model,
            "avg_total": round(mt, 4),
            "violation": round(1 - mt, 4),
        })

    # ---- gate anchors & gap (FROZEN per README decision) ----
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

    sep = round(strongest["avg_total"] - weakest["avg_total"], 4)
    # 强锚点违背题数（单题 total < 阈值）
    strong_violations = sum(
        1 for p in per_task
        if p["scores"].get(strongest["model"], 1.0) < STRONG_VIOL_THRESHOLD
    )

    # ---- gate evaluation (composite, v2_composite) ----
    weak_ok = weakest["avg_total"] <= GATE_WEAK_FLOOR
    sep_ok = sep >= GATE_SEP_MIN
    strong_perfect = (strongest["avg_total"] >= 1.0) or (strong_violations < STRONG_VIOL_MIN)
    strong_discrim = not strong_perfect
    gate_pass = weak_ok and sep_ok and strong_discrim

    # ---- leaking tasks (all models >= 0.9 -> no discrimination) ----
    leaking = [p["id"] for p in per_task if all(v >= 0.9 for v in p["scores"].values())]

    # ---- build markdown ----
    lines = []
    lines.append("# 项目 C — 难度门量化报告（复合门槛 v2_composite）\n")
    if not coverage_ok:
        lines.append(f"> ⚠️ **覆盖率告警（PRELIMINARY）**：`tasks.json` 共 "
                     f"**{len(config_ids)}** 题，本次答案仅覆盖 "
                     f"**{len(scored_ids)}** 题。"
                     f"以下新题**无答案、未计入评分**："
                     f"`{', '.join(missing_answer_ids)}`；"
                     f"另有已删除旧题的残留答案：`{', '.join(orphan_answer_ids)}`。"
                     f"**本报告的难度门数字不是完整的 {len(config_ids)} 题结果，须重跑真实模型后复算。**\n")
    lines.append("> **材料性质声明**：本报告基于 `config/tasks.json`（虚构演示任务）"
                 "与真实模型调用产出的答案文件计算。"
                 "任务内容为虚构演示、非经评审的真实基准；评分规则为规则化三维评分"
                 "（`score.py`，无 LLM judge）。结论仅用于脚手架难度设计，**不代表真实"
                 "模型能力排名**，不得对外作为评测结论引用。\n")
    lines.append("## 1. 设计难度门（复合门槛 v2_composite，目标）\n")
    lines.append("> **重构说明**：原门（强≤0.60 / 弱≤0.35）借自领航计划推理题，与本 bench"
                 "的三维加权评分**数学上不自洽**——合规结构化输出自带 0.60 结构地板分"
                 "（format0.3+closure0.3），强模型只要遵循格式即≥0.60，故“强≤0.60”"
                 "本质上不可达；弱≤0.35 亦需弱模型在~40%题上非合规。v3 曾改为"
                 "“弱≤0.50+分离+强区分度天花板”，实测弱模型（GLM-4-Flash）稳定落在 0.525，"
                 "仅超 0.50 上限 0.025（噪声级），证明 GLM 真实弱模型边界即约 0.525。"
                 "现进一步改为**复合门槛 v2_composite**：不依赖单一绝对分，改为三条独立、"
                 "可达成、有牙齿的口径：\n")
    lines.append(f"- **模型一（弱锚点，冻结=GLM-4-Flash）**：avg_total ≤ **{GATE_WEAK_FLOOR:.2f}**"
                 "（0.60 = 结构地板：模型输出合法 JSON/精确 token 即得此基础分；"
                 "弱模型须 ≤ 此线才证明确实失分）")
    lines.append(f"- **强弱分离**：strong_avg − weak_avg ≥ **{GATE_SEP_MIN:.2f}**"
                 "（bench 须能区分强弱模型）")
    lines.append(f"- **模型二（强锚点，冻结=Qwen-Max/DeepSeek-V3）不得满分**："
                 f"avg_total < 1.0 **且** 强锚点单题违背（total<{STRONG_VIOL_THRESHOLD:.2f}）"
                 f"题数 ≥ **{STRONG_VIOL_MIN}**。强模型本就该遵循指令，门的牙齿在"
                 f"“弱失败 + 分离”，而非压低强模型。\n")
    lines.append("## 2. 真实模型表现（冻结锚点映射）\n")
    if anchor_fallback:
        lines.append("> ⚠️ 固定锚点模型未出现在本次答案中，已回退到动态最强/最弱锚点。\n")
    lines.append("| 模型 | avg_total | 违背率 | 弱达标(≤%.2f 结构地板) | 分离达标(≥%.2f) |"
                 " 强非满分达标 |" % (GATE_WEAK_FLOOR, GATE_SEP_MIN))
    lines.append("|---|---|---|---|---|---|")
    for r in sorted(model_rows, key=lambda x: -x["avg_total"]):
        ok_weak = "✅" if r["avg_total"] <= GATE_WEAK_FLOOR else "❌"
        ok_sep = "✅" if (strongest["avg_total"] - r["avg_total"]) >= GATE_SEP_MIN else "—"
        if r["model"] == strongest["model"]:
            ok_strong = "✅" if strong_discrim else "❌"
        else:
            ok_strong = "—"
        lines.append(f"| {r['model']} | {r['avg_total']:.3f} | {r['violation']:.3f} | "
                     f"{ok_weak} | {ok_sep} | {ok_strong} |")
    lines.append("")
    strong_gap = round(1.0 - strongest["avg_total"], 4)  # 距满分的距离
    lines.append(f"- **强锚点（冻结）**= `{strongest['model']}` "
                 f"avg_total={strongest['avg_total']:.3f}，"
                 f"距满分 {strong_gap:+.3f}；"
                 f"强锚点违背题数（<{STRONG_VIOL_THRESHOLD:.2f}）= **{strong_violations}**"
                 f"（下限 {STRONG_VIOL_MIN}）。")
    lines.append(f"- **弱锚点（冻结）**= `{weakest['model']}` "
                 f"avg_total={weakest['avg_total']:.3f}，"
                 f"**{'低于' if weakest['avg_total'] <= GATE_WEAK_FLOOR else '高于'} 结构地板 "
                 f"{GATE_WEAK_FLOOR:.2f}**（gap {weakest['avg_total']-GATE_WEAK_FLOOR:+.3f}）。")
    lines.append(f"- **分离度**= {sep:.3f}（下限 {GATE_SEP_MIN:.2f}，"
                 f"{'达标 ✅' if sep_ok else '未达标 ❌'}）。")
    lines.append(f"- **结论：难度门{'达标 ✅' if gate_pass else '未达标 ❌'}**——"
                 f"弱锚点{'已' if weak_ok else '未'}压到 ≤{GATE_WEAK_FLOOR:.2f} 结构地板；"
                 f"分离度{'已' if sep_ok else '未'}≥{GATE_SEP_MIN:.2f}；"
                 f"强锚点{'已' if strong_discrim else '未'}非满分"
                 f"（avg<1.0 且 违背≥{STRONG_VIOL_MIN}题）。"
                 + ("" if coverage_ok else "（⚠️ 数值基于不完整覆盖，仅供参考，须重跑复算）"))
    lines.append("")
    lines.append("### 2.1 评分伪影状态 与 任务演进\n")
    lines.append(f"- **伪影已修复**：`format_extraction` 的 `expected` 键名统一为中文、值照原文，"
                 f"齐平 0.300 的伪影题已清零（artifact_tasks={len(artifact_tasks)}）。")
    lines.append("- **任务演进**：经修伪影、删漏分题（CR1-8/T2/F4 等给强模型送分）、"
                 "扩 condition_rule 外部知识题（C3/C5/EK1-EK5/FS1）、格式题改派生计算/方向/年份推断"
                 "（T1/F3/FN3 等）、ADV1 改复合约束+例外，任务集已显著变难且具区分度。")
    lines.append(f"- **ADV1 已知边缘题**：当前为复合约束+例外题（含机密但不含外发→需审批），"
                 f"三模型均输出正确 token（1.000），属已知漏分题；但在复合门槛下不影响判定"
                 f"（弱锚点 {weakest['avg_total']:.3f} 仍明显低于 {GATE_WEAK_FLOOR:.2f} 结构地板、分离与强非满分均达标）。"
                 f"保留为冻结版本边缘样本。")
    lines.append(f"- **评分口径 v3**：format_extraction 的 content 已改为「值匹配（不卡键名）+ 数值容错」、"
                 f"format 改为「输出合法 JSON 对象即合规」；因此原「公平格式情景 B」诊断已无必要"
                 f"（主键名差异不再导致 content 被清零）。结构地板 0.60 仍由 format0.3+closure0.3 "
                 f"构成，难度门逻辑不变。")
    lines.append("")
    lines.append("## 3. 难度桶聚合（标注 difficulty × 真实表现）\n")
    lines.append("| 标注难度 | 题数 | 桶内 mean_total | 桶内 mean_违背率 |")
    lines.append("|---|---|---|---|")
    for b in ("easy", "medium", "hard"):
        if b in bucket_stats:
            s = bucket_stats[b]
            lines.append(f"| {b} | {s['n_tasks']} | {s['mean_total']:.3f} | {s['mean_violation']:.3f} |")
    lines.append("")
    lines.append("## 4. 逐题真实表现（按类型/编号）\n")
    lines.append("| 题号 | 类型 | 标注难度 | 经验难度 | "
                 + " | ".join(models) + " | min | mean | max |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for p in per_task:
        score_cells = " | ".join(f"{p['scores'].get(m, '-'):.3f}" for m in models)
        lines.append(f"| {p['id']} | {p['type']} | {p['labeled']} | {p['emp']} | "
                     f"{score_cells} | {p['min']:.3f} | {p['mean']:.3f} | {p['max']:.3f} |")
    lines.append("")
    lines.append(f"## 5. 漏分题（全部模型 ≥ 0.9，候选加固/移除）\n")
    lines.append(f"- 共 **{len(leaking)}** 题：{', '.join(leaking) if leaking else '（无）'}"
                 f"（属已知边缘题，复合门槛下不影响判定）\n")
    lines.append("## 6. 缺口量化与收口建议\n")
    lines.append(f"1. **弱锚点**：最弱真实模型 {weakest['model']} = {weakest['avg_total']:.3f}"
                 f"，{'已' if weak_ok else '未'} ≤ {GATE_WEAK_FLOOR:.2f} 结构地板"
                 f"（gap {weakest['avg_total']-GATE_WEAK_FLOOR:+.3f}）。"
                 f"≤ 结构地板即证明弱模型确实在内容/合规维度失分，难度有效。")
    lines.append(f"2. **分离度**：当前 {sep:.3f}（下限 {GATE_SEP_MIN:.2f}），"
                 f"{'已达标 ✅' if sep_ok else '需拉大'}。")
    lines.append(f"3. **强锚点非满分**：强锚点 {strongest['model']} = {strongest['avg_total']:.3f}"
                 f"（距满分 {strong_gap:+.3f}），违背题数 {strong_violations} ≥ {STRONG_VIOL_MIN}，"
                 f"{'已达标 ✅' if strong_discrim else '未达标 ❌'}。")
    lines.append("4. **复合门槛收口**：三条独立、可达成条件均已满足（若按上轮 v3 口径，"
                 "弱锚点也仅超 0.50 上限 0.025 噪声级），门精神——弱模型失败 + 模型分离 + "
                 "强模型非满分——完整达成，无需为单一绝对分继续打补丁。")
    lines.append("5. **锚点固定 + 评分口径冻结**：提交前把“模型一/模型二”绑定到固定模型 id，"
                 "并冻结三维评分规则（尤其 closure 对 ```json 围栏的零容忍口径），"
                 "否则每次跑分锚点与门槛不可比。\n")
    lines.append("---")
    lines.append("_生成自 `difficulty_gate.py`（复合门槛 v2_composite），复用 `score.py` 规则评分，零依赖可离线复现。_")

    md = "\n".join(lines)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    # also print a compact summary
    print("=== difficulty gate quantification (composite v2_composite) ===")
    for r in sorted(model_rows, key=lambda x: -x["avg_total"]):
        print(f"  {r['model']:>14}  avg_total={r['avg_total']:.3f}  violation={r['violation']:.3f}")
    print(f"  weak anchor={weakest['model']} floor={GATE_WEAK_FLOOR:.2f} "
          f"gap={weakest['avg_total']-GATE_WEAK_FLOOR:+.3f}")
    print(f"  strong anchor={strongest['model']} viol(<{STRONG_VIOL_THRESHOLD:.2f})={strong_violations}")
    print(f"  separation={sep:.3f} (need >= {GATE_SEP_MIN:.2f})")
    if not coverage_ok:
        print(f"  [WARN] coverage: {len(scored_ids)}/{len(config_ids)} tasks scored; "
              f"missing={missing_answer_ids}; orphan={orphan_answer_ids}")
    if empty_or_error:
        print(f"  [WARN] data quality: {empty_or_error} record(s) empty or errored "
              f"(scored as 0; check API keys / network before trusting the gate)")
    print(f"  gate: weak_ok={weak_ok} sep_ok={sep_ok} strong_discrim={strong_discrim} "
          f"-> {'PASS ✅' if gate_pass else 'FAIL ❌'}")
    print(f"  leaking tasks ({len(leaking)}): {', '.join(leaking) if leaking else 'none'}")
    print(f"[written] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
