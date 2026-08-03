"""Knowledge base loader and temporal resolver.

Pure-python (stdlib only). No network, no C extensions, zero third-party
runtime dependencies — runs fully offline in a `python -S` clean environment.

Serialization format (schema locked in SIX_WEEK_PLAN.md):
  * ``laws/laws_index.json``  — law-level metadata, one entry per law_code.
  * ``laws/statutes.jsonl``   — one article-version node per line. A node
    carries ``effective_date`` and an optional ``revision_of`` back-pointer to
    the node it supersedes (relocation / amendment chain).

The loader synthesizes the in-memory ``Law``/``Revision``/``Article`` model
that ``resolve_article`` consumes. Time windows are derived, never stored:
for a node ``n`` with successor ``s`` (``s.revision_of == n.id``),
``window(n) = [n.effective_date, s.effective_date)`` — left-closed,
right-open, gap-free. The latest revision in force at ``as_of_date`` wins.
"""

from __future__ import annotations

import os
import re
import json
import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional

# Repealed-law names are recognized here so resolve_article can flag them as
# temporal hallucinations. The canonical — and now ONLY — source of truth for
# abolished law names is benchmark.extract.DEPRECATED_LAW_NAMES. The KB index
# deliberately carries no deprecated_aliases field, so the knowledge base stays
# 100% current-law and there is a single place to maintain the trap list.
from benchmark.extract import DEPRECATED_LAW_NAMES

KB_ROOT = os.path.dirname(os.path.abspath(__file__))
LAWS_DIR = os.path.join(KB_ROOT, "laws")
INDEX_FILE = os.path.join(LAWS_DIR, "laws_index.json")
STATUTES_FILE = os.path.join(LAWS_DIR, "statutes.jsonl")

# JSON (law index) and JSONL (article nodes) are both strict subsets of YAML
# but unambiguous and dependency-free — critical for a legal KB where a
# mis-parse is unacceptable and the package must run offline.


# --------------------------------------------------------------------------- #
# Data models
# --------------------------------------------------------------------------- #
@dataclass
class Article:
    article_no: str
    article_no_alt: Optional[str]
    chapter: Optional[str]
    section: Optional[str]
    content: str
    effective_from: Optional[str]
    effective_until: Optional[str]
    amended_by: Optional[str]  # "revision_id::article_no"
    # Provenance gate. "verified" means an expert confirmed the text against an
    # official source. "unverified" (default) means the text is scaffold/candidate
    # and MUST NOT be used as ground truth for scoring. An LLM-authored KB is, by
    # definition, "unverified" until a human verifies it.
    verification_status: str = "unverified"


@dataclass
class Revision:
    revision_id: str
    revision_type: str  # 制定|修订|修正|废止
    effective_date: str
    repealed_date: Optional[str]
    decision_url: Optional[str]
    articles: Dict[str, Article]


@dataclass
class Law:
    name: str
    aliases: List[str]
    # NOTE: repealed-law traps are NOT stored here. The single source of truth
    # for abolished law names is benchmark.extract.DEPRECATED_LAW_NAMES
    # (e.g. 旧公司法 / 合同法 / 民法总则 / ...). The loader recognizes those
    # names verbatim and flags a citation as a temporal hallucination without
    # ever keeping the old name inside the KB index (the KB stays 100%
    # current-law). See resolve_article's DEPRECATED_LAW_NAMES branch.
    issuing_authority: str
    jurisdiction: str
    status: str
    promulgation_date: Optional[str]
    effective_date: Optional[str]
    source_url: Optional[str]
    source_accessed_at: Optional[str]
    revisions: Dict[str, Revision]


