# -*- coding: utf-8 -*-
"""Render the instruction-following leaderboard as a standalone HTML file.

Offline, zero-dependency. Produces a single self-contained .html (inline CSS,
no external assets) so it can be opened locally or hosted anywhere.

The HTML always carries a banner that states whether the numbers are a DEMO
(dummy baselines, not a real ranking) or REAL (from provided model answers),
plus a materials-disclaimer footer — per the project's IP / accuracy guardrails.
"""
from __future__ import annotations

import html as _html
import os

_DEMO_BANNER = (
    "⚠️ DEMO 脚手架：本排行榜分数来自随机 / 空哑巴基线，<b>不是真实模型排名</b>。"
    "接入真实模型请使用 models.generate_answers 后再以 run.py --score-answers 生成。"
)
_REAL_BANNER = (
    "✅ 真实排行榜：基于提供的模型答案生成，给定相同的 answers 文件可完全复现。"
)

_DISCLAIMER = (
    "本页面为项目 C（企业封闭指令遵循评测基准）的演示产物。任务样例、公司名、发票、"
    "合同均为虚构示例数据，不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / "
    "专业意见。公开发布为真实基准前，须经作者（税务师 / 律师）逐题核验并标注法规版本轴。"
)


def _esc(value) -> str:
    return _html.escape(str(value))


def _row_cells(r: dict, hidden_count: int = 0) -> str:
    hidden_cell = ""
    if hidden_count > 0:
        if "hidden_total" in r:
            hidden_cell = f"<td>{r['hidden_total']:.3f}</td>"
        else:
            hidden_cell = "<td>—</td>"
    return (
        f"<td>{_esc(r['model'])}</td>"
        f"<td>{_esc(r['tasks'])}</td>"
        f"<td>{r['avg_format']:.3f}</td>"
        f"<td>{r['avg_content']:.3f}</td>"
        f"<td>{r['avg_closure']:.3f}</td>"
        f"<td><b>{r['avg_total']:.3f}</b></td>"
        f"<td>{r['instruction_violation_rate']:.3f}</td>"
        f"{hidden_cell}"
    )


def _bar(violation_rate: float) -> str:
    pct = max(0.0, min(100.0, violation_rate * 100))
    # violation rate is a RISK metric: low (good) = green, high (bad) = red
    if violation_rate <= 0.33:
        color = "#2e7d32"
    elif violation_rate <= 0.66:
        color = "#f9a825"
    else:
        color = "#c62828"
    return (
        f'<div class="bar-wrap"><div class="bar" style="width:{pct:.1f}%;'
        f'background:{color}">{pct:.1f}%</div></div>'
    )


def build_html(rows: list, mode: str = "demo", hidden_count: int = 0) -> str:
    banner = _DEMO_BANNER if mode == "demo" else _REAL_BANNER
    hidden_th = '<th>隐藏集综合(防刷分)</th>' if hidden_count > 0 else ""
    body_rows = "\n".join(
        f"<tr>{_row_cells(r, hidden_count)}<td>{_bar(r['instruction_violation_rate'])}</td></tr>"
        for r in rows
    )
    hidden_note = ""
    if hidden_count > 0:
        hidden_note = (
            f'<div class="banner hidden">⛨ 防刷分：本排行榜含 {hidden_count} 道'
            "隐藏题（题目不公开、不随仓库发布），仅用于验证模型是否针对公开题过拟合。"
            "隐藏题的逐题内容不会出现在任何对外页面，此处仅展示各模型的隐藏集综合得分。</div>"
        )
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>企业封闭指令遵循评测基准 · 指令违背率排行榜</title>
<style>
  body {{ font-family: -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif; margin: 2rem; color: #222; }}
  h1 {{ font-size: 1.4rem; }}
  .banner {{ padding: .75rem 1rem; border-radius: 8px; margin: 1rem 0; font-size: .92rem; line-height: 1.5; }}
  .banner.demo {{ background: #fff3e0; border: 1px solid #ffb74d; color: #e65100; }}
  .banner.real {{ background: #e8f5e9; border: 1px solid #81c784; color: #1b5e20; }}
  .banner.hidden {{ background: #ede7f6; border: 1px solid #9575cd; color: #4527a0; }}
  table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; font-size: .9rem; }}
  th, td {{ border: 1px solid #ddd; padding: .5rem .6rem; text-align: center; }}
  th {{ background: #f5f5f5; }}
  td:first-child {{ text-align: left; font-weight: 600; }}
  .bar-wrap {{ background: #eee; border-radius: 4px; min-width: 130px; }}
  .bar {{ color: #fff; font-size: .8rem; padding: 2px 4px; border-radius: 4px; text-align: right; white-space: nowrap; }}
  .disclaimer {{ margin-top: 1.5rem; font-size: .8rem; color: #777; border-top: 1px solid #eee; padding-top: .8rem; line-height: 1.5; }}
</style>
</head>
<body>
<h1>企业封闭指令遵循评测基准 · 指令违背率排行榜</h1>
<div class="banner {mode}">{banner}</div>
{hidden_note}
<table>
  <thead><tr>
    <th>模型</th><th>题数</th><th>格式(30%)</th><th>内容(40%)</th><th>封闭性(30%)</th>
    <th>综合</th><th>指令违背率</th>
    {hidden_th}
  </tr></thead>
  <tbody>
{body_rows}
  </tbody>
</table>
<div class="disclaimer">{_DISCLAIMER}</div>
</body>
</html>"""


def write_html(rows: list, mode: str, csv_path: str, hidden_count: int = 0) -> str:
    out_path = os.path.splitext(csv_path)[0] + ".html"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(build_html(rows, mode, hidden_count=hidden_count))
    return out_path
