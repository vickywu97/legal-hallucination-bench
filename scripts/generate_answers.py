#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate model answers for the Legal-Hallucination-Bench real-model leaderboard.

Zero runtime dependencies (Python stdlib only: urllib, json, os, sys, time).
Calls 5 domestic (China-based) LLM providers over REST, pins temperature=0 for
reproducibility, and writes ``answers.jsonl`` in the exact format the offline
pipeline consumes::

    {"question_id": "Q1", "model": "DeepSeek-V3",
     "as_of_date": "2025-01-01", "answer": "..."}

Design guardrail
----------------
A strict system prompt restricts every model to the 6 in-scope laws
(民法典 / 刑法 / 专利法 / 税收征收管理法 / 公司法 2023 / 增值税法 2026). This converts any
out-of-scope or fictional citation into a clean instruction violation +
hard hallucination (NOT_FOUND) — so the leaderboard conclusion is defensible.

API keys are read from the environment (never hardcoded):
    DEEPSEEK_API_KEY, ZHIPU_API_KEY, DASHSCOPE_API_KEY, MOONSHOT_API_KEY
A model with no key is skipped (with a warning) rather than failing the run.

Usage
-----
    python scripts/generate_answers.py                 # all models, all questions
    python scripts/generate_answers.py --models DeepSeek-V3 GLM-4-Flash
    python scripts/generate_answers.py --questions questions.json --out answers.jsonl
    python scripts/generate_answers.py --only Q1 Q7 Q13
    python scripts/generate_answers.py --resume        # merge into existing out (skip done pairs)
    python scripts/generate_answers.py --models Kimi --resume   # add one model safely

Note: before overwriting --out, the existing file is copied to a timestamped
.backup (answers.jsonl.bak.YYYYMMDD-HHMMSS) so a re-run never silently destroys
prior data. Use --resume to incrementally add a model without re-calling others.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

# --- repo layout: this file lives in <repo>/scripts/ ------------------------- #
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
QUESTIONS_DEFAULT = os.path.join(REPO_ROOT, "questions.json")
OUT_DEFAULT = os.path.join(REPO_ROOT, "answers.jsonl")

# Honesty + 6-law-scope guardrail (shared by every provider).
SYSTEM_PROMPT = (
    "你是一位严谨的中国法律检索助手。本次评测仅限以下六部现行有效法律："
    "民法典、刑法、专利法、税收征收管理法、公司法（2023年修订，2024-07-01施行）、"
    "增值税法（2024年12月25日通过，2026-01-01施行）。"
    "请仅引用这六部法律中的具体条文，并逐字引用条文原文。"
    "若问题无法由这六部法律回答，请明确说明“依据所给六部法律无法回答”，"
    "切勿引用其他法律、已废止法律或虚构法律。"
    "回答请简洁：先给出引注（如《民法典》第X条），再给出条文原文，最后简要说明适用。"
)

