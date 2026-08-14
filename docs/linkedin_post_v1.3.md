# LinkedIn 英文帖（v1.3，可直接贴）

> 平台：LinkedIn。受众：AI 公司招聘官 / 法务 AI 创业者 / 国际技术社区。调性：英文、简洁、重"我能交付 AI 质量评测 + 产品"。
> 配图建议：贴 `benchmark/reports/vat_domain_wipeout.html` 导出的"5 模型全灭"图，或 compliance-triangle 的 `docs/dashboard_preview.png`。
> v1.3 更新：数字刷新 + 双仓库作品集（合规三角 + 主页）+ 三证合一人设。

---

## 版本 A（完整版，约 200 词，推荐）

> I built an offline, expert-verified benchmark for Chinese legal citation hallucination — and then turned the same engine into a product. The results are uncomfortable.
>
> Tested 5 major domestic LLMs (DeepSeek-R1/V3, GLM-4-Flash, Qwen-Max, Kimi) on 23 carefully designed statute-citation traps across **8 current Chinese laws, backed by 2,327 expert-verified statute nodes (full official text)**. Even on the most forgiving metric (does the cited article even exist / is it repealed?), the best paid model still hallucinated **33.3%** of citations; the worst, **54.2%**.
>
> The standout: China's new **VAT Law (effective 2026-01-01)**. 42 citations across all 5 models, **0 verbatim-correct**. The models don't misquote it — they fabricate article numbers, exposing a training-data recency blind spot on a law that's now in force.
>
> As a **lawyer + tax agent + patent attorney building AI legal products**, I didn't stop at the benchmark. I shipped **compliance-triangle** — a legal / tax / IP compliance assistant that reuses the same verification engine to flag every AI citation with 🟢 / 🟡 / 🔴 (exists / repealed / content-mismatch) checks. 100% offline, zero-dependency, reproducible.
>
> My portfolio (github.com/vickywu97) ties it together: the benchmark that *proves* the problem, and the product that *catches* it.
>
> 👉 Benchmark: github.com/vickywu97/legal-hallucination-bench
> 👉 Product: github.com/vickywu97/compliance-triangle
>
> Curious what your legal-AI stack scores. #LegalAI #LLMevaluation #AIProduct #Hallucination #AIQuality

---

## 版本 B（极简版，约 90 词，适合首帖/移动端）

> Lawyer + tax agent + patent attorney, now building AI legal products. I shipped two open-source repos that prove I can *define, measure, and ship* AI-quality evaluation — not just prompt a model:
>
> 1. **legal-hallucination-bench**: offline, zero-dependency benchmark on 5 domestic LLMs across 8 Chinese laws (2,327 verified statute nodes). On China's new 2026 VAT Law, 42 citations, **0 verbatim-correct**.
> 2. **compliance-triangle**: turns the same engine into a 🟢🟡🔴 compliance checker for legal / tax / IP citations.
>
> Portfolio: github.com/vickywu97
> #LegalAI #AIProduct #LLMevaluation

---

## 中文 LinkedIn / 脉脉版（面向国内招聘官，见 `promo_maimai_cn.md`）
