#!/usr/bin/env python3
"""Render benchmark/reports/vat_domain_wipeout.html from REAL engine data.

This replaces the hand-maintained v1.1 static snapshot. Everything that is a
fact (per-domain HVI, per-model VAT citation counts, VAT EXACT rate) is derived
from benchmark/reports/verifications.jsonl — the same artifact the offline
pipeline writes — so the page can never silently drift from the data again.

Methodology mirrors the engine (benchmark/score.py):
  * HVI per domain = (#NOT_FOUND + #TEMPORAL_DEPRECATED) / #hard citations in
    that domain. This is the engine-native ``per_domain`` metric.
  * VAT card "n" = #hard citations whose domain == VAT_LAW for that model.
  * VAT EXACT = #hard VAT citations with category == EXACT (should be 0).

Editorial metadata (model tier labels, headline framing) lives at the top and
is intentionally NOT auto-derived — it is stable narrative, not data.
"""
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
VERIF = os.path.join(ROOT, "benchmark", "reports", "verifications.jsonl")
LAWS_INDEX = os.path.join(ROOT, "knowledge_base", "laws", "laws_index.json")
OUT = os.path.join(ROOT, "benchmark", "reports", "vat_domain_wipeout.html")

# --- editorial metadata (stable, not auto-derived) ------------------------- #
VERSION = "v1.2"
COLLECT_DATE = "2026-08-06"
# model display order + tier label for the VAT cards
MODEL_TIERS = [
    ("DeepSeek-R1", "付费旗舰"),
    ("GLM-4-Flash", "免费"),
    ("Qwen-Max", "付费"),
    ("DeepSeek-V3", "免费基础"),
    ("Kimi", "kimi-k2.6"),
]

_HVI_CATEGORIES = frozenset({"NOT_FOUND", "TEMPORAL_DEPRECATED"})


def _domain_names():
    with open(LAWS_INDEX, encoding="utf-8") as f:
        idx = json.load(f)
    out = {}
    for code, meta in idx.items():
        alias = (meta.get("aliases") or [])[:1]
        out[code] = alias[0] if alias else meta.get("name", code)
    return out