# Provider registry. All providers are OpenAI-compatible chat/completions JSON.
MODELS = [
    {"label": "DeepSeek-V3", "key": "DEEPSEEK_API_KEY", "kind": "openai",
     "url": "https://api.deepseek.com/chat/completions", "model": "deepseek-chat"},
    {"label": "DeepSeek-R1", "key": "DEEPSEEK_API_KEY", "kind": "openai",
     "url": "https://api.deepseek.com/chat/completions", "model": "deepseek-reasoner"},
    {"label": "GLM-4-Flash", "key": "ZHIPU_API_KEY", "kind": "openai",
     "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "model": "glm-4-flash"},
    {"label": "Qwen-Max", "key": "DASHSCOPE_API_KEY", "kind": "openai",
     "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions",
     "model": "qwen-max"},
    {"label": "Kimi", "key": "MOONSHOT_API_KEY", "kind": "openai",
     "url": "https://api.moonshot.cn/v1/chat/completions", "model": "kimi-k2.6",
     # Moonshot's kimi-k2.6 endpoint rejects optional params (temperature/stream)
     # with HTTP 400. Send the minimal payload (model + messages) up front — proven
     # working via curl — instead of burning a 400 + retry on every call.
     "minimal": True},
]

HTTP_TIMEOUT = 180  # seconds; reasoning models (e.g. Kimi k2.6) can take >60s
                     # to return a full non-streamed completion on long prompts.
MAX_RETRIES = 2
RETRY_BACKOFF = 2.0  # seconds


def _post(url: str, headers: dict, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            # Surface the provider's response body — it carries the real reason
            # (e.g. Kimi's 400 "invalid parameter" detail). Without it a 400 is a
            # black box; with it the run is debuggable from the logs alone.
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            last_err = f"HTTP {e.code}: {e.reason} | body={body[:600]}"
            if e.code < 500:  # 4xx: do not blindly retry the same payload
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = str(e)
        if attempt < MAX_RETRIES:
            time.sleep(RETRY_BACKOFF * (attempt + 1))
    raise RuntimeError(f"request failed after {MAX_RETRIES + 1} attempts: {last_err}")


def _call_openai(cfg: dict, api_key: str, user_prompt: str) -> str:
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]
    payload = {
        "model": cfg["model"],
        "messages": messages,
    }
    # Schema-strict endpoints (e.g. Kimi / kimi-k2.6) reject optional params like
    # temperature/stream with HTTP 400. For those providers (cfg["minimal"]) we
    # send the stripped payload up front so the call succeeds on the first try.
    if not cfg.get("minimal"):
        payload["temperature"] = 0
        payload["stream"] = False
    try:
        obj = _post(cfg["url"], headers, payload)
    except RuntimeError as e:
        # Last-resort self-heal: if a non-minimal call still 400s, retry once with
        # the stripped payload. The captured body propagates if even that fails.
        if (not cfg.get("minimal")) and "HTTP 400" in str(e):
            obj = _post(cfg["url"], headers,
                        {"model": cfg["model"], "messages": messages})
        else:
            raise
    return obj["choices"][0]["message"]["content"].strip()


def call_model(cfg: dict, user_prompt: str) -> str:
    api_key = os.environ.get(cfg["key"], "").strip()
    if not api_key:
        raise RuntimeError(f"missing env var {cfg['key']}")
    if cfg["kind"] != "openai":
        raise RuntimeError(f"unsupported provider kind: {cfg['kind']}")
    return _call_openai(cfg, api_key, user_prompt)


def _merge_resume(records, out_path):
    """Merge new records into an existing out_path, keeping any prior answer
    that was successful (non-empty, no _error). Returns the merged list.

    Used by --resume so a later single-model run (e.g. adding Kimi) cannot
    clobber answers already collected for other models.
    """
    existing = {}
    for l in open(out_path, encoding="utf-8"):
        l = l.strip()
        if not l:
            continue
        try:
            r = json.loads(l)
        except json.JSONDecodeError:
            continue
        existing[(r.get("model"), r.get("question_id"))] = r
    added = 0
    for r in records:
        key = (r.get("model"), r.get("question_id"))
        prev = existing.get(key)
        if prev and prev.get("answer") and not prev.get("_error"):
            continue  # already have a good answer; skip
        existing[key] = r
        added += 1
    print(f"[resume] kept {len(existing) - added} prior, added/refreshed {added}")
    return list(existing.values())


def main(argv=None):
    ap = argparse.ArgumentParser(description="Generate model answers for the "
                                             "legal-hallucination-bench leaderboard.")
    ap.add_argument("--questions", default=QUESTIONS_DEFAULT,
                    help="path to questions.json")
    ap.add_argument("--out", default=OUT_DEFAULT,
                    help="output answers.jsonl path")
    ap.add_argument("--models", nargs="*", default=None,
                    help="subset of model labels to run (default: all)")
    ap.add_argument("--only", nargs="*", default=None,
                    help="subset of question ids to run (default: all)")
    ap.add_argument("--resume", action="store_true",
                    help="merge with existing --out file, skipping (model,question) "
                         "pairs already answered successfully. Prevents clobbering "
                         "prior runs when adding a single model later.")
    args = ap.parse_args(argv)

    with open(args.questions, encoding="utf-8") as f:
        spec = json.load(f)
    questions = spec["questions"]
    as_of_default = spec.get("_meta", {}).get("as_of_date_default", "2025-01-01")

    selected = [m for m in MODELS if (args.models is None or m["label"] in args.models)]
    if args.models:
        missing = set(args.models) - {m["label"] for m in selected}
        if missing:
            print(f"[warn] unknown model label(s) ignored: {sorted(missing)}")
    if not selected:
        print("[error] no models selected / available; aborting.")
        return 2

    qfilter = set(args.only) if args.only else None

    records = []
    for m in selected:
        api_key = os.environ.get(m["key"], "").strip()
        if not api_key:
            print(f"[skip] {m['label']}: missing {m['key']}")
            continue
        print(f"[run ] {m['label']} ({m['model']})")
        for q in questions:
            if qfilter and q["id"] not in qfilter:
                continue
            as_of = q.get("as_of_date", as_of_default)
            rec = {"question_id": q["id"], "model": m["label"],
                   "as_of_date": as_of, "_domain": q.get("domain", "")}
            try:
                ans = call_model(m, q["prompt"])
                rec["answer"] = ans
            except Exception as e:  # never abort the whole run on one failure
                print(f"    [fail] {m['label']} {q['id']}: {e}")
                rec["answer"] = ""
                rec["_error"] = str(e)
            records.append(rec)
            # tiny politeness delay between calls
            time.sleep(0.3)

    out_path = args.out
    os.makedirs(os.path.dirname(os.path.abspath(out_path)), exist_ok=True)

    if args.resume and os.path.exists(out_path):
        # Merge with prior answers: keep a previously successful answer, only
        # refresh pairs that failed or were not present. Safe for incremental
        # single-model runs (e.g. adding Kimi later without re-calling others).
        records = _merge_resume(records, out_path)
    else:
        # Safety net: never silently destroy a prior run. Back up the existing
        # file (timestamped) before overwriting.
        if os.path.exists(out_path):
            import shutil, datetime
            ts = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
            bak = f"{out_path}.bak.{ts}"
            shutil.copy2(out_path, bak)
            print(f"[backup] existing {out_path} -> {bak}")

    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")

    n_models = len({r["model"] for r in records})
    n_err = sum(1 for r in records if "_error" in r)
    print(f"\n[done] wrote {len(records)} records "
          f"({n_models} model(s)) -> {out_path}"
          f"{f'  ({n_err} failed)' if n_err else ''}")
    print(f"[next] python -m benchmark.run --offline --input {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
