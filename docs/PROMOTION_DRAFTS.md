# 作品集推广文案草稿（PROMOTION DRAFTS）

> 用途：把 `legal-hallucination-bench` 推给 **AI 公司招聘官 / 法务 AI 创业者 / 技术社区**。
> 核心理念：**star / 下载不是指标**，目标是触达对的那 5–20 个人。
> 仓库杀手锏（反直觉 + 有数据）：*2026 年新《增值税法》生效，5 个国产大模型 42 次法条引注 0 次正确*。
> 配合动作（GitHub 网页，git 推不上去）：设 Topics、设 Social preview 图、填 About 栏。

---

## 1. LinkedIn 帖文（英文，可直接贴）

> I built an offline, expert-verified benchmark for Chinese legal citation hallucination — and the results are uncomfortable.
>
> Tested 5 major domestic LLMs (DeepSeek-R1/V3, GLM-4-Flash, Qwen-Max, Kimi) on 23 carefully designed statute-citation traps across 8 current Chinese laws. Even on the most forgiving metric (does the cited article even exist / is it repealed?), the best model still hallucinated **50.0%** of citations.
>
> The standout: China's new **VAT Law (effective 2026-01-01)**. 42 citations across all 5 models, **0 verbatim-correct**. The models don't misquote it — they fabricate article numbers, exposing a training-data recency blind spot on a law that's now in force.
>
> As a lawyer + tax agent + patent attorney pivoting to AI legal product management, this repo is my proof that I can define, quantify, and ship AI-quality evaluation — not just prompt a model. 100% offline, zero-dependency, reproducible.
>
> 👉 github.com/vickywu97/legal-hallucination-bench
> Curious what your legal-AI stack scores. #LegalAI #LLMevaluation #AIProduct #Hallucination

*提示：贴的时候把 `benchmark/reports/vat_domain_wipeout.html` 导出成 PNG 当配图，点击率更高。*

---

## 2. 知乎 / 掘金 文章（中文）

### 标题候选（挑一个最反直觉的）
- 《新〈增值税法〉2026 生效，我把 5 个国产大模型测到"集体翻车"》
- 《法律 AI 不能犯的错：为什么 42 次法条引注里 0 次正确》
- 《律师亲测：5 个主流大模型，在"引用法条"这件最基础的事上全军覆没》

### 推荐结构
1. **我是谁、为什么做**：律师 + 税务师 + 专利代理师，转 AI 法律 PM；法律文本有强制约束力，模型"差不多"会出事。
2. **方法（为什么结论可信）**：专家逐条核验 KB（每条带 `flk.npc.gov.cn` 官方源 + 具名签名）；逐字二元判定（逐字=1.0，否则=0）；零容忍旧法陷阱。结论只来自模型答案文本本身，无可辩驳。
3. **核心发现**：
   - 最宽容尺度（条文是否存在 / 是否废止）下，最好模型 HVI 仍 50.0%，最差 64.6%。
   - 免费 GLM-4-Flash/DeepSeek-V3(55.0%) 与付费 Qwen-Max(54.5%) 几乎同档；v1.2 中 Qwen-Max 反超 GLM-4-Flash；"贵即好"不成立。
   - **增值税法域（2026-01-01 施行）42 次引注 0 准确**，失败是"编造条号"而非"张冠李戴"——暴露训练数据时效盲区。
   - 内容级幻觉率全员 100%（没有任何一条逐字复述原文）。
4. **这对法律 AI 落地意味着什么**：RAG 必须有权威法条源 + 精确引用校验，否则幻觉直接进入合同/意见书。
5. **仓库链接 + 一键复现**：`python -S -m benchmark.run --offline --out-dir sample_demo_reports`。

### 开篇钩子（直接抄）
> 2026 年 1 月 1 日，《增值税法》正式施行。我拿它当试纸，喂给 5 个主流国产大模型，结果 42 次法条引注，没有一次是对的——而且错的不是"记混了"，是干脆"编了一个不存在的条号"。

---

## 3. 一句话 Elevator Pitch

**中文**：
> 我是一个有律师、税务师、专利代理师三重资质的法律科技从业者，正在转向 AI 法律产品。我做了一个离线、零依赖的中文法律引注幻觉基准：用专家逐条核验的知识库 + 逐字二元判定，把大模型"编造法条、引用废止法"的幻觉量化成可复现的跑分——实测 5 个国产模型在 2026 年新《增值税法》上 42 次引注 0 次正确。它证明我能定义、量化并交付 AI 质量评测，而不只是会调 prompt。

