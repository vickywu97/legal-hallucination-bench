"""Citation extractor (Week 3) — the "throat" of the evaluation pipeline.

Extracts legal citations from a model's free-text answer:
  - statutory articles : 《民法典》第584条 / 第五百八十四条 / 合同法第X条 (deprecated trap)
  - judicial interp.   : 法释〔2020〕17号
  - guiding cases      : 指导案例第18号
  - case numbers       : (2021)最高法民终123号
  - suspected          : law-name + 条/款/项 with no clean 第X条 match (heuristic, for audit)

Design (reinforced #2 — proactive correction):
- **offline default path = regex + normalization + suspicion heuristic**, zero
  runtime dependencies, fully reproducible. Covers ~70–80% of standard citations.
- Chinese numerals are normalized: 第五百八十四条 -> 584, 第一百一十三条 -> 113.
- Law-name aliases (incl. *deprecated* aliases) are resolved to a canonical
  ``law_code``. Using a deprecated alias (合同法 / 旧公司法 ...) is flagged
  ``deprecated_alias=True`` — this is the temporal-hallucination trap the bench
  exists to catch, and the signal MUST survive normalization.
- **Suspected heuristic (key)**: spans containing 条/款/项 near a law name but
  not matched by the strict regex are emitted with ``suspected=True`` for audit.
  We surface silent under-recall transparently instead of pretending full coverage.
- **LLM fallback is NOT in the offline path.** A ``--live`` hook may call an LLM
  later, but it never breaks the zero-dependency default.

Output citation dict (per SIX_WEEK_PLAN):
  {type, law_code, article_number, article_sort_key, original_text, position, suspected?}
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Chinese numeral conversion (accumulator form — the classic 五百八十四->512
# off-by-error is avoided by treating 十/百/千 as "num * unit" addends).
# ---------------------------------------------------------------------------
_DIGITS = {'零': 0, '一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
           '六': 6, '七': 7, '八': 8, '九': 9}
_UNITS = {'十': 10, '百': 100, '千': 1000}


def cn2int(s: str) -> int:
    """Convert a Chinese (or Arabic) article number to int. Returns -1 on failure."""
    s = s.strip()
    if s.isdigit():
        return int(s)
    sect, num = 0, 0
    for ch in s:
        if ch in _DIGITS:
            num = _DIGITS[ch]
        elif ch in _UNITS:
            u = _UNITS[ch]
            num = num or 1
            sect += num * u
            num = 0
        else:
            return -1
    return sect + num


# ---------------------------------------------------------------------------
# Citation record
# ---------------------------------------------------------------------------
@dataclass
class Citation:
    cit_type: str                 # law | interpretation | guiding_case | case_no | suspected
    raw: str                      # original matched text
    law_code: str = ""            # resolved canonical code ("" if unknown)
    law_name: str = ""            # matched law name (may be "")
    article_no: str = ""          # "584" or "584-586"
    article_sort_key: int = 0     # primary numeric key for sorting / matching
    doc_no: str = ""              # judicial interpretation doc number
    case_no: str = ""             # guiding case / case number
    span: tuple = (0, 0)          # (start, end) char offsets in source
    suspected: bool = False       # heuristic-only, not strict-regex matched
    deprecated_alias: bool = False  # matched a repealed law name (trap signal)


# ---------------------------------------------------------------------------
# Deprecated / repealed law names that are NO LONGER in laws_index.json.
#
# These names are intentionally absent from the KB index (the knowledge base
# is 100% current-law), but the extractor must still recognize them verbatim
# so a citation like "旧公司法第3条" is NOT silently swallowed by the substring
# match on "公司法" (which would wrongly score it against the 2024 text). We tag
# such citations deprecated_alias=True so the verification engine can mark them
# TEMPORAL_DEPRECATED (hallucination) instead of letting them leak through as OK.
#
# Mapping: deprecated_name -> (canonical law_code, repeal_date).
# Add future purged-law names here (e.g. a renamed statute) as needed.
# ---------------------------------------------------------------------------
DEPRECATED_LAW_NAMES = {
    # Purged repealed-law names. They are kept OUT of laws_index.json so the KB
    # stays 100% current-law; the trap lives here at code level instead. Each
    # entry maps a repealed law name -> (surviving canonical law_code, repeal
    # date). Citing any of these post-repeal is flagged TEMPORAL_DEPRECATED and
    # is never scored against current-law text.
    #
    # Company Law family (repealed by the 2023-amended Company Law, eff. 2024-07-01):
    "旧公司法": ("COMPANY_LAW", "2024-07-01"),
    # Civil Code predecessors (all repealed when the Civil Code took effect on
    # 2021-01-01; their substance was absorbed into the Civil Code's编制/编):
    "合同法": ("CIVIL_CODE", "2021-01-01"),
    "民法总则": ("CIVIL_CODE", "2021-01-01"),
    "侵权责任法": ("CIVIL_CODE", "2021-01-01"),
    "物权法": ("CIVIL_CODE", "2021-01-01"),
    "担保法": ("CIVIL_CODE", "2021-01-01"),
    "婚姻法": ("CIVIL_CODE", "2021-01-01"),
    "继承法": ("CIVIL_CODE", "2021-01-01"),
    "收养法": ("CIVIL_CODE", "2021-01-01"),
    "民法通则": ("CIVIL_CODE", "2021-01-01"),
}


def _lookup_name(ln: str, law_map: dict) -> tuple:
    """Return (law_code, deprecated) for a matched law name.

    Consults both the live KB ``law_map`` and ``DEPRECATED_LAW_NAMES`` so a
    repealed name resolves to its canonical law family (for reporting) while
    staying flagged as deprecated (so it can never be scored as current law).
    """
    if ln in DEPRECATED_LAW_NAMES:
        return DEPRECATED_LAW_NAMES[ln][0], True
    return law_map.get(ln, ("", False))


# ---------------------------------------------------------------------------
# Law-name -> law_code index (loaded from the KB; zero runtime deps)
# ---------------------------------------------------------------------------
_LAWS_INDEX_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "knowledge_base", "laws", "laws_index.json")

_INDEX_CACHE: Optional[dict] = None


def _load_index() -> dict:
    global _INDEX_CACHE
    if _INDEX_CACHE is None:
        with open(_LAWS_INDEX_PATH, encoding="utf-8") as f:
            _INDEX_CACHE = json.load(f)
    return _INDEX_CACHE


def build_law_map(index: Optional[dict] = None) -> dict:
    """Return {name: (law_code, deprecated?)} for all CURRENT-LAW names/aliases.

    Repealed-law names are intentionally NOT included here — they are trapped
    at code level by benchmark.extract.DEPRECATED_LAW_NAMES and consulted
    directly by ``_lookup_name`` / ``_name_pattern``, so the index stays 100%
    current-law and there is a single source of truth for the trap list.
    """
    idx = index if index is not None else _load_index()
    out = {}
    for code, meta in idx.items():
        names = [meta.get("name", "")] + list(meta.get("aliases", []))
        for nm in names:
            if nm:
                out[nm] = (code, False)
    return out


# ---------------------------------------------------------------------------
# Regexes
# ---------------------------------------------------------------------------
_NUM = r'[一二三四五六七八九十百千零两0-9]+'
# law-name alternation (longest first to avoid partial matches)
_NAME_RE = None  # built lazily from the law map


def _name_pattern(law_map: dict) -> str:
    # Include both live KB names and (purged) deprecated names so a repealed
    # name matches verbatim and is never swallowed by a substring of a live name
    # (e.g. "旧公司法" must not degrade to "公司法").
    names = set(law_map.keys()) | set(DEPRECATED_LAW_NAMES.keys())
    names = sorted(names, key=len, reverse=True)
    # escape, allow optional 《 》 around the name
    esc = [re.escape(n) for n in names]
    return r'(?:《)?(?P<ln>' + '|'.join(esc) + r')(?:》)?'


_LAW_RE = None
_INTERP_RE = re.compile(r'法释〔?(\d{4})〕?\s*(\d+)\s*号')
_GUIDING_RE = re.compile(r'指导?性?案例\s*第?\s*(\d+)\s*号')
_CASE_RE = re.compile(r'\((\d{4})\)([^()]{2,20}?)(?:民|刑|行|赔|执|再|终|初)\w*?\d+号')
_SUSPECT_TOKEN = re.compile(r'[条款项]')


def _law_regex(law_map: dict) -> re.Pattern:
    global _LAW_RE
    if _LAW_RE is None:
        pat = (
            r'(?:' + _name_pattern(law_map) + r'\s*)?'          # optional law name
            r'第\s*(' + _NUM + r')\s*条'                         # 第X条
            r'(?:\s*[至\-—~]\s*第?\s*(' + _NUM + r')\s*条)?'    # optional -第Y条 range
        )
        _LAW_RE = re.compile(pat)
    return _LAW_RE


# ---------------------------------------------------------------------------
# Core extraction
# ---------------------------------------------------------------------------
def _merge_spans(spans: List[tuple]) -> List[tuple]:
    spans = sorted(spans)
    out = []
    for s, e in spans:
        if out and s <= out[-1][1]:
            out[-1] = (out[-1][0], max(out[-1][1], e))
        else:
            out.append((s, e))
    return out


def extract(text: str, law_map: Optional[dict] = None) -> List[Citation]:
    """Extract all citations from ``text`` (offline, deterministic)."""
    if law_map is None:
        law_map = build_law_map()
    out: List[Citation] = []
    covered: List[tuple] = []

    def add(c: Citation):
        out.append(c)
        covered.append(c.span)

    # 1) case numbers
    for m in _CASE_RE.finditer(text):
        add(Citation(cit_type="case_no", raw=m.group(0),
                     case_no=m.group(0).strip(), span=m.span()))

    # 2) judicial interpretations
    for m in _INTERP_RE.finditer(text):
        doc = f"法释〔{m.group(1)}〕{m.group(2)}号"
        add(Citation(cit_type="interpretation", raw=m.group(0),
                     doc_no=doc, span=m.span()))

    # 3) guiding cases
    for m in _GUIDING_RE.finditer(text):
        add(Citation(cit_type="guiding_case", raw=m.group(0),
                     case_no=f"指导案例第{m.group(1)}号", span=m.span()))

    # 4) statutory articles
    covered_mer = _merge_spans(covered)
    for m in _law_regex(law_map).finditer(text):
        s, e = m.span()
        # skip if this whole span is already covered by a higher-priority match
        if any(cs <= s and e <= ce for cs, ce in covered_mer):
            continue
        ln = m.group("ln")
        a = cn2int(m.group(2))
        b = cn2int(m.group(3)) if m.group(3) else None
        article_no = str(a) if b is None else f"{a}-{b}"
        sort_key = a if a > 0 else 0
        code, deprecated = _lookup_name(ln, law_map) if ln else ("", False)
        add(Citation(
            cit_type="law", raw=m.group(0).strip(),
            law_code=code, law_name=ln or "", article_no=article_no,
            article_sort_key=sort_key, span=(s, e),
            deprecated_alias=deprecated))
        covered_mer = _merge_spans(covered)

    # 5) suspected heuristic — law name near 条/款/项 but not strictly matched
    suspect_names = set(law_map.keys()) | set(DEPRECATED_LAW_NAMES.keys())
    name_alts = '|'.join(re.escape(n) for n in sorted(suspect_names, key=len, reverse=True))
    for m in re.finditer(r'(?:《)?(' + name_alts + r')(?:》)?', text):
        s, e = m.span()
        if any(cs <= s and e <= ce for cs, ce in _merge_spans(covered)):
            continue
        window = text[max(0, s - 30): min(len(text), e + 30)]
        if _SUSPECT_TOKEN.search(window):
            code, deprecated = _lookup_name(m.group(1), law_map)
            add(Citation(cit_type="suspected", raw=m.group(0).strip(),
                         law_code=code, law_name=m.group(1), span=(s, e),
                         suspected=True, deprecated_alias=deprecated))

    # stable order by position
    out.sort(key=lambda c: c.span[0])
    return out


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _main():
    import argparse
    import sys
    ap = argparse.ArgumentParser(description="Extract legal citations (offline).")
    ap.add_argument("--text", help="text to extract from")
    ap.add_argument("--file", help="read text from file")
    ap.add_argument("--json", action="store_true", help="emit JSON")
    args = ap.parse_args()
    if args.file:
        text = open(args.file, encoding="utf-8").read()
    elif args.text:
        text = args.text
    else:
        text = sys.stdin.read()
    cites = extract(text)
    if args.json:
        print(json.dumps([c.__dict__ for c in cites], ensure_ascii=False, indent=2))
    else:
        for c in cites:
            print(f"[{c.cit_type}] {c.raw!r} code={c.law_code} "
                  f"art={c.article_no} dep={c.deprecated_alias} susp={c.suspected}")


if __name__ == "__main__":
    _main()
