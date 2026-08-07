"""Chunked, subprocess-isolated offline pipeline runner.

Motivation
----------
The full ``audit()`` over the 115-real-record ``answers.jsonl`` cannot run in a
single process: ``verify_citation`` performs a cross-law misattribution scan
that now iterates over the 10x-expanded corpus (2327 verified nodes vs 212),
so a single process exhausts the sandbox resource budget (~15–20 records in,
SIGKILL at ~115).

Fix: split the records into small chunks and run each chunk in a *fresh
subprocess* (``worker`` mode). Each worker loads the laws, verifies its chunk,
and writes its verification dicts to a per-chunk JSONL, then exits — so the
per-process resource budget is never exceeded. The parent (``driver`` mode)
only merges the per-chunk files and calls ``build_report`` (cheap I/O + metric
math, no corpus scans), which fits comfortably in one process.

Usage
-----
    # run the whole thing (default chunk size 8)
    PYTHONPATH=. python3 scripts/run_engine_chunked.py \
        --input answers.jsonl --out-dir benchmark/reports

    # tweak chunk size if a worker still gets killed
    ... --chunk 5

This reproduces byte-for-byte the same ``benchmark/reports/*`` artifacts that
``benchmark/run.py --offline --input answers.jsonl`` produces, just split
across processes.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# --------------------------------------------------------------------------- #
# Worker: process one chunk in a fresh subprocess
# --------------------------------------------------------------------------- #
def _worker(in_path: str, out_path: str) -> int:
    """Load laws, run the pipeline over ``in_path`` records, write verification
    dicts (plus ``model``) to ``out_path``. Returns process exit code."""
    from knowledge_base.loader import load_laws, normalize_as_of
    from benchmark.pipeline import run_answer
    from dataclasses import asdict

    laws = load_laws()
    records = [json.loads(l) for l in open(in_path, encoding="utf-8") if l.strip()]
    n = 0
    with open(out_path, "w", encoding="utf-8") as f:
        for rec in records:
            model = rec.get("model", "unknown")
            qid = rec.get("question_id", "")
            vs = run_answer(
                rec.get("answer", ""),
                normalize_as_of(rec.get("as_of_date")) or "2025-01-01",
                laws=laws,
                gold_candidates=rec.get("candidates"),
                question_id=qid,
            )
            for v in vs:
                d = asdict(v)
                d["model"] = model
                f.write(json.dumps(d, ensure_ascii=False) + "\n")
                n += 1
    sys.stderr.write(f"[worker] {len(records)} records -> {n} verifications\n")
    return 0


# --------------------------------------------------------------------------- #
# Driver: split -> subprocess workers -> merge -> build_report
# --------------------------------------------------------------------------- #
def _driver(input_path: str, out_dir: str, chunk: int,
            python_exe: str) -> int:
    from benchmark.pipeline import build_report
    from benchmark.verify import Verification

    records = [json.loads(l) for l in open(input_path, encoding="utf-8")
               if l.strip()]
    print(f"[driver] {len(records)} records, chunk={chunk}")

    tmp = tempfile.mkdtemp(prefix="lhb_chunk_")
    chunk_files = []
    verif_files = []
    for i in range(0, len(records), chunk):
        piece = records[i:i + chunk]
        cf = os.path.join(tmp, f"chunk_{i:04d}.jsonl")
        vf = os.path.join(tmp, f"verifs_{i:04d}.jsonl")
        with open(cf, "w", encoding="utf-8") as f:
            for r in piece:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        chunk_files.append(cf)
        verif_files.append(vf)

    # run each chunk in its own (budget-reset) subprocess
    for cf, vf in zip(chunk_files, verif_files):
        proc = subprocess.run(
            [python_exe, __file__, "worker", "--in", cf, "--out", vf],
            cwd=ROOT, env={**os.environ, "PYTHONPATH": ROOT},
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            sys.stderr.write(f"[driver] WORKER FAILED ({cf}):\n{proc.stdout}\n{proc.stderr}\n")
            return proc.returncode
        sys.stderr.write(proc.stderr)
        if not os.path.isfile(vf) or os.path.getsize(vf) == 0:
            sys.stderr.write(f"[driver] worker produced no output for {cf}\n")
            return 1

    # merge per-chunk verification files into one flat list
    flat = []
    for vf in verif_files:
        for line in open(vf, encoding="utf-8"):
            line = line.strip()
            if line:
                flat.append(json.loads(line))
    print(f"[driver] merged {len(flat)} verifications")

    # reconstruct the audit_result shape build_report expects
    audit_result = {}
    for r in flat:
        model = r.get("model", "unknown")
        if model not in audit_result:
            audit_result[model] = {"verifications": [], "n_citations": 0,
                                   "report": None}
        # rebuild Verification objects (dataclass is kwargs-friendly)
        v = Verification(**{k: v for k, v in r.items() if k != "model"})
        audit_result[model]["verifications"].append(v)
        audit_result[model]["n_citations"] += 1
    from benchmark.score import score
    for model, d in audit_result.items():
        d["report"] = score(d["verifications"])

    build_report(audit_result, out_dir)

    # print a compact leaderboard summary
    print("\n=== Leaderboard (by HR_statutory, lower=better) ===")
    rows = []
    for model, d in audit_result.items():
        # recompute metrics inline (build_report already wrote them, but we
        # want the summary here without re-importing score internals)
        from benchmark.score import score
        rep = score(d["verifications"])
        m = rep.metrics
        rows.append((m.get("hr_statutory", 1.0), model, m, d["n_citations"]))
    for hr, model, m, n in sorted(rows):
        print(f"  {model:18s} HVI={m.get('hr_statutory', 0):.1%} "
              f"content={m.get('hr_content', 0):.1%} "
              f"CRFI={m.get('crfi', 0):.1%} "
              f"deprecated={m.get('rate_deprecated', 0):.1%} "
              f"unverif={m.get('rate_unverifiable', 0):.1%} n={n}")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=["worker", "driver"],
                    help="worker = process one chunk; driver = orchestrate")
    ap.add_argument("--in", dest="in_path", default=None)
    ap.add_argument("--out", dest="out_path", default=None)
    ap.add_argument("--input", default="answers.jsonl",
                    help="driver: path to answers.jsonl")
    ap.add_argument("--out-dir", default=None,
                    help="driver: reports output dir")
    ap.add_argument("--chunk", type=int, default=8,
                    help="driver: records per worker subprocess")
    ap.add_argument("--python", default=sys.executable,
                    help="driver: python executable for workers")
    args = ap.parse_args(argv)

    if args.mode == "worker":
        if not args.in_path or not args.out_path:
            sys.stderr.write("--in and --out required for worker mode\n")
            return 2
        return _worker(args.in_path, args.out_path)

    # driver
    out_dir = args.out_dir or os.path.join(ROOT, "benchmark", "reports")
    return _driver(args.input, out_dir, args.chunk, args.python)


if __name__ == "__main__":
    sys.exit(main())
