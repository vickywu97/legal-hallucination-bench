"""CLI entry point for Legal-Hallucination-Bench.

Week 1 ships a temporal-resolution demo (old Company Law art.13 -> new art.10
after 2024-07-01). Week 4 ships the content-diff verification demo
(extract -> verify_citation, binary (verbatim-or-zero) content-diff + temporal/provenance gates).
Week 5 ships the end-to-end offline pipeline (extract -> verify -> score ->
audit report + leaderboard) via --offline.
"""
import argparse
import json
import os
import sys
from knowledge_base.loader import load_laws, resolve_article


def _demo():
    laws = load_laws()
    cases = [
        ("民法典", "584", "2025-01-01"),
        ("公司法", "13", "2020-01-01"),   # old law in force -> old text
        ("公司法", "13", "2025-01-01"),   # relocated -> not in this revision
        ("公司法", "10", "2025-01-01"),   # new law -> new text
        ("刑法", "232", "2025-01-01"),
    ]
    print("=== Temporal-resolution demo ===")
    for name, no, d in cases:
        r = resolve_article(laws, name, no, d)
        snippet = (r.content or "")[:24].replace("\n", " ")
        print(f"  {name} 第{no}条 @ {d}: found={r.found} "
              f"rev={r.revision_id} note={r.note!r} :: {snippet}")


def _verify_demo():
    """Week 4: extraction -> content-diff verification, end-to-end demo."""
    from benchmark.extract import extract, Citation
    from benchmark.verify import verify_citation

    laws = load_laws()
    as_of = "2025-01-01"
    print(f"=== Week-4 verify demo (as_of={as_of}) ===")

    # 1) extraction feeds verification (citation-level)
    passage = ("根据《刑法》第232条，故意杀人的处死刑、无期徒刑或者十年以上有期徒刑。"
               "另，依据旧公司法第3条，公司是企业法人。")
    print("\n[extract -> verify] from a sample model passage:")
    for c in extract(passage):
        v = verify_citation(c, as_of, laws)
        print(f"  {c.raw!r:14s} -> {v.verdict}/{v.category}")

    # 2) three-level content diff (ground truth pulled from the verified KB)
    rev = laws["刑法"].revisions[list(laws["刑法"].revisions)[-1]]
    gt232, gt234 = rev.articles["232"].content, rev.articles["234"].content
    c232 = Citation(cit_type="law", raw="刑法第232条", law_code="CRIMINAL_LAW",
                    law_name="刑法", article_no="232")
    print("\n[content-diff] three levels for 刑法第232条:")
    samples = [
        ("EXACT", gt232),
        # non-exact: extra gloss appended -> now HALLUCINATION (PARTIAL), not OK
        ("PARTIAL", gt232 + "（含作为与不作为）"),
        ("MISATTRIBUTED", gt234),  # 张冠李戴: 232 cited, 234 text rendered
    ]
    for label, cand in samples:
        v = verify_citation(c232, as_of, laws, candidate_text=cand)
        print(f"  {label:12s} -> {v.diff_level}/{v.category} score={v.score}")


