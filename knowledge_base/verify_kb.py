"""Human verification workflow for the statute knowledge base.

This tool walks a legal expert through every ``unverified`` node emitted by
``build_statute.generate()`` and records a verdict in ``verifications.json`` —
the human signature ledger. It is the ONLY thing that can flip a node to
``verified``; the LLM-authored SEED scaffold can never self-verify.

Why a separate tool + ledger
----------------------------
The benchmark's whole credibility rests on its ground truth being
expert-checked. The ledger is kept *outside* the LLM-authored SEED so that
``build_statute build`` can regenerate ``statutes.jsonl`` at any time without
ever losing a human verdict. Every decision is written to disk immediately, so
an interrupted session is fully resumable.

Commands
--------
    python -S -m knowledge_base.verify_kb report            # progress + writes report
    python -S -m knowledge_base.verify_kb pending           # list unverified ids
    python -S -m knowledge_base.verify_kb show <id>         # show one node
    python -S -m knowledge_base.verify_kb open <id>         # open source_url in browser
    python -S -m knowledge_base.verify_kb verify <id> --accept [--correct "..."] [--by NAME]
    python -S -m knowledge_base.verify_kb verify <id> --reject [--correct "..."] [--by NAME]
    python -S -m knowledge_base.verify_kb review            # interactive loop

All commands accept ``--ledger PATH`` to use a non-default ledger file.
"""
from __future__ import annotations

import os
import sys
import json
import argparse
import subprocess
import datetime
from typing import Dict, List, Optional

from knowledge_base.build_statute import (
    generate,
    _load_verifications,
    VERIFICATIONS_FILE,
    INDEX_FILE,
)

DEFAULT_VERIFIER = "Vicky Wu (律师/税务师/专利代理师)"
# Historical verification reports live in archive/ (see git history for the
# original). The tool regenerates a fresh report there, keeping knowledge_base/
# free of generated artifacts.
REPORT_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                           os.pardir, "archive", "VERIFICATION_REPORT.md")


# --------------------------------------------------------------------------- #
# Ledger I/O + decision application
# --------------------------------------------------------------------------- #
def load_ledger(path: str = VERIFICATIONS_FILE) -> dict:
    return _load_verifications(path)


def save_ledger(ledger: dict, path: str = VERIFICATIONS_FILE) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=2)
        f.write("\n")


def apply_decision(ledger: dict, node_id: str, status: str,
                   corrected_content: Optional[str] = None,
                   verified_by: str = DEFAULT_VERIFIER,
                   verified_at: Optional[str] = None) -> dict:
    """Record a verdict for ``node_id`` and return the ledger entry.

    status: "verified" | "rejected".
    corrected_content: when the scaffold was wrong but you supply the correct
    text, the node is promoted to scored ground truth ("verified").
    """
    if status not in ("verified", "rejected"):
        raise ValueError(f"status must be 'verified' or 'rejected' (got {status!r})")
    if verified_at is None:
        verified_at = datetime.date.today().isoformat()
    entry = {
        "status": status,
        "verified_by": verified_by,
        "verified_at": verified_at,
        "corrected_content": corrected_content,
        "note": "",
    }
    ledger[node_id] = entry
    return entry


# --------------------------------------------------------------------------- #
# Display helpers
# --------------------------------------------------------------------------- #
def load_law_names() -> Dict[str, str]:
    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            index = json.load(f)
        return {code: meta.get("name", code) for code, meta in index.items()}
    except FileNotFoundError:
        return {}


def print_node(node: dict, law_names: Dict[str, str]) -> None:
    name = law_names.get(node["law_code"], node["law_code"])
    bar = "=" * 72
    print(bar)
    print(f"  {node['id']}")
    print(f"  {name} {node['article_number']}  (生效 {node['effective_date']})")
    print(f"  状态: {node['verification_status']}   来源: {node.get('source_url', '')}")
    print(bar)
    print(node["content"])
    print()


def verification_progress(nodes: List[dict]) -> dict:
    per_law: Dict[str, Dict[str, int]] = {}
    for n in nodes:
        p = per_law.setdefault(n["law_code"],
                               {"verified": 0, "rejected": 0, "unverified": 0})
        p[n["verification_status"]] = p.get(n["verification_status"], 0) + 1
    totals = {"verified": 0, "rejected": 0, "unverified": 0}
    for p in per_law.values():
        for k in totals:
            totals[k] += p.get(k, 0)
    return {"per_law": per_law, "totals": totals}


