# 法律引注幻觉检测 Bench — 6 周 MVP 施工图

> 本文件取代 `MVP_DESIGN.md` 中的"6 周计划"小节。Schema 已锁定（`laws_index.json` + `statutes.jsonl`、`law_code` 助记码、不存 `repeal_date`、~200 条核心条文）。
> 核心纪律：**离线优先**——每周验证都在 `python -S`（无 site-packages）干净环境下跑，零第三方运行时依赖（继承 DD-007 教训）。
>
> ⚠️ **本文件为 6 周施工计划（历史记录），已被最终实现取代。** 最终判定政策以 [`docs/DIFF_POLICY.md`](DIFF_POLICY.md) 与 [`docs/METHODOLOGY.md`](METHODOLOGY.md) 为准；内容 diff 已从计划中的"四级"收口为"二元"。

---

## 0. 总览

| 周 | 主题 | 关键交付 | 验证门 |
|---|---|---|---|
| 0（已完成） | 脚手架 + 引擎地基 | zero-dep 工程骨架 + `resolve_article` 时序引擎 + 8 测试 | `--demo` 跑通 |
| 1 | 锁定 schema 接入 | `laws_index.json` + `statutes.jsonl` + JSONL adapter | adapter 测试绿 + 时间窗断言 |
| 2 | KB 策展流水线 + 脚手架 | `build_statute.py` 流水线 + 全量完整性 CI + 覆盖报告 + provenance 门 | 完整性 CI 绿；provenance 门就位（unverified 节点不可用于评分） |
| 3 | 引注抽取器 | `extract.py` 正则+归一化+疑点启发式 + 抽取审计 | 标注集召回≥95% + 公开 audit |
| 4 | 核验引擎 + Tier2 案号 | `verify.py` 逐条准确率≥98% | 标注集达标 |
| 5 | 评分器 + 审计报告 + Arm B | `score.py`/`report.py` + 20 陷阱 | 端到端出榜+报告 |
| 6 | 包装 / 发布 / live / 运营 | README + ROADMAP + 干净容器出榜 | clone 即跑 |

**两条并行流**：
- **Arm B（自动评分，本计划主线）**：陷阱探针，ground truth 由构造可知，offline 即可出榜。MVP 第一张排行榜靠它。
- **Arm A（专家标注开放题，用户劳动流）**：~50 条真实法律问题 + 专家逐条判定。**Week 2–3 启动标注**（利用策展间隙），Week 4 收尾审查，MVP 至少 30 条，持续扩充，喂同一 `score.py`。不阻塞主线。

---

## Week 0 — 脚手架 + 引擎地基（已完成）

已交付（2026-07-31）：
- `pyproject.toml`（`dependencies = []` 零运行时依赖）、MIT LICENSE、中英双语 README（含诚实边界）、CONTRIBUTING、`docs/METHODOLOGY.md`
- `knowledge_base/loader.py`：`resolve_article(law, article_no, as_of_date)` 走 revision + `amended_by` 链，已完成**时序解析**验证（旧公司法第13条 @2020 命中旧文、@2025 查无、新法第10条 @2025 命中）
- KB（旧嵌套 JSON 格式）：民法典 / 公司法(2018修正+2023修订) / 刑法 + `courts.json` 层级图谱
- `benchmark/` 骨架（`run.py --demo`、extract/verify/score/report/models 占位）+ `tests/`（8 项 unittest 全绿）

**本计划对 Week 0 的唯一改动**：Week 1 把 KB 序列化格式从嵌套 JSON 迁移到锁定的 `laws_index.json` + `statutes.jsonl`，引擎逻辑不变（加 adapter）。

---

## Week 1 — 锁定 Schema 接入（Reconciliation）

**目标**：把已跑通的嵌套 JSON loader 接入锁定的 `laws_index.json` + `statutes.jsonl`，零回归。

**交付物**：
- `knowledge_base/laws_index.json` — 5 部法律级元数据（含 `aliases` 已含废止法名："合同法""民法总则"归入 CIVIL_CODE；"旧公司法"归入 COMPANY_LAW）
- `knowledge_base/statutes.jsonl` — 迁移现有 sample 条文到新格式（~30 节点，含公司法 16→15 双版本）
- `knowledge_base/loader.py` — 新增 `load_from_jsonl(index_path, jsonl_path)`：读两份文件 → 组装成 `resolve_article` 接受的内存模型（保留 `amended_by`/`revision_of` 链、`effective_from/until` 推导）
- `tests/test_jsonl_adapter.py`：
  - adapter 产出的内存模型与旧结构**等价**（同一查询返回同一结论）
  - **时间窗左闭右开断言**（CI 核心）：同一 `(law_code, article_sort_key)` 的版本，`window_i = [eff_i, eff_{i+1})`，最后一条 `[eff_n, null)`；断言无重叠、无间隙
  - `revision_of` 指向的节点必须存在
