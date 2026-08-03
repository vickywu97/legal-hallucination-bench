"""Gold-candidate annotation tool (Week 6).

Produces a human-editable ``candidates.jsonl`` from a model-answer file so an
expert can align verified statute text to each citation. Supplying gold
candidate text enables STRICT content-level evaluation, instead of the
approximate ``candidate_window`` heuristic used by default.

Usage
-----
    python -m benchmark.annotate --input answers.jsonl --output candidates.jsonl

Input  (answers.jsonl): each line ``{"model", "as_of_date", "answer"}``.
Output (candidates.jsonl): one line per model record:
    {
      "model": "...",
      "as_of_date": "...",
      "citations": {                                  # reference metadata
        "0": {"raw": "《刑法》第232条",
              "auto_candidate": "<heuristic window>",
              "ground_truth_head": "<verified official text, truncated>"}
      },
      "candidates": {"0": "<EDIT HERE = auto_candidate by default>"}
    }

The expert edits the ``candidates`` values (or leaves them = auto_candidate),
then runs the pipeline with ``--candidates candidates.jsonl`` for strict eval.
The pipeline merges file candidates into each record; per-record ``candidates``
in the input override the file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from knowledge_base.loader import load_laws
from benchmark.extract import extract
from benchmark.pipeline import candidate_window
from benchmark.verify import _resolve_citation, ground_truth_verified


def build_skeleton(records: List[dict], laws: Optional[Dict] = None) -> List[dict]:
    """Build the editable candidate skeleton for a list of answer records."""
    if laws is None:
        laws = load_laws()
    out: List[dict] = []
    for rec in records:
        answer = rec.get("answer", "")
        as_of = rec.get("as_of_date", "2025-01-01")
        citations = extract(answer)
        cands: Dict[str, str] = {}
        meta: Dict[str, dict] = {}
        for i, c in enumerate(citations):
            auto = candidate_window(answer, c.span) if c.span else ""
            resolved = _resolve_citation(laws, c, as_of)
            gt = (resolved.content or "") if (resolved.found and
                    ground_truth_verified(resolved)) else ""
            key = str(i)
            cands[key] = auto
            meta[key] = {
                "raw": getattr(c, "raw", ""),
                "auto_candidate": auto,
                "ground_truth_head": (gt[:80] + "…") if len(gt) > 80 else gt,
            }
        out.append({
            "model": rec.get("model", "unknown"),
            "as_of_date": as_of,
            "citations": meta,
            "candidates": cands,
        })
    return out


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Generate a gold-candidate annotation skeleton (candidates.jsonl)")
    ap.add_argument("--input", required=True, help="answers.jsonl")
    ap.add_argument("--output", required=True, help="candidates.jsonl to write")
    ap.add_argument("--limit", type=int, default=0,
                    help="process only the first N records (0=all)")
    args = ap.parse_args(argv)

    recs = [json.loads(l) for l in open(args.input, encoding="utf-8") if l.strip()]
    if args.limit:
        recs = recs[:args.limit]
    skel = build_skeleton(recs)
    with open(args.output, "w", encoding="utf-8") as f:
        for s in skel:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    print(f"wrote {len(skel)} model records to {args.output}")
    print("edit the 'candidates' values (or leave = auto_candidate), then run:")
    print(f"  python -m benchmark.run --input {args.input} --candidates {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