@dataclass
class ResolveResult:
    found: bool
    content: Optional[str] = None
    law_name: Optional[str] = None
    revision_id: Optional[str] = None
    article_no: Optional[str] = None
    as_of: Optional[str] = None
    note: str = ""
    # Temporal-hallucination signal: the model cited a repealed law NAME in a
    # post-repeal context. Set by resolve_article when the raw law_name is a
    # deprecated alias and as_of_date >= its repealed_date.
    used_deprecated_alias: bool = False
    deprecated_repealed_date: Optional[str] = None
    # Provenance of the resolved text. None when no article matched. When set,
    # verify.py MUST refuse to score a citation against an "unverified" node.
    verification_status: Optional[str] = None


# --------------------------------------------------------------------------- #
# Low-level IO
# --------------------------------------------------------------------------- #
def _load_json(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: str):
    """Read a JSONL file into a list of dicts, skipping blank lines."""
    rows: List[dict] = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    return rows


# --------------------------------------------------------------------------- #
# JSONL -> in-memory model synthesis
# --------------------------------------------------------------------------- #
def _build_law_from_index_and_nodes(meta: dict, nodes: List[dict]) -> Law:
    """Build a ``Law`` (with synthesized ``Revision`` snapshots) from the
    law-level metadata and that law's article-version nodes.

    Temporal synthesis
    ------------------
    For each distinct ``effective_date`` ``d`` among the nodes we synthesize a
    ``Revision``. An article-version node ``n`` is "current" at ``d`` iff:
      * ``n.effective_date <= d``; and
      * its window is still open at ``d`` — i.e. it has no successor, or
        ``d < successor.effective_date`` (left-closed, right-open); and
      * it is the latest version of its ``(law_code, article_sort_key)``
        effective at ``d``.
    This makes a relocation (old art.13 -> new art.10, different sort_key)
    disappear from the new revision automatically, while a same-key amendment
    (old art.3 -> new art.3) is swapped in at the boundary.
    """
    by_id = {n["id"]: n for n in nodes}
    eff_dates = sorted({n["effective_date"] for n in nodes})

    revisions: Dict[str, Revision] = {}
    for idx, d in enumerate(eff_dates):
        rev_id = f"{meta.get('law_code', meta['name'])}@{d}"
        articles: Dict[str, Article] = {}
        for n in nodes:
            sk = n["article_sort_key"]
            if not (n["effective_date"] <= d):
                continue
            # window end = effective_date of the node that supersedes n
            succ_eff = None
            for m in nodes:
                if m.get("revision_of") == n["id"]:
                    succ_eff = m["effective_date"]
                    break
            if succ_eff is not None and not (d < succ_eff):
                continue  # window already closed at d
            # must be the latest version of this sort_key effective at d
            is_latest = True
            for m in nodes:
                if (
                    m["article_sort_key"] == sk
                    and m["effective_date"] <= d
                    and m["effective_date"] > n["effective_date"]
                ):
                    is_latest = False
                    break
            if not is_latest:
                continue
            articles[str(sk)] = Article(
                article_no=str(sk),
                article_no_alt=n.get("article_number"),
                chapter=None,
                section=None,
                content=n["content"],
                effective_from=n["effective_date"],
                effective_until=succ_eff,
                amended_by=None,
                verification_status=n.get("verification_status", "unverified"),
            )
        repealed_date = eff_dates[idx + 1] if idx + 1 < len(eff_dates) else None
        revisions[rev_id] = Revision(
            revision_id=rev_id,
            revision_type="制定" if idx == 0 else "修订",
            effective_date=d,
            repealed_date=repealed_date,
            decision_url=meta.get("source_url"),
            articles=articles,
        )
    return Law(
        name=meta["name"],
        aliases=meta.get("aliases", []),
        issuing_authority=meta.get("issuing_authority", ""),
        jurisdiction=meta.get("jurisdiction", ""),
        status=meta.get("status", ""),
        promulgation_date=meta.get("promulgation_date"),
        effective_date=meta.get("effective_date"),
        source_url=meta.get("source_url"),
        source_accessed_at=meta.get("source_accessed_at"),
        revisions=revisions,
    )