- `docs/METHODOLOGY.md` 补三处诚实声明：① 款/项粒度未覆盖（content 比对容忍到条级）；② alias 含废止法名以抓"引旧法名"的时序幻觉；③ 引注未命中 KB → 记 `unverifiable`，**不计入幻觉率分母**

**验证门**：
```
python -S -m unittest discover -s tests   # 旧 8 + 新 adapter 测试全绿
python -S -m benchmark.run --demo          # 新格式下时序解析仍正确
```

---

## Week 2 — KB 策展：5 部法律 ~200 条核心条文

**目标**：按"A1 筛选表"录入高频被引条文，单人 2–3 天完成。

> **⚠️ 来源可信度铁律（Week 2 增补，最高优先级）**：KB 文本只能由**专家从官方法律法规数据库复制粘贴**并逐项在**核验台账 `verifications.json`** 落 `verified` 后，才算 ground truth。当前 `statutes.jsonl` 的 102 个节点是 LLM 依记忆生成的**脚手架（scaffold）**，全部 `verification_status=unverified`，**不得用于给模型打分**。`verifications.json` 与 LLM 编写的 `SEED` **物理分离**，`build_statute build` 随时重生 `statutes.jsonl` 但永不丢失人类判定；`verify.py` 的 `refuse_unverified_ground_truth()` 会在命中未核验（或 `rejected`）节点时返回 `UNVERIFIABLE`，物理上阻断"用幻觉法条测幻觉"。**人类核验闭环工具 `knowledge_base/verify_kb.py`**（`report`/`pending`/`show`/`open`/`review`/`verify`）已配套交付，专家逐条比对官方法源、一键落 verdict、自动生成进度报告。约 200 条目标指的是**专家核验后**的条文，不是 LLM 生成条数。

**筛选分配（合计 ~200 条 / ~250 版本节点）**：

| 维度 | 示例条文 | 约数 |
|---|---|---|
| 合同编核心 | 584 违约赔偿、496 格式条款、563 解除权 | 40 |
| 物权担保 | 394 抵押、425 质权、447 留置 | 30 |
| 侵权编核心 | 1165 过错责任、1218 医疗损害 | 20 |
| 公司组织 | 16→15 担保、33→57 股东知情权、20→23 人格混同 | 30 |
| 税法核心 | 征管法 4 纳税义务、35 核定征收、32 滞纳金 | 20 |
| 专利三性 | 22 新颖性、23 创造性、24 实用性 | 10 |
| 刑法常见罪名 | 266 诈骗、382 贪污、389 行贿 | 30 |
| 陷阱相关 | 废止条文、修订前后对比条 | 20 |

**交付物**（录入质量加固，#1）：
- **`knowledge_base/build_statute.py` 流水线**：从 flk.npc.gov.cn **复制粘贴**法条原文（避免重新输入出错）+ 结构化元数据（条文号/所属法/施行日期/`revision_of`），脚本自动生成 JSONL 行并内置校验：
  - 自动生成 `id`（=`{law_code}_{sort_key}_v{ver}`）与 `article_sort_key`
  - 校验 `effective_date` 格式、若有 `revision_of` 则链完整性（指向节点存在）
  - 每 50 条报告进度
- `statutes.jsonl` 扩到 ~250 版本节点（含公司法 16→15 / 33→57 / 20→23 等双版本 relocation），由脚本产出
- `laws_index.json` 补 `TAX_ADMIN_LAW` / `PATENT_LAW` 完整元数据
- 每条带 `source_url`（flk.npc.gov.cn）+ `source_accessed_at`
- **`tests/test_kb_integrity.py`（全量硬门）**：所有节点 `content` 非空、不含非法字符、条文号与 `sort_key` 匹配；所有 `revision_of` 指向有效 id；`(law_code, sort_key)` 时间窗无重叠/无间隙。**每次新增条文后此 CI 必须绿。**
- `tests/test_kb_coverage.py`：每部法覆盖条文数 ≥ 阈值；**同时输出覆盖报告**（每部法条文数、编/章分布、双版本条比例）作为 CI artifact，可嵌入 `METHODOLOGY.md`
- PR 记录：随机抽 10 条与官方源人工比对结果

**验证门**：完整性 CI 绿（content 非空 + revision_of 有效 + 时间窗无重叠/无间隙 + verification_status 合法）；覆盖阈值达标。**在专家未置 `verified: true` 前，本 KB 仅用于引擎/管线开发调试，不做任何模型评分**——`METHODOLOGY.md` 须如实声明"当前 102 节点均为 unverified 脚手架"。

