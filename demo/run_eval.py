"""Run the annotate.py --candidates strict-eval loop end-to-end.

Two passes, into separate report dirs, so the contrast is visible:
  * reports_heuristic : NO candidates  -> relies on the noisy candidate_window
  * reports_strict    : WITH expert candidates -> clean, content-level binary eval

This mirrors `python -m benchmark.run --input answers.jsonl [--candidates ...]`
but writes to demo/ instead of benchmark/reports/ (so the canonical offline
reports are not clobbered).
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from benchmark.pipeline import audit, build_report

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEMO = os.path.join(ROOT, "demo")


def load_records():
    path = os.path.join(DEMO, "answers.jsonl")
    return [json.loads(l) for l in open(path, encoding="utf-8") if l.strip()]


def load_expert_candidates():
    file_cands = {}
    for line in open(os.path.join(DEMO, "candidates.expert.jsonl"), encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        obj = json.loads(line)
        file_cands[obj["model"]] = obj.get("candidates", {})
    return file_cands


def merge(records, file_cands):
    out = []
    for rec in records:
        m = rec.get("model", "unknown")
        r = dict(rec)
        if m in file_cands:
            merged = dict(file_cands[m])
            merged.update(rec.get("candidates", {}))
            r["candidates"] = merged
        out.append(r)
    return out


def summarize(label, result):
    print(f"\n=== {label} ===")
    for model, d in result.items():
        m = d["report"].metrics
        print(f"  {model:14s} HR_statutory={m.get('hr_statutory',0):.0%} "
              f"HR_content={m.get('hr_content',0):.0%} "
              f"deprecated={m.get('rate_deprecated',0):.0%} "
              f"n={d['n_citations']}")
        for v in d["verifications"]:
            print(f"      {v.citation_raw:14s} -> {v.verdict:13s} "
                  f"{v.category:14s} {v.diff_level or '-':10s} "
                  f"score={v.score:.2f}")


def main():
    records = load_records()
    file_cands = load_expert_candidates()

    # Pass 1: heuristic window only (no gold candidates)
    h_result = audit(records)
    build_report(h_result, os.path.join(DEMO, "reports_heuristic"))
    summarize("HEURISTIC (no --candidates)", h_result)

    # Pass 2: strict, with expert-annotated candidates
    s_records = merge(records, file_cands)
    s_result = audit(s_records)
    build_report(s_result, os.path.join(DEMO, "reports_strict"))
    summarize("STRICT (--candidates, expert-annotated)", s_result)

    print("\nwrote demo/reports_heuristic/ and demo/reports_strict/")


if __name__ == "__main__":
    main()
