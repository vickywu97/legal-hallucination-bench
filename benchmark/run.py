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
    """Built-in demo set: 4 questions x 3 toy models (good / bad / partial).

    Each record carries ``question_id`` so the offline demo also exercises the
    per-question diagnosis matrix. Covers all key verdicts out of the box and
    showcases the HVI metric distinctly from content failures:
    Q1 verbatim EXACT (good) / extra-gloss FABRICATED (bad) / truncated
    FABRICATED (partial); Q3 relocation NOT_FOUND; Q4 deprecated-alias
    TEMPORAL_DEPRECATED; Q10 MISATTRIBUTED.
    """
    laws = load_laws()
    rev_x = laws["刑法"].revisions[list(laws["刑法"].revisions)[-1]]
    gt232, gt234 = rev_x.articles["232"].content, rev_x.articles["234"].content
    rev_c = laws["民法典"].revisions[list(laws["民法典"].revisions)[-1]]
    gt584 = rev_c.articles["584"].content
    rev_co = laws["公司法"].revisions[list(laws["公司法"].revisions)[-1]]
    gt10 = rev_co.articles["10"].content  # current-company-law correct article
    gt15 = rev_co.articles["15"].content  # current-company-law art.15 (guarantee)

    grid = []
    # Q1 — 民法典 第584条 (verbatim benchmark)
    grid.append({"model": "Model-A-good", "question_id": "Q1",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《民法典》第584条，" + gt584})
    grid.append({"model": "Model-B-bad", "question_id": "Q1",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《民法典》第584条，" + gt584
                           + "（另据相关司法解释补充如下……）"})  # 编造后缀 -> FABRICATED
    grid.append({"model": "Model-C-partial", "question_id": "Q1",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《民法典》第584条，"
                           + "；".join(gt584.split("；")[:-1])})  # 截断 -> FABRICATED
    # Q3 — 公司法 法定代表人 (correct=第10条; 旧第13条已 relocation -> NOT_FOUND)
    grid.append({"model": "Model-A-good", "question_id": "Q3",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《公司法》第10条，" + gt10})
    grid.append({"model": "Model-B-bad", "question_id": "Q3",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《公司法》第13条，法定代表人由董事会选举产生。"})  # NOT_FOUND
    grid.append({"model": "Model-C-partial", "question_id": "Q3",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《公司法》第13条，法定代表人由公司章程规定。"})  # NOT_FOUND
    # Q4 — 公司对外担保 (correct=第15条; 旧公司法第16条=失效别名 -> TEMPORAL_DEPRECATED)
    grid.append({"model": "Model-A-good", "question_id": "Q4",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《公司法》第15条，" + gt15})
    grid.append({"model": "Model-B-bad", "question_id": "Q4",
                 "as_of_date": "2025-01-01",
                 "answer": "根据旧公司法第16条，公司为股东提供担保须经股东会决议。"})  # TEMPORAL
    grid.append({"model": "Model-C-partial", "question_id": "Q4",
                 "as_of_date": "2025-01-01",
                 "answer": "依据旧公司法第16条，公司对外担保由董事会或股东会决议。"})  # TEMPORAL
    # Q10 — 刑法 第232条 (good=EXACT; bad=张冠李戴 填234文本; partial=截断)
    grid.append({"model": "Model-A-good", "question_id": "Q10",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《刑法》第232条，" + gt232})
    grid.append({"model": "Model-B-bad", "question_id": "Q10",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《刑法》第232条，" + gt234})  # 张冠李戴 -> MISATTRIBUTED
    grid.append({"model": "Model-C-partial", "question_id": "Q10",
                 "as_of_date": "2025-01-01",
                 "answer": "根据《刑法》第232条，"
                           + "；".join(gt232.split("；")[:-1])})  # 截断 -> FABRICATED
    return grid


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