> 全量覆盖（民法典 1260 条等）列为 Phase 2 社区众筹目标，写入 `ROADMAP.md`。

---

## Week 3 — 引注抽取器（extract.py）

**目标**：从模型回答抽全部法律引注（"咽喉"），召回不足直接低估幻觉率。

**设计（加固 #2，主动纠偏）**：
- **offline 默认路径 = 正则 + 归一化 + 疑点启发式**，零依赖、可复现。覆盖约 70–80% 标准引注。
  - 正则识别：法条 `《XX法》第X条`、司法解释号 `法释〔2020〕17号`、指导案例号 `指导案例18号`、案号 `(2021)最高法民终123号`、法规
  - 中文数字归一化：`第五百八十四条`→`584`、`第一百一十三条`→`113`
  - **疑点启发式（关键）**：对正则未命中的文本段，若含"条/款/项"邻近法律名/法释/案号-like 令牌，标记为 `suspected_citation` 供审计——**用透明漏抽统计替代沉默低估**，而非假装全覆盖
- ~~**LLM 兜底 = 仅 `--live` 模式可选**~~（历史设计；当前版本未实现 `--live`，改为"你跑任意模型产出 `answers.jsonl`，本工具离线评分"）
  - ⚠️ **不采用 BERT 序列标注**：依赖 torch（数百 MB、非纯 Python），比 python-docx 更违背离线零依赖原则，与本项目硬约束冲突。
- 输出标准化 citation：`{type, law_code, article_number, article_sort_key, original_text, position, suspected?}`

**交付物**：
- `benchmark/extract.py`（上述混合设计）
- `benchmark/fixtures/extract_sample.json` — ~30 段真实/合成法律文本 + 人工标引注（含非标准变体），用于测召回/精确
- `tests/test_extract.py`：标注集上**召回 ≥95%、精确 ≥90%**
- **`METHODOLOGY.md` 写入抽取 audit 机制**：定期抽查抽取结果、统计漏抽率并**公开展示 audit 数字**（比单纯宣称达标更有可信度）

**验证门**：标注集召回/精确达标；audit 机制文档到位；对 `sample_outputs/` 抽取无崩溃。

---

## Week 4 — 核验引擎（verify.py）+ Tier2 案号结构

**目标**：对每条引注下"真 / 假 / 异常 / 不可验"结论（分层下结论）。

**前置（加固 #3，编码前先写）**：`docs/DIFF_POLICY.md` 用具体例子**量化四级边界**，否则评测不可复现（评测基准死穴）：

| 等级 | 定义 | 量化标准 | 示例 |
|---|---|---|---|
| 完全一致 | 逐字匹配 | 编辑距离 = 0 | 与 KB 完全一致 |
| 实质一致 | 核心要件完整，仅省略修饰/列举 | 编辑距离 ≤ 全文 10% 且无法律要件缺失 | "造成对方损失的" vs "造成对方损失的，" |
| 部分遗漏 | 遗漏某法律要件或关键但书 | 缺失独立要件（如"但是……"后半句） | 漏掉"包括合同履行后可以获得的利益" |
| 编造 | 捏造不存在的条文内容 | 出现 KB 中不存在的核心陈述 | 虚构构成要件 |

`verify.py` 的 diff 严格按此实现，**测试用例覆盖所有四级边界**。

**交付物 `benchmark/verify.py`**：
- **Tier1 硬核验**：
  - 存在性：`resolve_article(law, no, as_of)` 按时间窗判定
  - **废止 + relocation 提示（C3）**：命中废止节点时，沿 `revision_of` 找到现行有效版本，输出"已废止，现行有效为 XX 法第 YY 条"而非只报"已废止"
  - 内容四级 diff（按 `DIFF_POLICY.md`，difflib + 量化阈值）：完全一致 / 实质一致 / 部分遗漏 / 编造
- **Tier2 软核验**（普通案号，**明确标注非存在性**）：
  - 格式合法性（《案号规定》）
  - `courts.json` 层级图谱校验：所称法院是否存在、层级/地域/案件类型代码是否自洽
- **Tier3 透明**：覆盖不到 → 标 `unverifiable`，**不进 HR 分母**，单独报告"不可验证率"
- `tests/test_verify.py`：标注集上逐条判定准确率 ≥98%（Tier1 规则驱动应近满分）；**覆盖四级 diff 所有边界**

**Arm A 收尾（加固 #8）**：Week 2–3 已开始标注的 ~50 条开放题，本周完成审查并接入 `score.py`。MVP 至少 30 条。