# --------------------------------------------------------------------------- #
# Commands
# --------------------------------------------------------------------------- #
def cmd_pending(args, nodes):
    pending = [n for n in nodes if n["verification_status"] == "unverified"]
    print(f"{len(pending)} unverified node(s):\n")
    for n in pending:
        snippet = n["content"][:38].replace("\n", " ")
        print(f"  {n['id']:<26} {n['law_code']} {n['article_number']:<6} {snippet}...")
    return 0


def cmd_show(args, nodes):
    by_id = {n["id"]: n for n in nodes}
    n = by_id.get(args.id)
    if n is None:
        print(f"unknown node id: {args.id}", file=sys.stderr)
        return 1
    print_node(n, load_law_names())
    return 0


def cmd_open(args, nodes):
    by_id = {n["id"]: n for n in nodes}
    n = by_id.get(args.id)
    if n is None:
        print(f"unknown node id: {args.id}", file=sys.stderr)
        return 1
    url = n.get("source_url") or ""
    if not url:
        print("no source_url for this node", file=sys.stderr)
        return 1
    print(f"opening {url}")
    if sys.platform == "darwin":
        subprocess.run(["open", url])
    elif sys.platform.startswith("linux"):
        subprocess.run(["xdg-open", url])
    else:
        print(url)  # windows / unknown: just print it
    return 0


def cmd_verify(args, nodes):
    if not (args.accept ^ args.reject):
        print("specify exactly one of --accept / --reject", file=sys.stderr)
        return 1
    status = "verified" if args.accept else "rejected"
    by_id = {n["id"]: n for n in nodes}
    if args.id not in by_id:
        print(f"unknown node id: {args.id}", file=sys.stderr)
        return 1
    ledger = load_ledger(args.ledger)
    entry = apply_decision(ledger, args.id, status,
                           corrected_content=args.correct, verified_by=args.by)
    save_ledger(ledger, args.ledger)
    print(f"recorded {status} for {args.id}"
          + (" (with corrected text)" if args.correct else ""))
    return 0


