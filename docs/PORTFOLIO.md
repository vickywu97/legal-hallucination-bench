# 作品集总览 · 从法律执业到 AI 法律产品

> **TL;DR (English)** — I'm **Vicky Wu**, a lawyer + tax agent + patent attorney **building AI legal products**.
> This two-repo portfolio proves I can *define, quantify, and ship*
> AI-quality evaluation for the Chinese legal/tax/IP domain:
> [`legal-hallucination-bench`](https://github.com/vickywu97/legal-hallucination-bench) is the
> offline, expert-verified benchmark; [`compliance-triangle`](https://github.com/vickywu97/compliance-triangle)
> is the product built on the same verify engine. Both are zero-dependency and reproducible.

---

## 我是谁（护城河）

| 资质 | 在作品集里的实打实贡献 |
| --- | --- |
| **律师** | 懂"引用法条"在法律实务里有多严肃 → 定下**逐字二元判定**（错一个字 = 0 分）。 |
| **税务师** | 对税法体系有系统理解 → 把**增值税法 / 企税 / 个税**优先纳入（多数法律 AI 评测不碰税法）。 |
| **专利代理师** | 职业习惯是"精确比对文本" → 权利要求差一个字就改变保护范围，与基准"一个字都不能差"同一思维。 |

> 这不是贴金。三重资质让我能**自己设计校验规则、定义陷阱、签署每一条 KB**——这是任何纯工程 / 纯算法团队无法复制的壁垒。

---

## 作品集结构（地基 → 产品）

![作品集架构](portfolio_architecture.svg)

- **① 法条知识库 KB**（地基）：2327 节点 / 8 部法完整官方全文，100% verified，专家逐条具名核验。
- **② 共享校验引擎**：`resolve_article` + `content_diff` + 旧法陷阱 + 二元判定，纯标准库、离线、可复现。
- **③-a 量化基准**（`legal-hallucination-bench`）：把"法条引用幻觉"量化成可复现跑分。
- **③-b 合规三角**（`compliance-triangle`）：用同一套引擎，给每条 AI 引注盖 🟢🟡🔴 章。

两个仓库**共用同一套 verify 引擎与 KB**，不是两个独立项目，而是一个"证明问题 → 解决问题"的闭环。

---

## 它证明了什么（给 hiring manager 的三件事）

1. **法律 / 税 / 专利领域的真实深度** —— 不是"会用 AI 查法条"，而是能定义什么叫"引用对了"，并把法律实务的精度要求翻译成可执行的判定规则。
2. **能定义并量化 AI 质量（评测 / 跑分）** —— 设计 HVI（引注幻觉率）与 CRFI（张冠李戴率）双指标，而不是笼统报一个"幻觉率"。
3. **能交付可离线跑通、零依赖、可复现的产物** —— 任何人在任何机器 clone 就能跑（含面试官），不需要注册、不需要信我的服务器。

> 一句话：**我不是"会用 AI 的法律人"，而是"知道 AI 在法律场景哪里会出错、并设计了系统来防止它的产品人"。**

---

## 关键数字（无可辩驳）

| 指标 | 结果 |
| --- | --- |
| 测试规模 | 5 个国产模型 × 23 道陷阱题 = 115 条有效回答 |
| 引注幻觉率 HVI（最宽松尺度） | **33%–54%**（连付费旗舰都不过半） |
| 内容级 EXACT（逐字合规率） | **8 个法域全部 0%** |
| 张冠李戴率 CRFI | 0%（归因结论：模型更爱"编"而非"混记"） |
| 增值税法域（2026 新法） | 42 次引注，**0 次 EXACT** |

> 结论：在中文法律引注这种最基础的任务上，当前主流国产模型存在**系统性失效**——这正是法律 AI 产品最需要被量化、被拦截的风险。

---

## 怎么看 / 怎么跑

- **基准**：见 [`legal-hallucination-bench`](https://github.com/vickywu97/legal-hallucination-bench) —— `python -S -m benchmark.run --offline --out-dir sample_demo_reports`（零依赖、无 API Key）。
- **产品**：见 [`compliance-triangle`](https://github.com/vickywu97/compliance-triangle) —— 双击 `demo/output/index.html` 看离线展示页，或 `python -m compliance_triangle.web` 粘贴你自己的 AI 回答实时校验。
- **面试应答卡**：[`docs/INTERVIEW_QA.md`](INTERVIEW_QA.md)（9 个尖锐问题 + 应答逻辑）。
- **推广草稿**：[`docs/PROMOTION_DRAFTS.md`](PROMOTION_DRAFTS.md) + 公众号 / 知乎稿。

---

## 下一步

- **KB 扩容**：证券法 / 企业破产法 / 民事诉讼法 / 行政处罚法（架构已支持"加一部法 = 拿官方源 → 逐条核验 → 跑脚本"三步）。
- **评测维度扩展**：从"法条引用"扩到"法律推理 / 法条适用判断"。
- **动态排行榜**：GitHub Pages 上的实时榜单。

> 我不需要"改变法律 AI 行业"——能让几家我感兴趣的公司看到"这个候选人是真的懂法律 AI 评测"，它就值了。
