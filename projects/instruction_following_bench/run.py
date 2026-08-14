# -*- coding: utf-8 -*-
"""Offline runner for the instruction-following benchmark (v0.1 scaffold).

Two modes
---------
1. ``--offline`` (default): uses two DUMMY baselines (random / empty) so the
   whole pipeline runs with zero dependencies and no network. The produced
   ``leaderboard.csv`` is a DEMO scaffold, NOT a real model ranking.

2. ``--score-answers PATH``: scores a real ``answers_ifb.jsonl`` produced by
   ``models.generate_answers`` (which calls real models when API keys are set).
   This yields a REAL, reproducible leaderboard.

No LLM judge is used anywhere; scoring is rule-based (see score.py).
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import random

from .score import score_task
from . import report

HERE = os.path.dirname(os.path.abspath(__file__))
TASKS_PATH = os.path.join(HERE, "config", "tasks.json")
LEADERBOARD_PATH = os.path.join(HERE, "leaderboard.csv")


# ---- dummy baselines (offline, no network) ----
def _random_baseline(task: dict) -> str:
    random.seed((hash(task.get("id")) & 0xFFFFFFFF) ^ 0x9E3779B9)
    ttype = task.get("type")
    if ttype == "multi_turn_constraint":
        return random.choice(task.get("allowed", ["同意", "拒绝"]))
    if ttype == "fewshot_classify":
        return random.choice(["A", "B", "C", "D"])
    return '{"result": "unknown", "note": "随机基线，无实际依据"}'


def _empty_baseline(task: dict) -> str:
    return ""


DUMMY_MODELS = {
    "RandomBaseline": _random_baseline,
    "EmptyBaseline": _empty_baseline,
}


def load_tasks(path: str = TASKS_PATH) -> list:
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, list) else data.get("tasks", [])


def _aggregate(models: dict, tasks: list) -> list:
    rows = []
    for name, fn in models.items():
        agg = {"format": 0.0, "content": 0.0, "closure": 0.0, "total": 0.0}
        for t in tasks:
            s = score_task(t, fn(t))
            for k in ("format", "content", "closure", "total"):
                agg[k] += s[k]
        n = len(tasks) or 1
        rows.append({
            "model": name,
            "tasks": len(tasks),
            "avg_format": round(agg["format"] / n, 4),
            "avg_content": round(agg["content"] / n, 4),
            "avg_closure": round(agg["closure"] / n, 4),
            "avg_total": round(agg["total"] / n, 4),
            "instruction_violation_rate": round(1 - agg["total"] / n, 4),
        })
    rows.sort(key=lambda r: r["avg_total"], reverse=True)
    return rows


def run_offline(tasks_path: str = TASKS_PATH, out_path: str = LEADERBOARD_PATH) -> list:
    tasks = load_tasks(tasks_path)
    rows = _aggregate(DUMMY_MODELS, tasks)
    _write(rows, out_path)
    html_path = report.write_html(rows, "demo", out_path)
    print(f"[written] {out_path}\n[written] {html_path}  (DEMO: not a real ranking)")
    return rows


def score_answers(answers_path: str, tasks_path: str = TASKS_PATH,
                  out_path: str = LEADERBOARD_PATH) -> list:
    tasks = {t["id"]: t for t in load_tasks(tasks_path)}
    by_model: dict = {}
    with open(answers_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            r = json.loads(line)
            by_model.setdefault(r["model"], []).append(r)
    rows = []
    for model, recs in by_model.items():
        agg = {"format": 0.0, "content": 0.0, "closure": 0.0, "total": 0.0}
        n = 0
        for r in recs:
            t = tasks.get(r["task_id"])
            if not t:
                continue
            s = score_task(t, r.get("answer", ""))
            for k in ("format", "content", "closure", "total"):
                agg[k] += s[k]
            n += 1
        n = max(n, 1)
        rows.append({
            "model": model,
            "tasks": n,
            "avg_format": round(agg["format"] / n, 4),
            "avg_content": round(agg["content"] / n, 4),
            "avg_closure": round(agg["closure"] / n, 4),
            "avg_total": round(agg["total"] / n, 4),
            "instruction_violation_rate": round(1 - agg["total"] / n, 4),
        })
    rows.sort(key=lambda r: r["avg_total"], reverse=True)
    _write(rows, out_path)
    html_path = report.write_html(rows, "real", out_path)
    print(f"[written] {out_path}\n[written] {html_path}  (REAL: reproducible from answers)")
    return rows


def _write(rows: list, out_path: str) -> None:
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)


def _print(rows: list, note: str) -> None:
    print("=== instruction-following leaderboard ===")
    for r in rows:
        print(f"{r['model']:>14}  total={r['avg_total']:.3f}  "
              f"violation={r['instruction_violation_rate']:.3f}")
    print(f"\n[written] leaderboard.csv")
    print(f"[note] {note}")


def main(argv=None):
    ap = argparse.ArgumentParser(description="Instruction-following bench runner")
    ap.add_argument("--offline", action="store_true",
                    help="dummy baselines (default when no other mode given)")
    ap.add_argument("--score-answers", metavar="PATH",
                    help="score a real answers jsonl (from models.generate_answers)")
    ap.add_argument("--tasks", default=TASKS_PATH)
    ap.add_argument("--out", default=LEADERBOARD_PATH)
    args = ap.parse_args(argv)

    if args.score_answers:
        rows = score_answers(args.score_answers, args.tasks, args.out)
        _print(rows, "REAL leaderboard from the provided answers file. "
                     "Scores are reproducible given the same answers.")
    else:
        rows = run_offline(args.tasks, args.out)
        _print(rows, "DEMO scaffold: scores come from DUMMY baselines "
                     "(random/empty). NOT a real model ranking. Plug real "
                     "models via projects.instruction_following_bench.models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