**English**：
> I'm a lawyer, tax agent, and patent attorney pivoting into AI legal product management. I built an offline, zero-dependency benchmark that quantifies Chinese legal citation hallucination — an expert-verified statute KB plus a strict verbatim evaluator — and showed 5 major LLMs scoring 0/42 correct citations on China's new 2026 VAT Law. It's my proof that I can define, measure, and ship AI-quality evaluation.

---

## 4. 简历「项目经历」写法

**项目名**：legal-hallucination-bench · 中文法律引注幻觉基准（开源，MIT）
**角色**：作者 / 设计者 / 唯一贡献者
**时间**：2026-07 至今（v1.1 已发布）

**成果 bullet（STAR 风格，量化优先）**：
- 设计并交付一个**离线、零依赖（纯 Python 标准库）**的中文法律引注幻觉基准，覆盖 8 部现行法、212 条专家逐条核验法条（100% verified、100% 现行法）。
- 建立**二元内容评测引擎**（逐字=1.0 / 否则=0）与**零容忍旧法陷阱**（10 部废止法单源登记），将"法条引用幻觉"量化为可复现跑分。
- 实测 5 个国产大模型（DeepSeek-R1/V3、GLM-4-Flash、Qwen-Max、Kimi）23 题 115 条回答：最宽容尺度下引注幻觉率仍达 **50.0%–64.6%**；2026 年新《增值税法》域 **42 次引注 0 准确**，暴露训练数据时效盲区。
- 配套 110 个单元测试（全绿）、CI 流水线、专家标注闭环与可复现报告，作为"AI 质量可量化"的面试证据。

**面试一句话收尾**：
> 这个项目不是"我又调了个 prompt"，而是我作为法律专家，**定义了什么叫'法律 AI 的质量'**，并把它做成了任何人都能离线复现的评测产品——这正是 AI 法律 PM 该做的事。

---

## 5. 主动 outreach 名单（法务 AI / 合规方向，可私信或邮件附仓库链接）
幂律智能、华宇元典、秘塔科技、北大法宝 AI、通义法睿、得理法搜、法狗狗、无讼、理脉、以及各大厂（阿里/腾讯/字节/百度）的**法务科技 / 合规 AI** 团队招聘官。投递 AI PM / 法律合规岗时，在"作品集/GitHub"栏放本仓库链接。

---

## 6. 微信公众号推文（长文、重叙事、第一人称）

> 平台特性：打开率靠**标题 + 第一屏**；可 1000–3000 字；适合讲"我为什么做 + 方法可信 + 反差发现 + 行业意义"的完整故事；文末放仓库链接 + 引导留言/转发。

### 标题候选（抓人但不标题党，保专业感）
- 主：《我拿 2026 年新〈增值税法〉测了 5 个国产大模型，结果让人冒冷汗》
- 副：一个律师做的法律 AI 幻觉基准，把"引用法条"这件最基础的事量化成了跑分
- 备选 A：《大模型在法律问答里到底多能编？我用 212 条官方法条做了个基准》
- 备选 B：《律师亲测：5 个主流 AI，在"引用法条"上全军覆没》

### 推文结构（可直接扩写成长文）
1. **开篇钩子（第一屏）**：2026-01-01《增值税法》施行。我拿它当试纸喂给 5 个主流国产大模型——42 次法条引注，**没有一次是对的**。然后亮身份：律师 + 税务师 + 专利代理师，正在转 AI 法律 PM。
2. **为什么这件事重要**：法律文本有强制约束力。模型在合同、法律意见书、量刑建议里"差不多""编一条"，落到现实就是风险。幻觉不是彩蛋，是事故。
3. **我怎么做的（方法可信度）**：专家逐条核验知识库（每条带 `flk.npc.gov.cn` 官方源 + 具名签名，100% 现行法、0 未核验）；逐字二元判定（逐字=1.0，否则=0，法律没有"差不多"）；零容忍旧法陷阱（10 部废止法单源登记，引用即判失效）。强调：结论只来自模型答案文本本身，**无可辩驳**。
4. **实测结果**：5 模型 × 23 题 = 115 条。最宽容尺度（条文是否存在/是否废止）下，最好模型引注幻觉率仍 **50.0%**，最差 **64.6%**；免费 GLM-4-Flash/DeepSeek-V3(55.0%) 与付费 Qwen-Max(54.5%) 几乎同档，v1.2 中 Qwen-Max 反超 GLM-4-Flash；**增值税法域 42 引注 0 准确**，失败是"编条号"不是"张冠李戴"——暴露训练数据时效盲区；内容级幻觉率**全员 100%**（无一条逐字复述原文）。
5. **这意味着什么（行业视角）**：法律 AI 落地必须有权威法条源 + 精确引用校验，RAG 不是万能；给企业选型 / 从业者使用的具体建议（不要盲信"引用法条"，要校验）。
6. **收尾 + CTA**：开源仓库链接，欢迎跑分 / 提 issue；一句定位——"我能定义并量化 AI 质量，而不只是会调 prompt"。引导留言："你最常用哪个法律 AI？评论区聊聊"。

