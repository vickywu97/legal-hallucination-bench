#!/usr/bin/env python3
"""Render benchmark/reports/leaderboard.html from leaderboard.json + questions.json.

Stdlib-only, offline. This is the single source of truth for the shareable HTML
leaderboard: the data-driven parts (ranking table, metric facts) are computed from
the benchmark output, so the page can never silently drift from leaderboard.md again.

Editorial parts (model tier labels, the "pitfalls" narrative) live in the two
constants below and are updated per release — they are stable, not data-derived.

Usage:
    python -S scripts/render_leaderboard.py
(after `python -S -m benchmark.run --offline --input answers.jsonl`)
"""
import json
import os
import html

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORTS = os.path.join(REPO_ROOT, "benchmark", "reports")
LEADERBOARD_JSON = os.path.join(REPORTS, "leaderboard.json")
QUESTIONS_JSON = os.path.join(REPO_ROOT, "questions.json")
OUT_HTML = os.path.join(REPORTS, "leaderboard.html")

# Stable editorial metadata: model -> Chinese tier label (shown as a pill).
MODEL_TIERS = {
    "DeepSeek-R1": "付费旗舰",
    "Qwen-Max": "付费",
    "DeepSeek-V3": "免费基础",
    "GLM-4-Flash": "免费",
    "Kimi": "kimi-k2.6",
}

# Stable narrative about the trap design (true across v1.1/v1.2; edit per release).
PITFALLS_HTML = """
<div class="insight">
  <b>面对虚构 / 失效 / 新法序号，模型密集踩坑</b>：Q8（虚构法律"虚拟法"）五模型全部 NOT_FOUND、
  Q4（2024 新《公司法》将对外担保由第16条移至第15条）五模型全部引用旧序号 → NOT_FOUND、
  新增 Q16–Q18（《增值税法》2026-01-01 施行）5 模型 42 次引注 0 次 EXACT，失败以虚构序号为主。
  <br><span style="color:var(--muted);font-size:13px">注：直接引用"已废止法律"的陷阱仅 R1 在 Q7 踩中，其余 4 模型均避开。</span>
</div>
"""


def pct(x):
    return f"{x * 100:.1f}%"


def bar_color(hvi):
    if hvi <= 0.50:
        return "var(--good)"
    if hvi <= 0.58:
        return "var(--warn)"
    return "var(--bad)"


def rank_class(rank, total):
    if rank == 1:
        return "r1"
    if rank == total:
        return "r5"
    return ""


def load():
    with open(LEADERBOARD_JSON, encoding="utf-8") as f:
        rows = json.load(f)
    with open(QUESTIONS_JSON, encoding="utf-8") as f:
        n_questions = len(json.load(f)["questions"])
    return rows, n_questions


def build_table(rows):
    body = []
    total = len(rows)
    for r in rows:
        m = r["metrics"]
        hvi = m["hr_statutory"]
        tier = MODEL_TIERS.get(r["model"], "")
        pill = f' <span class="pill">{html.escape(tier)}</span>' if tier else ""
        cls = rank_class(r["rank"], total)
        body.append(f"""        <tr>
          <td><span class="rank {cls}">{r['rank']}</span></td>
          <td>{html.escape(r['model'])}{pill}</td>
          <td class="hvi-cell">{pct(hvi)}
            <div class="bar"><i style="width:{hvi * 100:.1f}%;background:{bar_color(hvi)}"></i></div></td>
          <td class="num">{r['n_citations']}</td>
        </tr>""")
    return "\n".join(body)


def build_facts(rows):
    # Content-level hallucination: hr_content == 1.0 for all => "全员 100%".
    all_content = all(abs(r["metrics"]["hr_content"] - 1.0) < 1e-9 for r in rows)
    content_txt = "全员内容级幻觉率 100%（零逐字合规）" if all_content else \
        f"内容级幻觉率 {pct(max(r['metrics']['hr_content'] for r in rows))} 起"

    crfi = rows[0]["metrics"]["crfi"]
    crfi_txt = f"张冠李戴率(CRFI) {pct(crfi)}"

    # Temporal (deprecated-law) hallucinations.
    temporal = [(r["model"], r["metrics"]["rate_deprecated"]) for r in rows
                if r["metrics"]["rate_deprecated"] > 0]
    if not temporal:
        temporal_txt = "未触发时序幻觉"
    else:
        parts = "、".join(f"{html.escape(m)} {pct(d)}" for m, d in temporal)
        temporal_txt = f"时序幻觉：{parts}"

    return f"{content_txt} · {crfi_txt} · {temporal_txt}"


def build_free_paid(rows):
    paid, free = [], []
    for r in rows:
        tier = MODEL_TIERS.get(r["model"], "")
        if "付费" in tier:
            paid.append(r)
        elif "免费" in tier:
            free.append(r)
    if not paid or not free:
        return ""
    best_paid = min(paid, key=lambda r: r["metrics"]["hr_statutory"])
    best_free = min(free, key=lambda r: r["metrics"]["hr_statutory"])
    pp = best_paid["metrics"]["hr_statutory"]
    fp = best_free["metrics"]["hr_statutory"]
    if pp <= fp:
        verdict = "付费并不保证更可靠，但旗舰仍居首"
    else:
        verdict = "免费模型未输付费"
    return f"""    <div class="insight">
      <b>付费 vs 免费：{html.escape(verdict)}</b>：最佳付费模型 {html.escape(best_paid['model'])}（{pct(pp)}）
      对比最佳免费模型 {html.escape(best_free['model'])}（{pct(fp)}）——"贵即好"与"免费即差"均不成立。
    </div>"""


