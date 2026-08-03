# Methodology / 方法学

本基准的核心设计哲学是**信心加权评测（confidence-weighted evaluation）**：当"真值（ground truth）"因数据可得性受限而无法完全获取时，按数据硬度分层下结论，而不是强行给一个不可靠的总分。

## 一、为什么分层？

| 引注类型 | 真值来源 | 可得性 |
|---|---|---|
| 法条 / 司法解释 | flk.npc.gov.cn 公开快照（手动策展+版本化） | ✅ 公开 |
| 指导性案例 / 公报案例 | 最高法官网发布，**有界集合** | ✅ 公开 |
| 普通裁判文书（案号） | 裁判文书网反爬 + 会员库 | ❌ 不可得 |

普通案号无法批量核验存在性——这是真实硬墙（裁判文书网反爬、威科/北大法宝需会员）。因此本基准**不宣称能做案例存在性 oracle**，而是诚实分层。

## 二、三层核验

- **Tier 1 硬核验**（能下"真/假"结论）：法条、司法解释、指导性案例 → 存在性 + 内容 diff（二元：完全一致 = 1.0 分，否则 = 0 分；PARTIAL/TRUNCATED/MISATTRIBUTED 仅作诊断子类，得分恒 0）。
- **Tier 2 软核验**（只下"异常"结论）：普通案号 → 格式合法性 + 所称法院是否存在 + 层级-类型-年份自洽。明确标注"非存在性核验"。
- **Tier 3 透明不可验**：Tier1/2 覆盖不到的引注 → 报"不可验证率"，**不计入幻觉率分母**。

## 三、版本化法条图谱与时序幻觉

法条序列化格式已锁定为 `laws_index.json`（法律级元数据）+ `statutes.jsonl`（条文版本节点）。每个条文版本节点带 `effective_date` 与 `revision_of`（指向被其取代的**前一版本**，含跨条 relocation，如旧《公司法》第13条 → 新法第10条）。**时间窗不存储、由 `revision_of` 推导**：节点 `n` 的窗口 `window(n) = [n.effective_date, s.effective_date)`（`s.revision_of == n.id`），最后一条为 `[eff_n, null)`；左闭右开、无间隙、无重叠（`tests/test_jsonl_adapter.py` 强制断言）。评测时按**题目上下文时间**解析到当时有效版本。这天然检测：
- 引用**尚未生效**的条文
- 引用**已废止/已调整**的条文（如某旧版条文在修订后被 relocation 至新法条号，按旧条号引用即"此版本无此条"）

## 四、陷阱探针（Arm B）——科学核心

不依赖任何外部数据、ground truth 100% 由构造已知，全自动可复现、无需标注。类型见 MVP_DESIGN.md §3。
为防止模型"应试"，部分探针作为**隐藏测试集**不随 repo 发布。

## 五、诚实边界（写在脸上）

1. 本基准**不宣称**普通裁判文书存在性核验。
2. **词条来源可信度是本项目命门，须如实声明**：`statutes.jsonl` 的条文文本**只从官方法律法规数据库（flk.npc.gov.cn）复制粘贴**，绝不由 LLM 凭记忆生成——LLM 仅提供 `SEED` 草稿（`unverified`），最终断定权在人类专家。经逐条核对、由专家在**核验台账 `verifications.json`** 中落 `verified` 后，节点方可被评测引擎当作事实依据。**截至当前（v1.0），KB 共 99 个节点、100% `verified`，已可用于给模型打分**；后续扩容新增条文仍须走同一门禁，未核验节点 `build` 重生后永不丢失人类判定。核验闭环工具 `knowledge_base/verify_kb.py`：`report`（进度+报告）、`pending`（待核验清单）、`show/open <id>`（看原文/打开来源）、`review`（交互式逐条比对）、`verify <id> --accept|--reject [--correct 文本]`（单次判定，支持附修正文本将错误脚手架升级为已核验事实）。`verifications.json` 与 LLM 编写的 `SEED` **物理分离**——`build_statute build` 随时重生 `statutes.jsonl`，但**永不丢失**任何人类判定。仅 `verified` 节点可被评测引擎当作事实依据；`unverified` 节点仅供引擎/管线开发调试。
3. 法条录入经 `knowledge_base/build_statute.py` 流水线：专家从官方法律法规数据库**复制粘贴**原文（不重新输入，避免转录错）+ 元数据，脚本自动生成 id/排序号、解析 `revision_of`、内置全量完整性校验（`tests/test_kb_integrity.py` 每次新增条文必须绿）。**LLM 只负责搭脚手架，不负责定事实**；最终断定权在专家。
4. 抽取召回不足会**低估**幻觉率——因此抽取器（`benchmark/extract.py`）内置"疑点启发式"：对正则未命中的文本段，若含"条/款/项"邻近法律名/法释/案号令牌，标记为 `suspected` 供审计；并以**公开标注集 + 透明召回/精确数字**替代沉默低估（见 §七）。
5. Arm A 的"不可验证率"如实报告。
6. 本基准**不构成法律意见**，也不向终端用户输出法律建议。
7. 法条来源为公开官方法律法规数据库的策展快照，**不爬裁判文书网**。
8. **粒度边界**：当前内容 diff 容忍到**条级**；款/项（如"第584条第一款"）粒度暂未覆盖，比对以整条为单位。
9. **废止法名捕获（时序幻觉陷阱）**：已废止法名（如 `旧公司法`/`合同法`/`民法总则`/`侵权责任法`/`物权法`/`担保法`/`婚姻法`/`继承法`/`收养法`/`民法通则`）**统一在代码级 `benchmark/extract.py` 的 `DEPRECATED_LAW_NAMES` 单一真相源中登记**（废止法名 → (存续 law_code, 废止日)），`laws_index.json` 不再携带任何 `deprecated_aliases` 字段，保证知识库 100% 现行法、且陷阱列表只有一处可维护。这是**刻意陷阱**：模型在废止日之后引用旧法名 = 引用已废止法律名称 = 时序幻觉。抽取器在 `_lookup_name`/`_name_pattern` 中直接查 `DEPRECATED_LAW_NAMES` 置位 `deprecated_alias`；loader 的 `resolve_article` 在同一真相源下把废止法名映射到存续法（保证条文解析可继续），并在 `as_of_date >= repealed_date` 时置位 `used_deprecated_alias`，供 verify.py 确定性判为时序幻觉——**不因规范化而丢失"模型使用了旧法名"这一关键证据**。
10. **未命中 KB 不计分母**：模型引注未能在 KB 中匹配（法条库仅覆盖核心条文）时，记为 `unverifiable` 并单独报告**不可验证率**，**不计入幻觉率分母**，避免虚高或虚低。另：命中节点若为 `unverified`，评测引擎须拒绝将其作为事实依据（见 §四 评测门禁）。