### 开篇段落可直接抄
> 2026 年 1 月 1 日，《增值税法》正式施行。作为一名律师、税务师、也是正在转向 AI 法律产品的从业者，我忍不住做了个实验：把这部新法当成试纸，喂给 5 个主流国产大模型。
> 结果让我冒了冷汗——42 次法条引注，没有一次是对的。而且错的不是"记混了"，是干脆"编了一个不存在的条号"。
> 这背后，是一个被很多人忽视的问题：当我们把法律判断交给大模型时，它连"引用一条现行法条"这件最基础的事，都还做不好。

---

## 7. 小红书笔记（短、视觉、emoji、反差钩子）

> 平台特性：封面图 + 标题决定一切；正文短、多换行、emoji、第一人称"实测/干货/踩坑"语气；结尾堆话题标签；适合人设 + 引流。封面建议用 `vat_domain_wipeout.html` 那张"5 模型全灭"图，上加大字"42 次引用 0 次对"。

### 标题候选（数字 / 反差 / 疑问）
- 《5个AI测新增值税法，42次引用0次对😱》
- 《律师实测｜大模型在法律上到底多能编》
- 《别迷信AI法律助手了，我测完冷汗直冒》
- 《转行AI PM，我做了个让大模型"翻车"的基准》

### 正文（可直接贴，按需删减）
```
作为律师+税务师+专利代理师，最近在转 AI 法律 PM 👩‍💻

顺手做了个小实验：
拿 2026 年刚施行的新《增值税法》
去测 5 个国产大模型
（DeepSeek / R1 / GLM / Qwen / Kimi）

结果——42 次法条引用，0 次准确 🤯

不是记混了，是直接编了个不存在的条号
（训练数据截止导致的时效盲区）

其实不止新法：
▫️ 最宽松尺度下，最好模型也有 50% 引用是幻觉
▫️ 免费的 GLM 居然比付费的 Qwen 靠谱
▫️ 5 个模型没有一条能逐字复述法条原文

法律 AI 不是不能做
但"引用法条"这种最基础的活都这么拉
真落到合同 / 意见书里得多吓人 💡

我做了个离线、零依赖的评测基准
212 条官方法条逐条人工核验，开源了
欢迎来跑分 👉 github.com/vickywu97/legal-hallucination-bench

#法律AI #大模型 #AI幻觉 #转行PM #增值税法 #干货分享 #人工智能
```

### 配图建议（3–4 张）
1. 封面：VAT 全灭图 + 大字"42 次引用 0 次对"。
2. 排行榜截图（5 模型 HVI 50.0–64.6%）。
3. README 架构图 / 专家核验 KB 说明（证明不是玩具）。
4. 仓库首页截图（带英文 TL;DR + 一键复现命令）。

---

## 8. 各平台一句话分发策略（汇总）
- **LinkedIn**：英文、给招聘官/国际受众，重"我能交付 AI 质量评测"。
- **知乎/掘金**：长文技术干货，重方法可信度 + 数据。
- **微信公众号**：长文叙事，重"我是谁 + 行业意义"，适合转发到法律/法务群。
- **小红书**：短平快反差，重人设 + 引流，封面图定生死。
- **共同点**：都带仓库链接；都用"5 模型 VAT 全灭"作钩子；都强调"离线可复现、专家核验"以建立可信度。
- **GitHub 侧配合**（网页设置）：Topics + Social preview 图 + About 栏，提升被搜到概率。
