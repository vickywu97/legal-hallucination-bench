# v1.2 Release 发布稿（修正版）

> 用途：复制本文件内容到 GitHub Releases 页面发布。
> 沙箱无 `gh` CLI、GitHub 连接器未连接，**实际 Tag/Release 点击由你在网页端完成**
> （惯例：你在 https://github.com/vickywu97/legal-hallucination-bench/releases 点
> "Draft a new release"，Tag 填 `v1.2`）。
>
> 注意：本稿已**删除"CRFI 首次激活"伪结论**——真实数据 CRFI 在 115 条中 0 触发，
> 已在 README / CHANGELOG / PORTFOLIO_SUMMARY 如实记录，发布稿须与之一致。

---

**Tag**：`v1.2`（Create new tag on publish）

**Title**：`v1.2 — 8法域/212节点 · 实体税法域激活 · 模型"编/概括"而非"记混"`

**Describe**：

> ## v1.2 核心交付
> - **8 大法域、212 节点专家核验知识库**：新增《企业所得税法》(60条)、《个人所得税法》(22条)、专利法补强(14条)；全部经用户提供官方 .doc 逐字提取 + 三重资质专家署名核验。
> - **23 道四类陷阱测试题**：新增 Q19–Q23（企税/个税/专利法 张冠李戴陷阱），覆盖税率/不征税/免税/职务发明等易混点对。
> - **5 模型真实排行榜（23 题 / 115 条）**：DeepSeek-R1 50.0% · Qwen-Max 54.5% · DeepSeek-V3 55.0% · GLM-4-Flash 55.0% · Kimi 64.6%（引注最多却垫底）。
> - **Qwen-Max 反超 GLM-4-Flash 升至第二**：新增实体税法题目暴露免费模型在企税/个税域的相对弱势；"贵即好"与"免费即差"均不成立。
> - **CRFI（张冠李戴率）实测仍 0% —— 这是评测的归因结论，不是指标失效**：5 模型在 Q19–Q23 的失分形态为"引对正确条号、却写概括/改写内容"(PARTIAL/FABRICATED_GENERIC) 与"引不存在条号"(NOT_FOUND)，**从不出现"条号对、内容错"**；硬 `MISATTRIBUTED` 与软探针 `SOFT_MISATTRIBUTED` 在 115 条中均 0 触发。这恰恰说明真实模型更倾向"编造/概括"而非"记混邻居条文"——详见 README 已知局限。
> - **全量 110 项测试绿灯**，CI 自动化验证；评分引擎离线零依赖、可复现。
>
> [完整变更记录](https://github.com/vickywu97/legal-hallucination-bench/blob/master/CHANGELOG.md)