## 六、可复现性

- 模型版本 pin 死、temperature=0、记录 seed 与原始输出。
- 核验逻辑以规则为主（保证可复现），LLM 仅作兜底抽取。
- 重跑应得到同一分数（bootstrap CI 报告不确定性）。

## 七、抽取器 audit 机制（Week 3）

抽取是全局瓶颈：召回不足 → 漏判模型引注 → 系统性低估幻觉率。本基准用**透明 audit** 替代"假装全覆盖"：

- **离线默认路径 = 正则 + 中文数字归一化 + 疑点启发式**，零运行时依赖、可复现。覆盖约 70–80% 标准引注。
  - 中文数字归一化：`第五百八十四条 → 584`、`第一千一百六十五条 → 1165`。
  - 法律名别名归一化到 `law_code`；废止法名由代码级 `DEPRECATED_LAW_NAMES`（§五.9）统一捕获并置位 `deprecated_alias`（时序幻觉陷阱信号）。
  - 疑点启发式：对正则未命中的段，若含"条/款/项"邻近法律名/法释/案号令牌，标记为 `suspected` 进入审计队列——**公开漏抽**，而非沉默低估。
- **LLM 兜底仅 `--live` 可选**，不进离线默认路径、不破坏零依赖。
- **标注集门禁**：`benchmark/fixtures/extract_sample.json`（~30 段真实/合成法律文本 + 人工标引注，含非标准变体、废止法名陷阱、负样本）。`tests/test_extract.py` 在该集上强制 **召回 ≥ 95%、精确 ≥ 90%**；`suspected` 启发式结果不计入这两个分母（属审计信号）。

**实测（2026-08-02）**：标注集 31 条 gold / 31 条严格抽取 → 召回 **0.968**、精确 **0.968**，达标。后续扩充标注集须保持门禁不降，并在每次发版公布最新 audit 数字。

## 八、内容对比引擎（Week 4 + 100% 精确）

`benchmark/verify.py` 在三层核验 + 来源门禁之上，落地**二元内容 diff**
（详见 `docs/DIFF_POLICY.md`，阈值唯一权威）：
`EXACT`（逐字归一化相等，score 1.0）/ `FABRICATED`（任何非逐字偏离，score 0.0）。
FABRICATED 细分为诊断子类 `PARTIAL`（覆盖率≥50%）/ `TRUNCATED`（官方真前缀截断）/
`MISATTRIBUTED`（张冠李戴：候选文本与同法另一条已核验节点匹配度>0.80）/
`FABRICATED_GENERIC`，**所有子类得分恒为 0.0——不存在中间分**。判定为确定性规则、
零依赖、可复现，无任何 LLM 介入 diff。

> **绝对二元策略（2026-08-03 收口）**：法条引用无"差不多"——只有逐字相等才算
> EXACT（OK，1.0），任何非逐字偏离一律 FABRICATED（HALLUCINATION，0 分）。
> `diff_level` 字段严格只有 `EXACT` / `FABRICATED` 两值。

时序陷阱 `TEMPORAL_DEPRECATED` 与存在性失败 `NOT_FOUND` 由
`verify_citation()` 在 diff 之前优先判定；来源门禁 `UNVERIFIED_GT` 由
`refuse_unverified_ground_truth()` 落 `UNVERIFIABLE`、不计入 HR 分母。

配套 `benchmark/score.py` 聚合头条跑分：`hr_statutory`（法条级幻觉率）、
`hr_content`（仅含 candidate_text 的内容级子集）、`rate_deprecated`（时序幻觉率）、
`rate_unverifiable`（透明不可验率）、`per_domain`（分法域 HR），并给出 bootstrap
95% 置信区间（固定 seed）。`python -m benchmark.run --verify-demo` 可端到端演示
抽取→核验→二元 diff 全流程。

**评分面永远只用最新已核验版本**：在 `as_of ≥ 2024-07-01` 时，`公司法第X条` 解析到 2024 已核验版本；引用已废止的 `旧公司法` 被确定性判为时序幻觉（见 §五.9）。KB 不含任何旧版 2018《公司法》节点（已整体删除，仅保留 `DEPRECATED_LAW_NAMES` 单一真相源陷阱），故评分面绝不会混入失效或未核验条文。即：**评分面永远只用最新法、且 100% 现行法、100% 已核验**。

