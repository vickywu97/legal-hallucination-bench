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
# Held-out anti-gaming set. Lives at the project root, PHYSICALLY ISOLATED from
# the public tasks.json, and is git-ignored so it is NEVER published. The public
# leaderboard must not reveal these tasks; only the aggregated "hidden_total"
# column (when --include-hidden is passed) is shown internally.
HIDDEN_PATH = os.path.join(HERE, "hidden_tasks.json")
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


def load_hidden(path: str = HIDDEN_PATH) -> list:
    """Load the held-out (non-public) task set used to prevent leaderboard
    gaming. Returns [] when the file is absent (e.g. not published), so the
    pipeline still runs without it."""
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    tasks = data if isinstance(data, list) else data.get("tasks", [])
    for t in tasks:
        t["hidden"] = True
    return tasks


def _score_task_aggregate(t: dict, out) -> dict:
    """Score one task output, or a list of repeated outputs (--repeat N).

    Returns the per-dimension MEAN across the repeats (mirrors
    difficulty_gate.py's aggregation so the leaderboard and the gate agree).
    """
    outs = out if isinstance(out, list) else [out]
    agg = {"format": 0.0, "content": 0.0, "closure": 0.0, "total": 0.0}
    for o in outs:
        s = score_task(t, o)
        for k in agg:
            agg[k] += s[k]
    n = max(len(outs), 1)
    return {k: agg[k] / n for k in agg}


def _pstdev(xs) -> float:
    """Population standard deviation (stability band across tasks)."""
    if len(xs) < 2:
        return 0.0
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / len(xs)) ** 0.5


def _row_from(model: str, public_pairs: list, hidden_pairs=None) -> dict:
    pub_task_totals = []
    agg = {"format": 0.0, "content": 0.0, "closure": 0.0, "total": 0.0}
    for t, out in public_pairs:
        g = _score_task_aggregate(t, out)
        for k in agg:
            agg[k] += g[k]
        pub_task_totals.append(g["total"])
    n = max(len(public_pairs), 1)
    pub = {k: round(agg[k] / n, 4) for k in agg}
    std = round(_pstdev(pub_task_totals), 4)
    row = {
        "model": model,
        "tasks": len(public_pairs),
        "avg_format": pub["format"],
        "avg_content": pub["content"],
        "avg_closure": pub["closure"],
        "avg_total": pub["total"],
        "avg_total_std": std,
        "instruction_violation_rate": round(1 - pub["total"], 4),
    }
    if hidden_pairs:
        hid_task_totals = []
        ha = {"format": 0.0, "content": 0.0, "closure": 0.0, "total": 0.0}
        for t, out in hidden_pairs:
            g = _score_task_aggregate(t, out)
            for k in ha:
                ha[k] += g[k]
            hid_task_totals.append(g["total"])
        hn = max(len(hidden_pairs), 1)
        hid = {k: round(ha[k] / hn, 4) for k in ha}
        row["hidden_tasks"] = len(hidden_pairs)
        row["hidden_total"] = hid["total"]
        row["hidden_total_std"] = round(_pstdev(hid_task_totals), 4)
        row["hidden_violation"] = round(1 - hid["total"], 4)
    return row


def run_offline(tasks_path: str = TASKS_PATH, out_path: str = LEADERBOARD_PATH,
                hidden: bool = False, hidden_path: str = HIDDEN_PATH) -> list:
    public = load_tasks(tasks_path)
    hidden_tasks = load_hidden(hidden_path) if hidden else []
    rows = []
    for name, fn in DUMMY_MODELS.items():
        pub_pairs = [(t, fn(t)) for t in public]
        hid_pairs = [(t, fn(t)) for t in hidden_tasks] or None
        rows.append(_row_from(name, pub_pairs, hid_pairs))
    rows.sort(key=lambda r: r["avg_total"], reverse=True)
    _write(rows, out_path)
    html_path = report.write_html(rows, "demo", out_path, hidden_count=len(hidden_tasks),
                                  with_hidden_label=hidden)
    print(f"[written] {out_path}\n[written] {html_path}  (DEMO: not a real ranking)")
    return rows


def score_answers(answers_path: str, tasks_path: str = TASKS_PATH,
                  out_path: str = LEADERBOARD_PATH, hidden: bool = False,
                  hidden_path: str = HIDDEN_PATH) -> list:
    public = load_tasks(tasks_path)
    public_by_id = {t["id"]: t for t in public}
    hidden_tasks = load_hidden(hidden_path) if hidden else []
    hidden_by_id = {t["id"]: t for t in hidden_tasks}
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
        pub_pairs, hid_pairs = [], []
        for r in recs:
            tid = r["task_id"]
            # Prefer the repeated-outputs list (--repeat N); fall back to the
            # single 'answer' for back-compat with older answers files.
            out = r.get("outputs")
            if not out:
                out = r.get("answer", "")
            if tid in public_by_id:
                pub_pairs.append((public_by_id[tid], out))
            elif tid in hidden_by_id:
                hid_pairs.append((hidden_by_id[tid], out))
        rows.append(_row_from(model, pub_pairs, hid_pairs or None))
    rows.sort(key=lambda r: r["avg_total"], reverse=True)
    _write(rows, out_path)
    html_path = report.write_html(rows, "real", out_path, hidden_count=len(hidden_tasks),
                                  with_hidden_label=hidden)
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
    ap.add_argument("--include-hidden", action="store_true",
                    help="also score the held-out hidden set (hidden_tasks.json at "
                         "the project root, git-ignored and NOT published); used to "
                         "prevent leaderboard gaming. Only works where that file exists.")
    args = ap.parse_args(argv)

    if args.score_answers:
        rows = score_answers(args.score_answers, args.tasks, args.out,
                             hidden=args.include_hidden)
        _print(rows, "REAL leaderboard from the provided answers file. "
                     "Scores are reproducible given the same answers.")
    else:
        rows = run_offline(args.tasks, args.out, hidden=args.include_hidden)
        _print(rows, "DEMO scaffold: scores come from DUMMY baselines "
                     "(random/empty). NOT a real model ranking. Plug real "
                     "models via projects.instruction_following_bench.models.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
