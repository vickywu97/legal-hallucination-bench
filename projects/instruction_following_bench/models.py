# -*- coding: utf-8 -*-
"""Model adapter for the instruction-following benchmark.

Reuses the proven zero-dependency, OpenAI-compatible REST pattern from
``scripts/generate_answers.py`` (Python stdlib ``urllib`` only). API keys are
read from the environment, or from a local ``.env`` file via
``load_dotenv_local`` (stdlib-only, no python-dotenv); an explicit shell
``export`` always wins over the file. A model with no key is skipped rather
than failing the whole run.

IMPORTANT
---------
* This module performs REAL network calls when API keys are present.
* The offline demo (``run.py --offline``) does NOT import or call this module.
* Answers written here are real model outputs; score them with
  ``run.py --score-answers answers_ifb.jsonl`` to produce a REAL leaderboard.
  Never present scores from dummy baselines as a real model ranking.
"""
from __future__ import annotations

import argparse
import json
import os
import time
import urllib.error
import urllib.request

from .run import load_tasks


def load_dotenv_local(path: str | None = None) -> dict:
    """Minimal stdlib-only ``.env`` loader (no third-party dependency).

    Reads ``KEY=value`` lines from a local ``.env`` file and injects them into
    ``os.environ``. Existing environment variables are NOT overridden, so an
    explicit ``export`` in the shell always wins over the file.

    Returns the dict of variables that were actually added (for logging).
    """
    if path is None:
        path = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".env")
    if not os.path.exists(path):
        return {}
    added = {}
    with open(path, encoding="utf-8") as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if "=" not in line:
                continue
            key, _, val = line.partition("=")
            key, val = key.strip(), val.strip()
            if len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
                val = val[1:-1]
            if key and key not in os.environ:
                os.environ[key] = val
                added[key] = val
    return added


# Provider registry — OpenAI-compatible chat/completions JSON.
MODELS = [
    {"label": "DeepSeek-V3", "key": "DEEPSEEK_API_KEY",
     "url": "https://api.deepseek.com/chat/completions", "model": "deepseek-chat"},
    {"label": "GLM-4-Flash", "key": "ZHIPU_API_KEY",
     "url": "https://open.bigmodel.cn/api/paas/v4/chat/completions", "model": "glm-4-flash"},
    {"label": "Qwen-Max", "key": "DASHSCOPE_API_KEY",
     "url": "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions", "model": "qwen-max"},
    {"label": "Kimi", "key": "MOONSHOT_API_KEY",
     "url": "https://api.moonshot.cn/v1/chat/completions", "model": "kimi-k2.6"},
]

SYSTEM_PROMPT = (
    "你是一名严谨的指令遵循助手。用户会给出一条带强格式约束的指令，"
    "你必须严格按指令要求的格式与封闭性输出，不得添加任何额外解释、寒暄或理由，"
    "除非指令本身要求输出理由字段。"
)

HTTP_TIMEOUT = 180
MAX_RETRIES = 2


def _post(url: str, headers: dict, payload: dict) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    last_err = None
    for _ in range(MAX_RETRIES + 1):
        try:
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = ""
            try:
                body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            last_err = f"HTTP {e.code}: {e.reason} | body={body[:600]}"
            if e.code < 500:
                break
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last_err = str(e)
        time.sleep(1.0)
    raise RuntimeError(f"request failed after {MAX_RETRIES + 1} attempts: {last_err}")


def call_model(cfg: dict, user_prompt: str) -> str:
    api_key = os.environ.get(cfg["key"], "").strip()
    if not api_key:
        raise RuntimeError(f"missing env var {cfg['key']}")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": cfg["model"],
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": 0,
    }
    obj = _post(cfg["url"], headers, payload)
    return obj["choices"][0]["message"]["content"].strip()


def build_prompt(task: dict) -> str:
    instr = task.get("instruction", "")
    inp = task.get("input", "")
    return f"{instr}\n{inp}" if inp else instr


def generate_answers(tasks: list, models=None, out_path: str = "answers_ifb.jsonl") -> list:
    """Call real models (requires API keys in env) and write answers jsonl.

    Output record format (compatible with ``run.py --score-answers``)::
        {"task_id": "T1", "model": "DeepSeek-V3", "answer": "..."}
    """
    selected = [m for m in MODELS if (models is None or m["label"] in models)]
    records = []
    for m in selected:
        if not os.environ.get(m["key"], "").strip():
            print(f"[skip] {m['label']}: no {m['key']}")
            continue
        print(f"[run ] {m['label']}")
        for t in tasks:
            rec = {"task_id": t["id"], "model": m["label"]}
            try:
                rec["answer"] = call_model(m, build_prompt(t))
            except Exception as e:  # never abort the whole run on one failure
                rec["answer"] = ""
                rec["_error"] = str(e)
                print(f"    [fail] {m['label']} {t['id']}: {e}")
            records.append(rec)
            time.sleep(0.3)
    with open(out_path, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"[done] {len(records)} records -> {out_path}")
    return records


def main(argv=None):
    """CLI: generate real model answers.

    Requires API keys in the environment (see ``MODELS`` for the exact env-var
    names). A model with no key is skipped, so you can run with only some keys
    set. Output is a jsonl compatible with ``run.py --score-answers``.
    """
    ap = argparse.ArgumentParser(
        description="Generate real model answers for the instruction-following bench")
    ap.add_argument("--out", default="answers_ifb.jsonl",
                    help="output jsonl path (default: answers_ifb.jsonl)")
    ap.add_argument("--tasks", default=None,
                    help="tasks json path (default: bundled config/tasks.json)")
    ap.add_argument("--models", nargs="*", default=None,
                    help="subset of model labels, e.g. DeepSeek-V3 GLM-4-Flash "
                         "(default: all models whose API key env var is set)")
    args = ap.parse_args(argv)

    loaded = load_dotenv_local()
    if loaded:
        print(f"[env ] loaded {len(loaded)} key(s) from local .env")

    tasks_path = args.tasks or os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "config", "tasks.json")
    tasks = load_tasks(tasks_path)
    generate_answers(tasks, models=args.models or None, out_path=args.out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