def build_best_worst(rows):
    best = min(rows, key=lambda r: r["metrics"]["hr_statutory"])
    worst = max(rows, key=lambda r: r["metrics"]["hr_statutory"])
    return f"""    <div class="insight">
      <b>榜首与末位</b>：{html.escape(best['model'])}（{pct(best['metrics']['hr_statutory'])}，{best['n_citations']} 次引注）表现最佳；
      {html.escape(worst['model'])}（{pct(worst['metrics']['hr_statutory'])}，{worst['n_citations']} 次引注）引注最积极却幻觉率最高——"引得越多错得越多"稳定成立。
    </div>"""


CSS = """  <style>
  :root{
    --bg:#0f172a; --card:#1e293b; --ink:#e2e8f0; --muted:#94a3b8;
    --accent:#38bdf8; --good:#34d399; --warn:#fbbf24; --bad:#f87171;
  }
  *{box-sizing:border-box}
  body{
    margin:0; background:linear-gradient(160deg,#0b1220,#0f172a 60%);
    color:var(--ink); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",
    "PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
    padding:40px 20px; display:flex; justify-content:center;
  }
  .wrap{width:100%; max-width:760px}
  header h1{font-size:26px; margin:0 0 6px}
  header p{color:var(--muted); margin:0 0 4px; font-size:14px}
  .tag{display:inline-block; background:rgba(56,189,248,.12); color:var(--accent);
    border:1px solid rgba(56,189,248,.3); border-radius:999px; padding:3px 10px;
    font-size:12px; margin-top:8px}
  .card{background:var(--card); border:1px solid rgba(148,163,184,.15);
    border-radius:16px; padding:22px; margin-top:20px; box-shadow:0 10px 40px rgba(0,0,0,.35)}
  table{width:100%; border-collapse:collapse; font-size:15px}
  th,td{padding:12px 10px; text-align:left; border-bottom:1px solid rgba(148,163,184,.12)}
  th{color:var(--muted); font-weight:600; font-size:13px; text-transform:uppercase; letter-spacing:.04em}
  td.num{text-align:right; font-variant-numeric:tabular-nums; font-weight:700}
  .rank{display:inline-flex; align-items:center; justify-content:center;
    width:26px; height:26px; border-radius:8px; font-weight:700; font-size:13px;
    background:rgba(148,163,184,.15)}
  .r1{background:rgba(52,211,153,.18); color:var(--good)}
  .r5{background:rgba(248,113,113,.18); color:var(--bad)}
  .bar{height:8px; border-radius:6px; background:rgba(148,163,184,.18); overflow:hidden; margin-top:6px}
  .bar > i{display:block; height:100%; border-radius:6px}
  .hvi-cell{min-width:120px}
  .pill{font-size:12px; padding:2px 8px; border-radius:999px; background:rgba(148,163,184,.15); color:var(--muted)}
  h2{font-size:16px; margin:0 0 12px}
  .insight{border-left:3px solid var(--accent); padding:10px 14px; margin:12px 0;
    background:rgba(56,189,248,.06); border-radius:0 10px 10px 0}
  .insight b{color:#fff}
  footer{margin-top:18px; font-size:13px; color:var(--muted); text-align:center}
  footer a{color:var(--accent); text-decoration:none}
  footer a:hover{text-decoration:underline}
  </style>"""


def main():
    rows, n_questions = load()
    n_models = len(rows)
    n_records = n_questions * n_models  # every model answers every question

    table = build_table(rows)
    facts = build_facts(rows)
    free_paid = build_free_paid(rows)
    best_worst = build_best_worst(rows)

    doc = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8" />
<meta name="viewport" content="width=device-width, initial-scale=1" />
<title>Legal-Hallucination-Bench · 真实模型引注幻觉排行榜</title>
{CSS}</head>
<body>
<div class="wrap">
  <header>
    <h1>法律 AI 引注幻觉排行榜</h1>
    <p>Legal-Hallucination-Bench · {n_questions} 题 × {n_models} 国产模型 = {n_records} 条真实回答</p>
    <p>引注幻觉率（HVI，越低越好）：只查"引用的法条是否存在 / 是否废止"，不要求逐字</p>
    <span class="tag">离线评分 · 零依赖 · 可复现</span>
  </header>

  <div class="card">
    <h2>排行榜（按 HVI 升序）</h2>
    <table>
      <thead>
        <tr><th>#</th><th>模型</th><th class="hvi-cell">引注幻觉率 HVI</th><th class="num">引注数</th></tr>
      </thead>
      <tbody>
{table}
      </tbody>
    </table>
  </div>

  <div class="card">
    <h2>核心洞察</h2>
{best_worst}
{free_paid}
{PITFALLS_HTML}
    <p style="color:var(--muted);font-size:13px;margin:14px 0 0">{facts}</p>
  </div>

  <footer>
    数据与方法论详见 GitHub 仓库：
    <a href="https://github.com/vickywu97/legal-hallucination-bench" target="_blank" rel="noopener">
      github.com/vickywu97/legal-hallucination-bench
    </a>
  </footer>
</div>
</body>
</html>
"""
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(doc)
    print(f"[render] wrote {OUT_HTML}")
    print(f"[render] {n_questions} 题 × {n_models} 模型 = {n_records} 条;"
          f" 榜首 {rows[0]['model']} {pct(rows[0]['metrics']['hr_statutory'])}")


if __name__ == "__main__":
    main()