def load_from_jsonl(
    index_path: Optional[str] = None,
    jsonl_path: Optional[str] = None,
) -> Dict[str, Law]:
    """Build the in-memory law model from ``laws_index.json`` + ``statutes.jsonl``.

    Returns a dict keyed by canonical name AND every alias (so resolution by
    alias — including repealed-law names like "合同法"/"旧公司法" — works).
    """
    index_path = index_path or INDEX_FILE
    jsonl_path = jsonl_path or STATUTES_FILE
    index = _load_json(index_path)
    nodes = _load_jsonl(jsonl_path)
    laws: Dict[str, Law] = {}
    for law_code, meta in index.items():
        meta = dict(meta)
        meta["law_code"] = law_code
        law_nodes = [n for n in nodes if n.get("law_code") == law_code]
        law = _build_law_from_index_and_nodes(meta, law_nodes)
        laws[law.name] = law
        # Register by canonical law_code too, so resolve_article's purged
        # repealed-name branch (DEPRECATED_LAW_NAMES -> code) can map back to
        # the surviving law object even when the name itself was purged from
        # the index (e.g. 旧公司法 -> COMPANY_LAW, 合同法 -> CIVIL_CODE).
        laws[meta["law_code"]] = law
        for alias in law.aliases:
            laws[alias] = law
    return laws


def load_laws(kb_root: Optional[str] = None) -> Dict[str, Law]:
    """Load all laws from the default ``laws/`` directory."""
    kb_root = kb_root or KB_ROOT
    laws_dir = os.path.join(kb_root, "laws")
    return load_from_jsonl(
        os.path.join(laws_dir, "laws_index.json"),
        os.path.join(laws_dir, "statutes.jsonl"),
    )


def load_courts(kb_root: Optional[str] = None) -> Dict[str, dict]:
    kb_root = kb_root or KB_ROOT
    path = os.path.join(kb_root, "courts.json")
    data = _load_json(path)
    return {c["code"]: c for c in data.get("courts", [])}


# --------------------------------------------------------------------------- #
# Temporal resolution  (unchanged engine)
# --------------------------------------------------------------------------- #
def _parse_iso_date(s) -> Optional[tuple]:
    """Parse a date-ish value into a comparable ``(Y, M, D)`` tuple, or None.

    Accepts ISO ``YYYY-MM-DD``, common separators (``/`` ``.``), and the Chinese
    ``YYYY年M月D日`` form. ``None``/empty/unparseable -> None so temporal checks
    never crash on messy input.
    """
    if not s:
        return None
    if isinstance(s, datetime.date):
        return (s.year, s.month, s.day)
    t = str(s).strip()
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", t)
    if m:
        return tuple(int(x) for x in m.groups())
    m = re.match(r"^(\d{4})[/.](\d{1,2})[/.](\d{1,2})$", t)
    if m:
        return tuple(int(x) for x in m.groups())
    m = re.match(r"^(\d{4})年(\d{1,2})月(\d{1,2})日$", t)
    if m:
        return tuple(int(x) for x in m.groups())
    return None


def _date_le(a, b) -> bool:
    """Date <= comparison tolerant of None and non-ISO formats."""
    pa, pb = _parse_iso_date(a), _parse_iso_date(b)
    if pa is None or pb is None:
        return True
    return pa <= pb


def _date_ge(a, b) -> bool:
    """Date >= comparison tolerant of None and non-ISO formats.

    A missing/unknown date can never *confirm* an on/after relationship, so
    either side being None yields False.
    """
    pa, pb = _parse_iso_date(a), _parse_iso_date(b)
    if pa is None or pb is None:
        return False
    return pa >= pb


