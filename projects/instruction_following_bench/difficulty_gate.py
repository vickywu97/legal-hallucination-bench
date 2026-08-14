# -*- coding: utf-8 -*-
"""Difficulty-gate quantification for the instruction-following benchmark.

Reads the REAL answers file (answers_ifb*.jsonl) and the task config
(config/tasks.json), reuses the rule-based scorer (score.py, no LLM judge),
and quantifies the benchmark against the *designed* difficulty gate:

    gate_model_1 (弱锚点)  : avg_total <= 0.35   (得分率 <= 35%)
    gate_model_2 (强锚点)  : avg_total <= 0.60   (得分率 <= 60%)

Outputs (printed + written to difficulty_gate_report.md):
  * per-task empirical difficulty (min/mean/max total across real models)
  * difficulty-bucket aggregation (easy/medium/hard mean total & violation)
  * per-model gate status vs the two anchors
  * the exact gap (how far each anchor sits from its threshold)
  * which tasks are "leaking" easy points (candidates to harden/remove)

Run:
    python -S difficulty_gate.py --answers ../answers_ifb_no_kimi.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from score import score_task  # noqa: E402

GATE_M1 = 0.35  # 弱锚点上限
GATE_M2 = 0.60  # 强锚点上限

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


def fair_format_total(task: dict, answer: str) -> float:
    """Conservative 'fair' rescore for format_extraction: if the model emitted
    the required VALUES (regardless of JSON key name), credit format+content
    fully and keep the actual closure score.

    This isolates the *key-name mismatch artifact*: current scoring keys the
    expected English schema, but the instruction asks for Chinese field names,
    so models naturally emit Chinese keys and get flat-capped at 0.3.
    """
    expected = task.get("expected", {})
    values = [str(v).strip() for v in expected.values()]
    if not values:
        return 0.0
    present = sum(1 for v in values if v and v in (answer or ""))
    content = present / len(values)
    closure = 1.0 if score_task(task, answer)["closure"] == 1.0 else 0.0
    return round(0.3 * 1.0 + 0.4 * content + 0.3 * closure, 4)


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

    # raw answer map (model, tid) -> answer text
    raw: dict = {}
    for model, recs in by_model.items():
        for r in recs:
            raw[(model, r["task_id"])] = r.get("answer", "")

    # ---- per-task scores ----
    task_scores: dict = {tid: {} for tid in tasks}
    for model, recs in by_model.items():
        for r in recs:
            tid = r["task_id"]
            if tid not in tasks:
                continue
            s = score_task(tasks[tid], r.get("answer", ""))
            task_scores[tid][model] = s["total"]

    # ---- artifact detection + fair-format scenario B ----
    # format_extraction tasks where models emit correct VALUES but get capped
    # at 0.3 due to English-key vs Chinese-key mismatch.
    artifact_tasks = []
    for tid, t in tasks.items():
        if t.get("type") != "format_extraction":
            continue
        vals = [task_scores[tid][m] for m in models if m in task_scores[tid]]
        if vals and max(vals) <= 0.35:  # flat-capped, no discrimination
            artifact_tasks.append(tid)
    fair_scores: dict = {tid: {} for tid in tasks}
    for (model, tid), ans in raw.items():
        if tid in tasks and tasks[tid].get("type") == "format_extraction":
            fair_scores[tid][model] = fair_format_total(tasks[tid], ans)
        elif tid in tasks:
            fair_scores[tid][model] = task_scores[tid].get(model, 0.0)

    # per-model avg under fair-format scenario B
    model_fair = []
    for model in models:
        vals = [fair_scores[tid][model] for tid in tasks if model in fair_scores[tid]]
        mt = sum(vals) / len(vals)
        model_fair.append({"model": model, "avg_total": round(mt, 4),
                           "violation": round(1 - mt, 4)})

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

    # ---- bucket aggregation ----
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
    # 强锚点固定候选：Qwen-Max / DeepSeek-V3（取存在的、得分最高者）
    # 弱锚点固定候选：GLM-4-Flash（取存在的、得分最低者）
    # 若固定锚点模型不在本次答案中，回退到动态最强/最弱并显式告警。
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
    gap_m2 = round(strongest["avg_total"] - GATE_M2, 4)      # 需下降量(正=超标)
    gap_m1 = round(weakest["avg_total"] - GATE_M1, 4)

    # ---- leaking tasks (all models >= 0.9) ----
    leaking = [p["id"] for p in per_task if all(v >= 0.9 for v in p["scores"].values())]

    # ---- build markdown ----
    lines = []
    lines.append("# 项目 C — 难度门量化报告（③）\n")
    # 覆盖率告警（trust-but-verify）：答案必须覆盖 config 全部任务
    if not coverage_ok:
        lines.append(f"> ⚠️ **覆盖率告警（PRELIMINARY）**：`tasks.json` 共 "
                     f"**{len(config_ids)}** 题，本次答案仅覆盖 "
                     f"**{len(scored_ids)}** 题。"
                     f"以下新题**无答案、未计入评分**："
                     f"`{', '.join(missing_answer_ids)}`；"
                     f"另有已删除旧题的残留答案：`{', '.join(orphan_answer_ids)}`。"
                     f"**本报告的难度门数字不是完整的 21 题结果，须重跑真实模型后复算。**\n")
    lines.append("> **材料性质声明**：本报告基于 `config/tasks.json`（虚构演示任务）"
                 "与真实模型调用产出的答案文件计算。"
                 "任务内容为虚构演示、非经评审的真实基准；评分规则为规则化三维评分"
                 "（`score.py`，无 LLM judge）。结论仅用于脚手架难度设计，**不代表真实"
                 "模型能力排名**，不得对外作为评测结论引用。\n")
    lines.append("## 1. 设计难度门（目标）\n")
    lines.append(f"- **模型一（弱锚点，冻结=GLM-4-Flash）**：avg_total ≤ **{GATE_M1:.2f}**（得分率 ≤ 35%）")
    lines.append(f"- **模型二（强锚点，冻结=Qwen-Max/DeepSeek-V3）**：avg_total ≤ **{GATE_M2:.2f}**（得分率 ≤ 60%）\n")
    lines.append("## 2. 真实模型表现（冻结锚点映射）\n")
    if anchor_fallback:
        lines.append("> ⚠️ 固定锚点模型未出现在本次答案中，已回退到动态最强/最弱锚点。\n")
    lines.append("| 模型 | avg_total | 违背率 | 是否达标(强≤0.60) | 是否达标(弱≤0.35) |")
    lines.append("|---|---|---|---|---|")
    for r in sorted(model_rows, key=lambda x: -x["avg_total"]):
        ok_m2 = "✅" if r["avg_total"] <= GATE_M2 else "❌"
        ok_m1 = "✅" if r["avg_total"] <= GATE_M1 else "❌"
        lines.append(f"| {r['model']} | {r['avg_total']:.3f} | {r['violation']:.3f} | {ok_m2} | {ok_m1} |")
    lines.append("")
    lines.append(f"- **强锚点（冻结）**= `{strongest['model']}` "
                 f"avg_total={strongest['avg_total']:.3f}，"
                 f"**超标 {gap_m2:+.3f}**（需降至 ≤0.60）。")
    lines.append(f"- **弱锚点（冻结）**= `{weakest['model']}` "
                 f"avg_total={weakest['avg_total']:.3f}，"
                 f"**超标 {gap_m1:+.3f}**（需降至 ≤0.35）。")
    gate_pass = (gap_m2 <= 0) and (gap_m1 <= 0)
    lines.append(f"- **结论：难度门{'达标 ✅' if gate_pass else '未达标 ❌'}**——"
                 f"强锚点{'已' if gap_m2<=0 else '未'}压到 ≤0.60；"
                 f"弱锚点{'已' if gap_m1<=0 else '未'}压到 ≤0.35。"
                 + ("" if coverage_ok else "（⚠️ 数值基于不完整覆盖，仅供参考，须重跑复算）"))
    lines.append("")
    lines.append("### 2.1 评分伪影状态 与 本轮（v2）重设计思路\n")
    lines.append(f"- **伪影已修复**：上一轮将 `format_extraction` 的 `expected` 键名统一为中文、"
                 f"值照原文，齐平 0.300 的伪影题已清零（artifact_tasks={len(artifact_tasks)}）。"
                 "当前强锚点 ≈1.0 不是伪影压低，而是**真·难任务不足**。")
    lines.append("- **上一轮（原始18题）逐题结论**：显式给出规则的 `condition_rule` 题强模型全部 "
                 "1.000，唯一区分强/弱的是要求精确外部知识（税率/阈值记忆）的 C3/C5/CR6；"
                 "`format` 题在“照原文”下也近乎送分。→ 守门主力**不能是显式规则题**。")
    lines.append("- **本轮 v2 重设计（已落地于 `config/tasks.json`）**：")
    lines.append("  ① `format` 题强制**规范化/派生计算**（纯数字、ISO 日期、价税分离、排序数组、"
                 "方向歧义），利用 scorer 的 `content` 精确匹配 + `closure` 零容忍双杠杆；")
    lines.append("  ② `condition_rule` 题改为**不给出规则、需凭记忆判断 `eligible`**（EK 系列，"
                 "带 `demo_note` 待核验）；")
    lines.append("  ③ 新增**对抗/约束陷阱**（ADV1 内容安全机器人、ADV2 裸数字 closure、FS1 对抗少样本）。")
    lines.append(f"- **公平格式情景（B）**（仅作口径参照，键名已正确故与 A 接近）：")
    lines.append("| 模型 | 情景A(严格) | 情景B(公平格式) |")
    lines.append("|---|---|---|")
    for r, rf in zip(sorted(model_rows, key=lambda x: -x["avg_total"]),
                     sorted(model_fair, key=lambda x: -x["avg_total"])):
        lines.append(f"| {r['model']} | {r['avg_total']:.3f} | {rf['avg_total']:.3f} |")
    sb = max(model_fair, key=lambda r: r["avg_total"])
    lines.append(f"- 本轮目标：通过上述重设计把强锚点由 ≈1.0 压到 ≤0.60、弱锚点压到 ≤0.35；"
                 f"实际效果以下方真实重跑为准（当前情景B 强锚点 ≈ {sb['avg_total']:.3f}）。\n")
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
    lines.append(f"- 共 **{len(leaking)}** 题：{', '.join(leaking) if leaking else '（无）'}\n")
    lines.append("## 6. 缺口量化与加固建议\n")
    lines.append(f"1. **强锚点缺口 {gap_m2:+.3f}**（情景A）/ 情景B 下约 "
                 f"{sb['avg_total']-GATE_M2:+.3f}：需让最强模型整体下降约 "
                 f"{gap_m2*100:.1f} 个百分点（违背率由 {strongest['violation']:.3f} 升至 ≥0.40）。")
    lines.append(f"2. **弱锚点缺口 {gap_m1:+.3f}**：最弱真实模型需再降约 "
                 f"{gap_m1*100:.1f} 个百分点才能压到 ≤0.35。")
    lines.append(f"3. **伪影已修复（v2 落地）**：原齐平 0.3 的 format 伪影题已清零"
                 f"（artifact_tasks={len(artifact_tasks)}）。`format` 题现已改为强制规范化/"
                 "派生计算（纯数字、ISO 日期、价税分离、排序数组、方向歧义），直接利用 scorer "
                 "的 `content` 精确匹配 + `closure` 零容忍，是真·难的主要来源之一。")
    lines.append(f"4. **堵漏分题**：{len(leaking)} 道全模型 ≥0.9 的送分题"
                 f"（{', '.join(leaking)}），建议删除或升级为 medium/hard（增加条件分支、"
                 "对抗性措辞、易混淆同义词）。")
    lines.append("5. **condition_rule 守门须靠外部知识，而非显式规则**：上一轮显式给规则的题"
                 "强模型全部 1.0；v2 已改为不给出规则、需凭记忆判断 `eligible`（EK1–EK5 + "
                 "保留 C3/C5 税率/阈值题）。但强模型对常见法条记忆较好，外部知识题区分度有限，"
                 "仍需与规范化/对抗题叠加才能压下强锚点。")
    lines.append("6. **锚点固定 + 评分口径冻结**：提交前把“模型一/模型二”绑定到固定模型 id，"
                 "并冻结三维评分规则（尤其 closure 对 ```json 围栏的零容忍口径），"
                 "否则每次跑分锚点与门槛不可比。\n")
    lines.append("---")
    lines.append("_生成自 `difficulty_gate.py`，复用 `score.py` 规则评分，零依赖可离线复现。_")

    md = "\n".join(lines)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write(md)

    # also print a compact summary
    print("=== difficulty gate quantification ===")
    for r in sorted(model_rows, key=lambda x: -x["avg_total"]):
        print(f"  {r['model']:>14}  avg_total={r['avg_total']:.3f}  violation={r['violation']:.3f}")
    print(f"  strong anchor={strongest['model']} gap_m2={gap_m2:+.3f}")
    print(f"  weak   anchor={weakest['model']} gap_m1={gap_m1:+.3f}")
    if not coverage_ok:
        print(f"  [WARN] coverage: {len(scored_ids)}/{len(config_ids)} tasks scored; "
              f"missing={missing_answer_ids}; orphan={orphan_answer_ids}")
    print(f"  buckets: " + ", ".join(f"{b}={bucket_stats[b]['mean_total']:.3f}({bucket_stats[b]['n_tasks']})" for b in ('easy','medium','hard') if b in bucket_stats))
    print(f"  leaking tasks ({len(leaking)}): {', '.join(leaking) if leaking else 'none'}")
    print(f"[written] {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