**验证门**：标注集逐条准确率达标；DIFF_POLICY 边界测试全过；offline 跑通样例。

---

## Week 5 — 评分器 + 审计报告 + Arm B 陷阱集

**目标**：出第一张排行榜 + 审计报告示例（lawyer 一看就懂）。

**交付物**：
- `benchmark/arm_b.json` — ~20 陷阱，分 6 类。**隐藏子集 `arm_b_hidden.json` 加密入库（如 AES + CI secret），repo 仅见密文 blob，CI 解密后跑分但不对外公开原题**（加固 #4，防厂商扒 repo）
  - B1 废止条文（问新公司法已取代的旧条款）
  - B2 虚构法释号（题干种"法释〔2025〕99号"）
  - B3 虚构指导案例号（问"指导案例第200号"，实际只到 40+）
  - B4 内容错引（复述《民法典》第584条与 KB diff）
  - B5 时间错位（民法典施行前终审案却引民法典）
  - B6 虚构法院（引不存在的"北京第四中级知识产权法院"）
- `benchmark/score.py`：
  - 指标：法条引注幻觉率(HR 硬) / 法条内容幻觉率(headline) / 废止误用率 / 指导案例幻觉率 / 案号结构异常率(软) / **不可验证率(透明)**
  - 分领域 HR：民 / 刑 / 行政 / **税** / **知产**（你的三证红利）
  - bootstrap 置信区间（可选 DeLong/McNemar 显著性）
- `benchmark/report.py`：严格按**真实审计报告结构**输出（加固 #5）：`检查目的 / 检查范围 / 检查依据 / 检查方法 / 检查发现 / 结论与建议`，每模型一份。Week 5 前先找一份真实审计报告做模板。
- `results/sample_leaderboard.csv` + `results/sample_audit_report.md`（offline 样例）
- `tests/test_score.py`：已知 ground-truth 样例算分正确

**验证门**：
```
python -S -m benchmark.run --demo    # 端到端出榜 + 报告
python -S -m unittest discover        # CI 绿
```

---

## Week 6 — 包装 / 发布 / live 接入 / 运营

**目标**：clone 即跑、可上 GitHub、形成作品集硬通货。

**交付物**：
- README：30 秒跑通（offline 默认）、中英双语、诚实边界声明（不宣称案例存在性核验；KB 有时效；unverifiable 率如实报告）
- `ROADMAP.md`：Phase 2 众筹全量覆盖 + 税法/知产专项子基准（你的独占领域）+ **Web UI（Streamlit/Gradio）列为 Phase 2**（加固 #6：MVP 核心用户是技术人，clone 后命令行跑即可，UI 分散精力）
- `models/adapters.py` live 模式：智谱 GLM-4 / 通义千问-Max / DeepSeek-Chat 接 API（key 走 env，**默认离线**）
- Tag `v0.1.0`，推 GitHub，LegalTech 社群发布
- `tests/test_clean_container.py` 或 CI：模拟 clone + `python -S` 干净环境出榜（零 pip）

**验证门**：干净容器 clone 即出榜 + 报告（零 pip、零网络）。

---

## 跨周风险与依赖

1. **抽取召回是全局瓶颈**（Week 3）：召回不足 → 低估 HR。改用"正则+归一化+疑点启发式+公开 audit"替代沉默低估；LLM 兜底仅 live 可选；标注集门必须达标。
2. **KB 录入错误是可信度命门**（Week 2）：一条录错 = 错扣模型帽子。用 `build_statute.py` 复制粘贴流水线 + `test_kb_integrity.py` 全量硬门（content 非空/revision_of 有效/时间窗无重叠）兜底，抽样 10 条人工比对作最终防线。
3. **内容 diff 不可复现**（Week 4）：先写 `DIFF_POLICY.md` 量化四级边界，否则不同评测者判级不一致 → 基准失效。
4. **Arm B 防作弊**（Week 5）：隐藏子集加密入库、CI 解密跑分不公开原题；社区贡献探针可公开"类型"不公开"实例"。
5. **live 成本/限流**（Week 6，历史设计）：当前版本未实现 `--live`；真实榜单靠用户/厂商自己跑模型产出 `answers.jsonl`，本工具离线评分。

## 验证纪律（每周必做）

- 所有测试在 `python -S` 干净环境跑（无全局包、无 pip）。
- 不引入任何非 stdlib 运行时依赖；如需临时扩展（如 live 模式的 LLM SDK），放进 `optional-dependencies`，默认离线零依赖。
- 每周结束前 `git commit` 一个可 clone 即跑的状态。