def _pipeline_demo(input_path: str = None, candidates_path: str = None):
    """Week 5/6: full offline pipeline -> audit report + leaderboard.

    With --input <answers.jsonl> uses the user's model answers; otherwise runs
    a built-in SAMPLE (good model vs bad model) to produce the first report.
    With --candidates <candidates.jsonl> (from benchmark.annotate) the gold
    candidate texts are merged in for STRICT content-level evaluation.
    """
    from benchmark.pipeline import audit, build_report

    out_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           "reports")
    if input_path:
        records = [json.loads(l) for l in open(input_path, encoding="utf-8")
                   if l.strip()]
        print(f"[pipeline] loaded {len(records)} model-answer records from {input_path}")
    else:
        records = _SAMPLE_RECORDS()
        print(f"[pipeline] no --input given; running built-in SAMPLE "
              f"({len(records)} model-answer records)")

    if candidates_path:
        file_cands: dict = {}
        for line in open(candidates_path, encoding="utf-8"):
            line = line.strip()
            if not line:
                continue
            obj = json.loads(line)
            file_cands[obj["model"]] = obj.get("candidates", {})
        for rec in records:
            m = rec.get("model", "unknown")
            if m in file_cands:
                merged = dict(file_cands[m])
                merged.update(rec.get("candidates", {}))  # rec overrides file
                rec["candidates"] = merged
        print(f"[pipeline] merged gold candidates from {candidates_path} "
              f"({len(file_cands)} model(s))")

    result = audit(records)
    build_report(result, out_dir)

    print(f"[pipeline] wrote reports to {out_dir}")
    print("\n=== Leaderboard (by HR_statutory, lower=better) ===")
    for model, d in sorted(result.items(),
                           key=lambda kv: kv[1]["report"].metrics.get("hr_statutory", 1.0)):
        m = d["report"].metrics
        print(f"  {model:18s} HR={m.get('hr_statutory', 0):.1%} "
              f"content={m.get('hr_content', 0):.1%} "
              f"deprecated={m.get('rate_deprecated', 0):.1%} "
              f"unverif={m.get('rate_unverifiable', 0):.1%} "
              f"n={d['n_citations']}")


def _SAMPLE_RECORDS():
    """Three toy model answers: careful / hallucinating / partially-omitting.

    Covers all key content-diff categories (EXACT via A; MISATTRIBUTED +
    TEMPORAL_DEPRECATED + NOT_FOUND via B; PARTIAL via C) so the built-in
    --offline demo exercises the full engine out of the box.
    """
    laws = load_laws()
    rev = laws["刑法"].revisions[list(laws["刑法"].revisions)[-1]]
    gt232 = rev.articles["232"].content
    gt234 = rev.articles["234"].content
    rev_c = laws["民法典"].revisions[list(laws["民法典"].revisions)[-1]]
    gt584 = rev_c.articles["584"].content

    good = (
        "关于故意杀人，根据《刑法》第232条，" + gt232 +
        "\n根据《民法典》第584条，" + gt584
    )
    bad = (
        "关于故意杀人，根据《刑法》第232条，" + gt234 +  # 张冠李戴：232 条号却填 234 文本
        "\n《旧公司法》第3条规定公司是企业法人。" +        # 时序幻觉
        "\n《公司法》第13条，法定代表人由董事会选举产生。"   # NOT_FOUND（已 relocation）
    )
    # PARTIAL: cites 232 correctly but drops the trailing "情节较轻" clause
    partial = "；".join(gt232.split("；")[:-1])
    partial_ans = "关于故意杀人，根据《刑法》第232条，" + partial
    return [
        {"model": "Model-A-good", "as_of_date": "2025-01-01", "answer": good},
        {"model": "Model-B-bad", "as_of_date": "2025-01-01", "answer": bad},
        {"model": "Model-C-partial", "as_of_date": "2025-01-01", "answer": partial_ans},
    ]


def main(argv=None):
    ap = argparse.ArgumentParser(
        prog="legal-hallucination-bench",
        description="Chinese legal citation hallucination benchmark.")
    ap.add_argument("--demo", action="store_true",
                    help="run the Week-1 temporal-resolution demo")
    ap.add_argument("--offline", action="store_true",
                    help="run the Week-5 offline pipeline (extract+verify+score)")
    ap.add_argument("--verify-demo", action="store_true",
                    help="run the Week-4 content-diff engine demo")
    ap.add_argument("--input", default=None,
                    help="path to answers.jsonl for --offline (else built-in SAMPLE)")
    ap.add_argument("--candidates", default=None,
                    help="path to candidates.jsonl (from benchmark.annotate) "
                         "for strict content-level evaluation")
    args = ap.parse_args(argv)

    if args.demo:
        _demo()
        return 0
    if args.verify_demo:
        _verify_demo()
        return 0
    if args.offline:
        _pipeline_demo(args.input, args.candidates)
        return 0
    ap.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