def cmd_review(args, nodes):
    law_names = load_law_names()
    ledger = load_ledger(args.ledger)
    pending = [n for n in nodes if n["verification_status"] == "unverified"]
    if not pending:
        print("nothing to verify — all nodes have a verdict.")
        return 0
    print(f"== 核验模式：{len(pending)} 条待核验。每条输入指令后回车。 ==")
    print("  a=通过(verified)  r=驳回(rejected)  e=修正文本(verified+correct)  "
          "o=打开来源  s=跳过  q=退出并保存\n")
    idx = 0
    while idx < len(pending):
        n = pending[idx]
        print_node(n, law_names)
        try:
            cmd = input(f"[{idx + 1}/{len(pending)}] 指令> ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n中断：已保存已作出的判定。")
            break
        if cmd == "q":
            print("已退出并保存。")
            break
        elif cmd == "s":
            idx += 1
            continue
        elif cmd == "o":
            url = n.get("source_url")
            if url:
                if sys.platform == "darwin":
                    subprocess.run(["open", url])
                elif sys.platform.startswith("linux"):
                    subprocess.run(["xdg-open", url])
                else:
                    print(url)
            else:
                print("  该节点无 source_url")
            continue
        elif cmd in ("a", "e"):
            corrected = None
            if cmd == "e":
                print("  粘贴正确条文（单行；空行=取消本次修正）:")
                try:
                    corrected = input("  修正文本> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print("\n中断：已保存已作出的判定。")
                    break
                if not corrected:
                    print("  已取消，节点保持 unverified。")
                    idx += 1
                    continue
            apply_decision(ledger, n["id"], "verified",
                           corrected_content=corrected, by=args.by)
            save_ledger(ledger, args.ledger)
            print(f"  ✓ 已记录 verified: {n['id']}"
                  + (" (含修正)" if corrected else ""))
            idx += 1
        elif cmd == "r":
            corrected = None
            print("  若你能提供正确文本（节点将升级为 verified），请粘贴；否则直接回车:")
            try:
                corrected = input("  正确文本(可选)> ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n中断：已保存已作出的判定。")
                break
            apply_decision(ledger, n["id"], "rejected",
                           corrected_content=corrected or None, by=args.by)
            save_ledger(ledger, args.ledger)
            print(f"  ✗ 已记录 rejected: {n['id']}"
                  + (" (已附正确文本→升级为 verified)" if corrected else ""))
            idx += 1
        else:
            print("  未知指令，请输入 a/r/e/o/s/q")
            continue
    # refresh pending count
    prog = verification_progress(generate(ledger=ledger))
    t = prog["totals"]
    print(f"\n进度：{t['verified']} verified / {t['rejected']} rejected / "
          f"{t['unverified']} unverified")
    return 0


def cmd_report(args, nodes):
    prog = verification_progress(nodes)
    law_names = load_law_names()
    t = prog["totals"]
    total = sum(t.values())
    pct = (t["verified"] / total * 100) if total else 0.0
    print(f"{'law_code':<14}{'verified':>9}{'rejected':>9}{'unverified':>11}")
    print("-" * 43)
    for code, p in sorted(prog["per_law"].items()):
        print(f"{code:<14}{p.get('verified',0):>9}{p.get('rejected',0):>9}"
              f"{p.get('unverified',0):>11}")
    print("-" * 43)
    print(f"{'TOTAL':<14}{t['verified']:>9}{t['rejected']:>9}{t['unverified']:>11}")
    print(f"\n已核验覆盖率: {pct:.1f}% ({t['verified']}/{total})")
    _write_report(prog, law_names, total, pct)
    print(f"\n报告已写入: {REPORT_FILE}")
    return 0


def _write_report(prog, law_names, total, pct):
    t = prog["totals"]
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    lines = [
        "# 法条知识库核验进度报告",
        "",
        f"> 生成时间：{now}  ",
        f"> 已核验覆盖率：**{pct:.1f}%** ({t['verified']}/{total})",
        "",
        "## 分法律统计",
        "",
        "| 法律 | verified | rejected | unverified |",
        "| --- | ---: | ---: | ---: |",
    ]
    for code, p in sorted(prog["per_law"].items()):
        name = law_names.get(code, code)
        lines.append(f"| {name} | {p.get('verified',0)} | {p.get('rejected',0)} "
                     f"| {p.get('unverified',0)} |")
    lines += [
        "| **合计** | "
        f"**{t['verified']}** | **{t['rejected']}** | **{t['unverified']}** |",
        "",
        "## 说明",
        "",
        "- `unverified`：LLM 脚手架文本，未经专家核验，**不可用于评分**（见 `verify.py` 硬门）。",
        "- `verified`：经专家比对官方法律法规数据库确认（或已修正），可作评分 ground truth。",
        "- `rejected`：脚手架文本有误且尚未提供正确版本，已被评分门禁排除。",
        "- 本文件由 `python -S -m knowledge_base.verify_kb report` 自动生成。",
        "",
    ]
    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


# --------------------------------------------------------------------------- #
# CLI
# --------------------------------------------------------------------------- #
def main(argv=None):
    ap = argparse.ArgumentParser(description="Human verification workflow for the KB")
    ap.add_argument("--ledger", default=VERIFICATIONS_FILE,
                    help="verification ledger path (default: verifications.json)")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("pending", help="list unverified node ids")
    sub.add_parser("report", help="print + write verification progress report")
    p_show = sub.add_parser("show", help="show one node")
    p_show.add_argument("id")
    p_open = sub.add_parser("open", help="open node source_url in browser")
    p_open.add_argument("id")

    p_verify = sub.add_parser("verify", help="record a verdict for one node")
    p_verify.add_argument("id")
    p_verify.add_argument("--accept", action="store_true", help="mark verified")
    p_verify.add_argument("--reject", action="store_true", help="mark rejected")
    p_verify.add_argument("--correct", default=None,
                          help="corrected text (promotes rejected->verified)")
    p_verify.add_argument("--by", default=DEFAULT_VERIFIER, help="verifier name")

    sub.add_parser("review", help="interactive loop over unverified nodes")

    args = ap.parse_args(argv)

    # Nodes reflect the current ledger (so pending/show/report are consistent).
    nodes = generate(ledger=load_ledger(args.ledger))

    if args.cmd == "pending":
        return cmd_pending(args, nodes)
    if args.cmd == "show":
        return cmd_show(args, nodes)
    if args.cmd == "open":
        return cmd_open(args, nodes)
    if args.cmd == "verify":
        return cmd_verify(args, nodes)
    if args.cmd == "review":
        return cmd_review(args, nodes)
    if args.cmd == "report":
        return cmd_report(args, nodes)
    return 1


if __name__ == "__main__":
    sys.exit(main())