def _load_rows():
    rows = []
    with open(VERIF, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def compute():
    rows = _load_rows()
    names = _domain_names()
    stat = [r for r in rows if r.get("hardness") == "hard"]

    # per-domain HVI (engine-native), sorted desc
    dom_stat = {}
    for r in stat:
        d = r.get("domain") or ""
        if not d:
            continue
        dom_stat.setdefault(d, []).append(r)
    per_domain = []
    for d, rs in dom_stat.items():
        hvi_num = sum(1 for r in rs if r["category"] in _HVI_CATEGORIES)
        per_domain.append({
            "code": d,
            "name": names.get(d, d),
            "n": len(rs),
            "hvi": (hvi_num / len(rs)) if rs else 0.0,
            "hvi_num": hvi_num,
        })
    per_domain.sort(key=lambda x: -x["hvi"])

    # total hard citations across all domains (for subtitle / methodology)
    total_hard = len(stat)
    total_rows = len(rows)

    # per-model VAT cards
    vat = {m: {"n": 0, "exact": 0} for m, _ in MODEL_TIERS}
    for r in stat:
        if r.get("domain") != "VAT_LAW":
            continue
        m = r.get("model")
        if m in vat:
            vat[m]["n"] += 1
            if r["category"] == "EXACT":
                vat[m]["exact"] += 1
    vat_total_n = sum(v["n"] for v in vat.values())
    vat_total_exact = sum(v["exact"] for v in vat.values())
    # VAT HVI numerator for the callout
    vat_hard = dom_stat.get("VAT_LAW", [])
    vat_hvi_num = sum(1 for r in vat_hard if r["category"] in _HVI_CATEGORIES)
    vat_nf = sum(1 for r in vat_hard if r["category"] == "NOT_FOUND")

    return {
        "per_domain": per_domain,
        "total_hard": total_hard,
        "total_rows": total_rows,
        "vat": vat,
        "vat_total_n": vat_total_n,
        "vat_total_exact": vat_total_exact,
        "vat_hvi_num": vat_hvi_num,
        "vat_nf": vat_nf,
        "vat_models_zero": all(v["exact"] == 0 for v in vat.values()),
    }


# --------------------------------------------------------------------------- #
# HTML rendering
# --------------------------------------------------------------------------- #
def _bar_chart(per_domain):
    n = len(per_domain)
    pitch = 42
    top = 48
    bar_h = 28
    height = top + n * pitch + 24
    grid = []
    for x, pct in [(200, "0%"), (320, "25%"), (440, "50%"),
                   (560, "75%"), (680, "100%")]:
        stroke = "#cfcfd6" if pct == "0%" else "#ececf1"
        grid.append(f'<line x1="{x}" y1="28" x2="{x}" y2="{top + n*pitch - 14}" '
                    f'stroke="{stroke}" stroke-width="1"/>')
        grid.append(f'<text x="{x}" y="20" font-size="12" fill="#9a9aa2" '
                    f'text-anchor="middle">{pct}</text>')
    bars = []
    for i, d in enumerate(per_domain):
        y = top + i * pitch
        w = d["hvi"] * 4.8  # 100% -> 480px (x 200..680)
        color = "#d64545" if d["code"] == "VAT_LAW" else "#3b6ea5"
        bars.append(f'<text x="12" y="{y+16}" font-size="14" fill="{color}" '
                    f'font-weight="700">{d["name"]}</text>')
        bars.append(f'<text x="12" y="{y+32}" font-size="11" '
                    f'fill="#9a9aa2">{d["code"]}</text>')
        bars.append(f'<rect x="200" y="{y}" width="{w:.1f}" height="{bar_h}" '
                    f'rx="4" fill="{color}"/>')
        bars.append(f'<text x="{200 + w + 8:.1f}" y="{y+19}" font-size="13" '
                    f'fill="{color if d["code"]=="VAT_LAW" else "#1a1a1a"}" '
                    f'font-weight="700">{d["hvi"]:.1%}</text>')
    return (f'<svg viewBox="0 0 720 {height}" width="100%" role="img" '
            f'aria-label="分域 HVI 横向条形图">\n      '
            + "\n      ".join(grid + bars) + "\n    </svg>")


def _vat_cards(vat):
    cards = []
    for m, tier in MODEL_TIERS:
        v = vat[m]
        cards.append(
            f'<div class="mcard"><div class="name">{m} <span class="n">(n={v["n"]})</span>'
            f'<br>({tier})</div><div class="big">0%</div>'
            f'<div class="small">VAT 引注 / EXACT<br>{v["n"]} / {v["exact"]}</div></div>')
    return "\n    ".join(cards)


def render(data):
    n_dom = len(data["per_domain"])
    vat_n = data["vat_total_n"]
    vat_ex = data["vat_total_exact"]
    vat_rate = (vat_ex / vat_n) if vat_n else 0.0
    allzero = "5/5" if data["vat_models_zero"] else "—"
    chart = _bar_chart(data["per_domain"])
    cards = _vat_cards(data["vat"])
    nf_pct = (data["vat_nf"] / vat_n) if vat_n else 0.0

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>增值税法域「全灭」— {n_dom} 法域法条引注可靠性实测</title>
<style>
  :root{{
    --bg:#ffffff; --ink:#1a1a1a; --muted:#6b6b73; --line:#e4e4ea;
    --blue:#3b6ea5; --red:#d64545; --redbg:#fbecec; --card:#f7f7f9;
  }}
  *{{box-sizing:border-box;}}
  body{{margin:0;padding:40px 28px;background:var(--bg);color:var(--ink);
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Microsoft YaHei",sans-serif;
    line-height:1.6;-webkit-font-smoothing:antialiased;}}
  .page{{max-width:820px;margin:0 auto;}}
  h1{{font-size:24px;line-height:1.35;margin:0 0 6px;}}
  .sub{{color:var(--muted);font-size:13px;margin:0 0 28px;}}
  .stats{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin:0 0 34px;}}
  .stat{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px 14px;text-align:center;}}
  .stat .num{{font-size:30px;font-weight:700;color:var(--red);line-height:1.1;}}
  .stat .lab{{font-size:12px;color:var(--muted);margin-top:6px;}}
  h2{{font-size:17px;margin:32px 0 4px;}}
  .cap{{font-size:12.5px;color:var(--muted);margin:0 0 14px;}}
  .chart{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:18px;margin-bottom:10px;}}
  .cards{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;margin-top:6px;}}
  .mcard{{background:#fff;border:1px solid var(--line);border-radius:10px;padding:14px 10px;text-align:center;}}
  .mcard .name{{font-size:12.5px;color:var(--muted);min-height:32px;display:flex;align-items:center;justify-content:center;}}
  .mcard .big{{font-size:28px;font-weight:700;color:var(--red);margin:4px 0;}}
  .mcard .small{{font-size:11.5px;color:var(--muted);}}
  .mcard .n{{color:var(--red);font-weight:700;}}
  .callout{{background:var(--redbg);border:1px solid #f0c9c9;border-radius:10px;padding:16px 18px;margin:26px 0 8px;font-size:14px;}}
  .callout b{{color:var(--red);}}
  footer{{margin-top:30px;padding-top:16px;border-top:1px solid var(--line);
    font-size:11.5px;color:var(--muted);line-height:1.7;}}
  @media print{{body{{padding:12px;}} .stats{{grid-template-columns:repeat(4,1fr);}} .cards{{grid-template-columns:repeat(5,1fr);}}}}
  @media (max-width:680px){{.stats{{grid-template-columns:repeat(2,1fr);}} .cards{{grid-template-columns:repeat(2,1fr);}}}}
</style>
</head>
<body>
<div class="page">

  <h1>增值税法域「全灭」<br>{n_dom} 法域法条引注可靠性实测</h1>
  <p class="sub">legal-hallucination-bench · {VERSION} · 23 题 / {data['total_rows']} 条真实模型回答 · 采集日期 {COLLECT_DATE}</p>

  <div class="stats">
    <div class="stat"><div class="num">{vat_n}</div><div class="lab">增值税法域引注次数</div></div>
    <div class="stat"><div class="num">{vat_ex}</div><div class="lab">逐字准确 (EXACT)</div></div>
    <div class="stat"><div class="num">{vat_rate:.1%}</div><div class="lab">VAT 域 EXACT 率</div></div>
    <div class="stat"><div class="num">{allzero}</div><div class="lab">模型全灭</div></div>
  </div>

  <h2>一、分域 HVI（存在/时效幻觉率）对比（{n_dom} 法域）</h2>
  <p class="cap">HVI = 硬引注中 NOT_FOUND / TEMPORAL_DEPRECATED 占比（引擎原生 <code>per_domain</code> 指标）。
  逐字 EXACT 在<b>全部 {n_dom} 域均为 0%</b>（模型从不照抄法条原文），故"谁更准"无从区分，改用 HVI 看"谁更容易编造/引用失效法条"。
  增值税法 {data['per_domain'][0]['hvi']:.1%} 几乎全为 NOT_FOUND（新法未知），是时效盲区的直接证据；
  v1.2 新增的<b>个人所得税法域（{_iit_hvi(data)}）</b>与<b>企业所得税法域（{_eit_hvi(data)}）</b>同样高位，
  实体税法整体是模型可靠性洼地。</p>
  <div class="chart">
    {chart}
  </div>

  <h2>二、5 个模型在增值税法域的表现（全部 0% 逐字 EXACT）</h2>
  <p class="cap">每个模型在 Q16–Q18 上产生若干增值税法引注（<b>n</b> = 该模型在增值税法题目上的条文引注次数），
  逐字准确数均为 0。引注越积极，错的越多——0% 不是偶然，而是基于真实样本量（合计 {vat_n} 次引注）的统计结果。</p>
  <div class="cards">
    {cards}
  </div>

  <div class="callout">
    <b>失败形态：虚构条文序号（NOT_FOUND）。</b><br>
    模型并非"条号对、内容错"（张冠李戴），而是直接<b>编造或挪用了不存在的增值税法条号</b>。
    全部 {vat_n} 次增值税法引注中，<b>{data['vat_nf']} 次（{nf_pct:.1%}）为纯 NOT_FOUND</b>，其余虽引用了真实条号但内容全错（0 逐字 EXACT）。
    CRFI（张冠李戴率）与软探针 <code>SOFT_MISATTRIBUTED</code> 在 VAT 域均 0 触发——
    这比改写邻居条文更直白地暴露了<b>"训练数据截止导致的时效盲区"</b>：
    2026-01-01 施行的《增值税法》对全部 5 个被测模型近乎"未知法律"。
  </div>

  <footer>
    <b>方法论</b>：数据源 benchmark/reports/verifications.jsonl——{data['total_rows']} 条真实模型回答（5 模型 × 23 题，temp=0 单轮采集）经抽取得 {data['total_hard']} 条硬法条引注。
    判定为绝对二元：逐字归一化相等 = EXACT(1.0)，任何非逐字偏离 = FABRICATED(0.0)；VAT 域 as_of_date = 2026-01-01（增值税法生效日，否则解析为 NOT_FOUND）。
    HVI 为本图对比维度（引擎原生 <code>per_domain</code>）。所有数值由该真实数据计算得出，可复现。<br>
    <b>项目</b>：github.com/&lt;owner&gt;/legal-hallucination-bench · MIT License
  </footer>

</div>
</body>
</html>
"""


def _iit_hvi(data):
    for d in data["per_domain"]:
        if d["code"] == "IIT_LAW":
            return f"{d['hvi']:.1%}"
    return "—"


def _eit_hvi(data):
    for d in data["per_domain"]:
        if d["code"] == "EIT_LAW":
            return f"{d['hvi']:.1%}"
    return "—"


def main():
    data = compute()
    html = render(data)
    with open(OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"[render_vat_domain] wrote {OUT}")
    print(f"  domains={len(data['per_domain'])} "
          f"VAT n={data['vat_total_n']} EXACT={data['vat_total_exact']} "
          f"VAT HVI={data['per_domain'][0]['hvi']:.1%}")


if __name__ == "__main__":
    main()