def normalize_as_of(as_of) -> Optional[str]:
    """Normalize ``as_of_date`` to a strict ISO ``YYYY-MM-DD`` string, or None.

    Pipeline entry point: collapses ``None``, empty string, the literals
    ``"null"``/``"none"``, non-ISO separators (``2024/06/01``) and the Chinese
    ``2024年6月1日`` form into a canonical date. Unparseable input falls back to
    None so downstream logic degrades gracefully instead of crashing.
    """
    if as_of is None:
        return None
    if isinstance(as_of, datetime.date):
        return as_of.isoformat()
    s = str(as_of).strip()
    if s == "" or s.lower() in ("null", "none"):
        return None
    parts = _parse_iso_date(s)
    if parts is None:
        return None
    try:
        return datetime.date(*parts).isoformat()
    except ValueError:
        return None


def resolve_article(
    laws: Dict[str, Law], law_name: str, article_no: str, as_of_date: str
) -> ResolveResult:
    """Resolve the article content valid at ``as_of_date``.

    Walks revisions at the requested time, then follows the ``amended_by``
    chain if the matched article expired and was relocated.
    """
    law = laws.get(law_name)
    # Temporal-hallucination trap — single source of truth is
    # benchmark.extract.DEPRECATED_LAW_NAMES. A citation that names a repealed
    # law (e.g. "旧公司法" / "合同法") is mapped to its canonical surviving
    # law_code so article resolution can still run, but is flagged as a
    # temporal hallucination whenever as_of_date is on/after the repeal date.
    used_dep = False
    dep_repealed = None
    if law_name in DEPRECATED_LAW_NAMES:
        _, repealed = DEPRECATED_LAW_NAMES[law_name]
        if _date_le(repealed, as_of_date):
            used_dep = True
            dep_repealed = repealed
        law = laws.get(DEPRECATED_LAW_NAMES[law_name][0])
    if law is None:
        return ResolveResult(
            found=False, law_name=law_name, as_of=as_of_date, note="UNKNOWN_LAW",
            used_deprecated_alias=used_dep, deprecated_repealed_date=dep_repealed,
        )

    # Find the latest revision in force at as_of_date.
    valid_rev: Optional[Revision] = None
    for rev in law.revisions.values():
        if _date_le(rev.effective_date, as_of_date) and (
            rev.repealed_date is None or _date_le(as_of_date, rev.repealed_date)
        ):
            if valid_rev is None or _date_le(valid_rev.effective_date, rev.effective_date):
                valid_rev = rev

    if valid_rev is None:
        return ResolveResult(
            found=False,
            law_name=law.name,
            as_of=as_of_date,
            note="LAW_NOT_IN_FORCE_AT_DATE",
            used_deprecated_alias=used_dep,
            deprecated_repealed_date=dep_repealed,
        )

    art = valid_rev.articles.get(article_no)
    if art is None:
        return ResolveResult(
            found=False,
            law_name=law.name,
            revision_id=valid_rev.revision_id,
            article_no=article_no,
            as_of=as_of_date,
            note="ARTICLE_NOT_IN_THIS_REVISION",
            used_deprecated_alias=used_dep,
            deprecated_repealed_date=dep_repealed,
        )

    # Follow amended_by if the article itself expired and was relocated.
    if art.effective_until and _date_le(art.effective_until, as_of_date) and art.amended_by:
        rid, ano = art.amended_by.split("::")
        target_rev = law.revisions.get(rid)
        if target_rev and ano in target_rev.articles:
            tgt = target_rev.articles[ano]
            return ResolveResult(
                found=True,
                content=tgt.content,
                law_name=law.name,
                revision_id=rid,
                article_no=ano,
                as_of=as_of_date,
                note=f"RELOCATED from {valid_rev.revision_id}::{article_no}",
                used_deprecated_alias=used_dep,
                deprecated_repealed_date=dep_repealed,
                verification_status=tgt.verification_status,
            )

    return ResolveResult(
        found=True,
        content=art.content,
        law_name=law.name,
        revision_id=valid_rev.revision_id,
        article_no=article_no,
        as_of=as_of_date,
        used_deprecated_alias=used_dep,
        deprecated_repealed_date=dep_repealed,
        verification_status=art.verification_status,
    )


def resolve_court(courts: Dict[str, dict], code: str) -> Optional[dict]:
    return courts.get(code)
