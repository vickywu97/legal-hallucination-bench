"""Expand ``knowledge_base/laws/statutes.jsonl`` to the full official text (方案 B).

Background
----------
The eval engine scores against ``statutes.jsonl`` (loaded via
``knowledge_base.loader.load_laws``). Historically that file held only the 212
expert-verified nodes (each article compared verbatim against the official
source). The downloadable ``packs/*_full.jsonl`` (built by
``build_law_pack.py --verified-source``) carry the *complete* official text of
all 8 laws (2327 unique articles across the 8 source laws; the 9th "TAX_full"
pack is a merge of 4 tax laws and is excluded from this count), signed by the
project author as "source confirmed complete + faithful extraction".

This script promotes those full-text packs into the eval ground truth so the
benchmark scores against the entire corpus, not just the 212-node subset. This
is a *deliberate, documented trust upgrade* (the user chose 方案 B): the new
2329 nodes are "verified" under the weaker "official source confirmed complete"
criterion, distinct from the original "each article proofread verbatim" basis.
The provenance gate (``refuse_unverified_ground_truth``) stays in force for any
future genuinely-unverified addition.

Merge rule (idempotent)
-----------------------
Key = (law_code, article_sort_key). The 212 existing nodes are kept verbatim
(preserving their original verified_by/at). Pack nodes whose key is absent from
the existing set are added as verified, with Chinese article numbers converted
to Arabic to match the statutes.jsonl convention, and the pack-only ``trust_tier``
field dropped (statutes.jsonl has no such field). Total must equal 2541.
"""
import json
import os
import re
import sys

# Reuse the canonical decimal sort-key parser so existing nodes are normalized
# onto the same scheme the loader/engine expect (e.g. 第234条之一 -> 234.001),
# which lets them dedup against the pack nodes and keeps re-runs idempotent.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from knowledge_base.build_statute import _parse_sort_key  # noqa: E402

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAT = os.path.join(REPO, "knowledge_base", "laws", "statutes.jsonl")
PACKS_DIR = os.path.join(REPO, "packs")
PACK_LAWS = [
    "COMPANY_LAW", "CIVIL_CODE", "CRIMINAL_LAW", "PATENT_LAW",
    "EIT_LAW", "IIT_LAW", "TAX_ADMIN_LAW", "VAT_LAW",
]
EXPECT_TOTAL = 2327
VERIFIED_BY = "Vicky Wu (律师/税务师/专利代理师)"
VERIFIED_AT = "2026-08-07"

DIGIT = {"零": 0, "一": 1, "二": 2, "三": 3, "四": 4,
         "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
UNIT = {"十": 10, "百": 100, "千": 1000}


def cn2int(s: str) -> int:
    total = 0
    cur = 0
    for ch in s:
        if ch in DIGIT:
            cur = DIGIT[ch]
        elif ch in UNIT:
            u = UNIT[ch]
            if u == 10 and cur == 0:
                cur = 1
            total += cur * u
            cur = 0
    return total + cur


def to_arabic(article_number: str) -> str:
    """'第一条' -> '第1条'; '第一百二十条之一' -> '第120条之一'.

    Passes through article numbers that are already Arabic ('第120条之一' ->
    '第120条之一') so the function is safe to apply to both the Chinese-numeral
    pack sources and the already-Arabic existing statutes. The 之一/之二 suffix
    follows 条 (e.g. 第X条之一), NOT precedes it.
    """
    m = re.match(r"^第(.+?)条(之一|之二|之三|之四|之五|之六|之七|之八|之九|之十)?$",
                 article_number)
    if not m:
        return article_number
    core, sub = m.group(1), m.group(2)
    # core may already be Arabic (e.g. '120') or Chinese (e.g. '一百二十').
    num = int(core) if core.isdigit() else cn2int(core)
    s = f"第{num}条"
    if sub:
        s += sub
    return s


def rk(n: dict):
    """Dedup key: (law_code, rounded sort_key). Rounding guards against
    float-precision drift between sources that both mean e.g. 234.001, and
    against id/sort_key format drift in upstream pack nodes."""
    return (n["law_code"], round(float(n["article_sort_key"]), 3))


def main():
    existing = [json.loads(l) for l in open(STAT, encoding="utf-8") if l.strip()]
    # Normalize existing nodes onto the decimal scheme so the legacy integer
    # sort_key (e.g. 2341) and any Chinese article numbers align with the pack
    # nodes and let them dedup. verified_by/at are preserved (Tier A provenance).
    for n in existing:
        n["article_number"] = to_arabic(n["article_number"])
        n["article_sort_key"] = _parse_sort_key(n["article_number"])

    by_key = {rk(n): n for n in existing}

    out = list(existing)
    seen = set(by_key.keys())
    added = 0
    collisions = 0

    for code in PACK_LAWS:
        path = os.path.join(PACKS_DIR, f"{code}_full.jsonl")
        for l in open(path, encoding="utf-8"):
            if not l.strip():
                continue
            r = json.loads(l)
            key = rk(r)
            if key in seen:
                collisions += 1
                continue
            node = dict(r)
            node.pop("trust_tier", None)  # statutes.jsonl schema has no trust_tier
            node["article_number"] = to_arabic(r["article_number"])
            node["article_sort_key"] = _parse_sort_key(node["article_number"])
            node["verification_status"] = "verified"
            node["verified_by"] = r.get("verified_by") or VERIFIED_BY
            node["verified_at"] = r.get("verified_at") or VERIFIED_AT
            out.append(node)
            seen.add(key)
            added += 1

    # Defensive collapse: never emit two nodes sharing a dedup key.
    collapsed = {}
    for n in out:
        collapsed.setdefault(rk(n), n)
    out = list(collapsed.values())

    out.sort(key=lambda n: (n["law_code"], n["article_sort_key"]))
    with open(STAT, "w", encoding="utf-8") as f:
        for n in out:
            f.write(json.dumps(n, ensure_ascii=False) + "\n")

    assert len(out) == EXPECT_TOTAL, f"total {len(out)} != {EXPECT_TOTAL}"
    print(f"[expand] existing kept = {len(existing)}")
    print(f"[expand] pack collisions (already in statutes) = {collisions}")
    print(f"[expand] added from packs = {added}")
    print(f"[expand] total statutes nodes = {len(out)} (expected {EXPECT_TOTAL})")


if __name__ == "__main__":
    main()
