# 作品集推广文案总索引（PROMOTION DRAFTS · v1.3）

> 用途：把**整个作品集**（不止一个仓库）推给 **AI 公司招聘官 / 法务 AI 创业者 / 技术社区**。
> 核心理念：**star / 下载不是指标**，目标是触达对的那 5–20 个人。
> 杀手锏（反直觉 + 有数据）：*2026 年新《增值税法》生效，5 个国产大模型 42 次法条引注 0 次逐字正确*。
> 配套动作（GitHub 网页，git 推不上去）：见 `GITHUB_PROFILE_CHECKLIST.md` 设 Topics / Social preview / About / Pinned。

---

## 0. 作品集三件套（对外统一叙事）

| 仓库 | 角色 | 链接 |
| --- | --- | --- |
| `legal-hallucination-bench` | **地基**：离线零依赖的中文法律引注幻觉基准（2327 条专家核验法条，5 国产模型真实跑分） | github.com/vickywu97/legal-hallucination-bench |
| `compliance-triangle` | **产品**：把同一套校验引擎做成法律/税务/IP 三域 🟢🟡🔴 合规助手 | github.com/vickywu97/compliance-triangle |
| `vickywu97`（profile） | **人脸**：作品集主页 README（双仓库卡片 + 架构图 + 三证护城河） | github.com/vickywu97 |

一句话人设：**律师 + 税务师 + 专利代理师，在做 AI 法律产品；能定义、量化并交付 AI 质量评测，而不只是会调 prompt。**

---

## 1. 各平台文案（可直接发，均已刷新到 v1.3）

| 文件 | 平台 / 用途 | 状态 |
| --- | --- | --- |
| `wechat_post_v1.3.md` | 微信公众号长文（故事+实测+行业警示+双仓库） | ✅ 定稿 |
| `zhihu_article_v1.3.md` | 知乎 / 掘金长文（方法可信+数据+表格） | ✅ 定稿 |
| `linkedin_post_v1.3.md` | LinkedIn 英文帖（A 完整 / B 极简两版） | ✅ 定稿 |
| `promo_maimai_cn.md` | 脉脉 / LinkedIn 中文短文（人设+双仓库，3 个版本） | ✅ 定稿 |
| `GITHUB_PROFILE_CHECKLIST.md` | 三个仓库门面设置清单（网页操作） | ✅ 待你点 |
| `LAUNCH_PLAN.md` | 发布顺序 + CTA 话术 + 统一口径 + 数据红线 | ✅ 总策划 |

> 旧版 `wechat_post_v1.2.md` / `zhihu_article_v1.2.md` 已删除（数字过时）。

---

## 2. v1.3 核心数字（对外统一口径，切勿混入旧值）

- **KB**：2327 节点 = 8 部现行法完整官方全文；212 条专家逐条署名核验作黄金真相。
- **实测**：23 题 × 5 模型 = 115 条回答。HVI 区间 **33.3%（Qwen-Max 最佳）~ 54.2%（Kimi 最差）**。
- **旗舰钩子**：2026 新《增值税法》域，5 模型 **42 次引注 0 次逐字正确（EXACT=0）**，HVI 70.6%。
- **结构发现**：CRFI（记混率）全员 0%；内容级幻觉率（hr_content）全员 100%（无一条逐字复述原文）。
- **结论**：免费 GLM-4-Flash / DeepSeek-V3（45.0%）并列超越付费旗舰 R1（47.6%）；"贵即好"不成立。

---

## 3. 一句话 Elevator Pitch

**中文**：
> 我是一个有律师、税务师、专利代理师三重资质的法律科技从业者，在做 AI 法律产品。我做了两个开源作品：① 离线零依赖的中文法律引注幻觉基准（2327 条专家核验法条，实测 5 个国产模型在 2026 新《增值税法》上 42 次引注 0 次逐字正确）；② 合规三角（把同一套校验引擎做成法律/税务/IP 三域 🟢🟡🔴 合规助手）。它们证明我能定义、量化并交付 AI 质量评测。

**English**：
> I'm a lawyer, tax agent, and patent attorney building AI legal products. I built two open-source repos that prove I can define, measure, and ship AI-quality evaluation — not just prompt a model: (1) legal-hallucination-bench, an offline benchmark on 5 domestic LLMs across 8 Chinese laws (2,327 verified statute nodes; 42 VAT-law citations, 0 verbatim-correct); (2) compliance-triangle, a 🟢🟡🔴 legal/tax/IP citation checker reusing the same engine. Portfolio: github.com/vickywu97

---

## 4. 简历「项目经历」写法

**项目名**：legal-hallucination-bench · 中文法律引注幻觉基准（开源，MIT）+ compliance-triangle · 三域合规校验产品
**角色**：作者 / 设计者 / 唯一贡献者
**时间**：2026-07 至今（v1.3 已发布）

**成果 bullet（STAR 风格，量化优先）**：
- 设计并交付**离线、零依赖（纯 Python 标准库）**的中文法律引注幻觉基准，覆盖 8 部现行法、2327 条专家核验法条（100% verified、100% 现行法）。
- 建立**二元内容评测引擎**（逐字=1.0 / 否则=0）与**零容忍旧法陷阱**（10 部废止法单源登记），将"法条引用幻觉"量化为可复现跑分。
- 实测 5 个国产大模型（DeepSeek-R1/V3、GLM-4-Flash、Qwen-Max、Kimi）23 题 115 条回答：最宽容尺度下引注幻觉率仍达 **33.3%–54.2%**；2026 年新《增值税法》域 **42 次引注 0 逐字正确**，暴露训练数据时效盲区。
- 复用同一校验引擎交付 **compliance-triangle** 产品：对 AI 法条引注做存在性/时效性/内容匹配三层 🟢🟡🔴 校验，离线可跑、零依赖。
- 配套 110+ 单元测试（全绿）、CI 流水线、专家标注闭环与可复现报告，作为"AI 质量可量化"的面试证据。

**面试一句话收尾**：
> 这个项目不是"我又调了个 prompt"，而是我作为法律专家，**定义了什么叫'法律 AI 的质量'**，并把它做成了任何人都能离线复现的评测 + 一个能挡住质量事故的产品——这正是做 AI 法律产品该做的事。

---

## 5. 主动 outreach 名单（法务 AI / 合规方向，可私信或邮件附主页链接）

幂律智能、华宇元典、秘塔科技、北大法宝 AI、通义法睿、得理法搜、法狗狗、无讼、理脉，以及各大厂（阿里/腾讯/字节/百度）的**法务科技 / 合规 AI** 团队招聘官。投递 AI PM / 法律合规岗时，在"作品集/GitHub"栏放 `github.com/vickywu97`。

---

## 6. 各平台一句话分发策略（汇总）

- **GitHub（门面）**：先设 Topics/Social preview/About/Pinned（见清单），是所有外链的落地页。
- **知乎/掘金**：长文技术干货，重方法可信度 + 数据，长期被搜索收录。
- **微信公众号**：长文叙事，重"我是谁 + 行业意义"，适合转发法律/法务群。
- **LinkedIn（英文）**：给国际/招聘官受众，重"我能交付 AI 质量评测 + 产品"。
- **脉脉 / LinkedIn 中文**：极简人设短文，直投招聘官。
- **小红书（可选）**：短平快反差，封面图定生死，引流到 GitHub / 公众号。
- **共同点**：都带三个仓库链接；都用"5 模型 VAT 42/0"作钩子；都强调"离线可复现、专家核验"以建立可信度。
