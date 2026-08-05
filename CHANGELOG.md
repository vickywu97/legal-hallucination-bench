# Changelog

本项目所有重要变更记录在案。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## 2026-08-04

### 修复 / 改进
- **门禁与健壮性（P0/P1）**：删除空壳模块 `models/adapters.py`、`benchmark/report.py`；
  README 与 `pyproject.toml` 移除「`--live` 真实模型」误导表述（本工具模型无关，由用户外接模型产出 `answers.jsonl`）；
  `loader.normalize_as_of` 容错 `None`/空/`null`/非 ISO 日期；抽取支持引注区间拆分（如「第20-22条」→ 20/21/22）；
  跨法条张冠李戴检测扫描全部法律、阈值 0.90，并对失效法名走时序门禁。
- **死代码清理（P2）**：`extract._law_regex` 改为按 `law_map` 分桶缓存（原为单全局，对测试 fixture 等会静默漏抽取）；
  删除 `score.content_only` 死参数；删除 `loader` 中永不可达的 `amended_by` 重定位分支；
  审计报告新增 bootstrap 95% CI 行；历史文档归档至 `archive/`。
- **核验归属一致性**：`verifications.json` 全部 99 条 `verified_by` 改为具名签名
  「Vicky Wu (律师/税务师/专利代理师)」，官方来源溯源保留进新增 `source` 字段；
  `verify_kb.REPORT_FILE` 指向 `archive/`，避免运行工具时在 `knowledge_base/` 重新生成游离报告。
- 全量测试由 74 增至 **83 用例**（新增区间引注、跨法条、日期容错、空日期鲁棒性测试）。

### 修复（HVI 与内容级指标分离，2026-08-04）
- **指标修正（关键）**：`score.py` 的 `hr_statutory` 原把内容级失败（FABRICATED/PARTIAL/TRUNCATED/MISATTRIBUTED）一并计入引注幻觉率，与文档"HVI 只考核存在性与时效性"自相矛盾，且使 paraphrase 模型的 HVI 齐刷刷 100%、零区分度。现收紧为仅统计 `NOT_FOUND`+`TEMPORAL_DEPRECATED`（分母=全部 hard 引注）；内容失败单列 `hr_content`；内容子集改用 `diff_level` 非空过滤（顺手修掉 `NOT_FOUND` 被误算进 `hr_content` 的旁支 bug）。`_attrs` 补取 `diff_level`。
- SAMPLE 增 Q4 时序陷阱样本（旧公司法第16条→TEMPORAL_DEPRECATED）演示 HVI；同步更新 `test_verify.py`/`test_pipeline.py` 断言。审计/排行榜标签明确标注 HVI。`docs/METHODOLOGY.md` 同步澄清 `hr_statutory`=HVI（不含内容改写）。全量 83 用例绿。

### 新增（真实模型排行榜工作流）
- **测试集规格 `questions.json`（15 题）**：覆盖 5 部现行法的四类陷阱——基准 / 时序陷阱 / 硬幻觉 / 张冠李戴（同法 + 跨法）。
  每条含 `domain`、`trap_type`、`difficulty`、`as_of_date`、`target{law_code,article_no}`、`prompt`、`expected`，
  并附 `_meta`（评测范围、失效别名、5 法护栏、陷阱分类、双指标定义）。所有 `target` 条文号均经 KB 核验存在（除 Q8=虚构/超范围、Q12=第9999条两条故意的 `NOT_FOUND` 陷阱）。
- **零依赖采集脚本 `scripts/generate_answers.py`**：纯标准库 `urllib` 调用 **5 个纯国产模型**
  （DeepSeek-V3、DeepSeek-R1 付费旗舰、GLM-4-Flash、Qwen-Max、Kimi，全部 OpenAI 兼容协议、总成本≈零），
  `temperature=0` 可复现，从环境变量读 API Key（缺键跳过不报错），写出引擎可直接消费的 `answers.jsonl`
  （`{question_id, model, as_of_date, answer}`）。内置 5 法护栏系统提示词，把"超范围/虚构引用"转化为干净的硬幻觉判定。
  （同日收口：初稿含 GPT-4o-mini / Claude-Haiku 海外模型与 GLM-4，后剔除海外模型、GLM-4 升级为免费的 GLM-4-Flash。）
- **README 新增「真实模型排行榜」章节**：目标、15 题陷阱表、双指标 HVI（引注幻觉率+时序幻觉率）与 CRFI（张冠李戴率）、采集与 `--input` 评分命令（仅需 4 个国产平台 key）、逐题诊断矩阵说明。
- **`.gitignore`**：新增 `answers.jsonl`（个人 API 产物，不入库）。

### 引擎支撑（此前已实现，本版串接）
- `verify.Verification` 新增 `question_id` 字段；`pipeline.audit` 按模型**累加**引注（修复同模型多题被覆盖的 bug）；
  `pipeline.build_report` 新增**逐题诊断矩阵**（Question × Model，✓/✗子类/?/·）。
- 内置 `--offline` SAMPLE 重构为 3 题（Q1/Q3/Q10）× 3 玩具模型，开箱即演示逐题矩阵。

### 改进（评测严谨性收口，2026-08-04）
- **CRFI 指标落地**：`score.py` 计算 `crfi`（内容级 diff 子集中 `MISATTRIBUTED` 占比，专抓「条号对、内容错」）；`pipeline.py` 审计报告与排行榜新增「张冠李戴率(CRFI)」列，`_CAT_ABBR` 增 `MA=张冠李戴`；`test_pipeline.py`/`test_verify.py` 补 CRFI 断言。全量 83 用例绿。
- **10 题改为「逐字引用」提示**：Q1/Q2/Q5/Q6/Q9/Q10/Q11/Q13/Q14/Q15 在 prompt 明确要求逐字引用法条原文，与绝对二元 DIFF_POLICY（逐字一致才 EXACT，否则 0 分）对齐；时序/硬幻觉类陷阱题（Q3/Q4/Q7/Q8/Q12）保持原样。
- **修复内置 SAMPLE Q10 串题**：`run.py` `_SAMPLE_RECORDS` 的 Q10 块原误测刑法232/234，改为正确测试专利法65（gt65 正确 EXACT / gt69 张冠李戴 MISATTRIBUTED / 截断 gt65 FABRICATED）。
- **KB 增补民法典第1182条（100 节点）**：Q15 为跨法张冠李戴（专利法65 vs 民法典1182），原 KB 缺 1182 会导致跨法检测只判通用 FABRICATED、抓不到 MISATTRIBUTED。现补 SEED + verifications.json 具名签名 + 重建 statutes.jsonl（100 verified / 0 unverified）；`test_kb_coverage` 的 `MIN_TOTAL` 99→100。

---

## 2026-08-05

### 修复（评测公平性 + 排行榜可信度）
- **Q9 公平性 bug 修复（关键）**：原 Q9 目标写《公司法》第20条，但 2024 新《公司法》已把"法人人格否认"移至**第23条**；KB 旧节点存的是旧序号第20条，导致正确引用新法第23条的模型反而被判 `NOT_FOUND`（引擎 note 自标 "relocated article"），与 Q4 用新序号第15条自相矛盾。修复：KB 新增 `COMPANY_LAW 第23条` 节点（新法 3 款原文，含横向否认与一人公司）+ verifications.json 具名签名；Q9 目标与 `correct_citation` 改为第23条；旧第20条节点 notes 修正为"股东权利滥用（新法第20条）"。KB 增至 **101 节点 / 101 verified**；`test_kb_coverage` 的 `MIN_NODES[COMPANY_LAW]` 15→16、`MIN_TOTAL` 100→101。修复后 R1 的 HVI 由 42.1% 降至 **36.8%**（正确引用第23条者不再被误罚）。
- **排行榜排名修复**：`_write_leaderboard` 原按 HVI 升序但未排除 `n_citations==0`，导致 Kimi（0 引注、HTTP 400 全失败）被排到第 1。改为 `n_citations==0` 的模型置末位并标注"无数据"；逐题矩阵模型排序同步修正。

### 真实模型排行榜（4 国产模型，2026-08-05 采集）
- HVI：R1 **36.8%** / GLM-4-Flash 45.0% / Qwen-Max 47.1% / DeepSeek-V3 60.0%（全员内容级幻觉率 100%、CRFI 0%；仅 R1 触发时序幻觉 5.3%，在 Q7 引已废止《合同法》第113条）。
- README「真实模型排行榜」章节增补：纠错的陷阱分类表（Q4 归为"新法序号未更新"非时序陷阱）、修正 HVI 定义（已内含时效陷阱，非 `hr_statutory + rate_deprecated` 双重计数）、新增「§5 实测结果」含排行榜表 + 8 条关键发现 + Kimi 400 状态说明。

---

## 2026-08-03

### 新增
- **初始发布 v1.0**：离线优先、零运行时依赖（`python -S` 可跑）的法律法条幻觉评测基准。
  - 抽取引擎 `benchmark/extract.py`、内容级二元 diff 与门禁 `benchmark/verify.py`、
    幻觉率聚合与 bootstrap CI `benchmark/score.py`、端到端管线 `benchmark/pipeline.py`。
  - 专家核验知识库 KB：99 节点 / 99 verified / 0 unverified，纯现行法；
    `DEPRECATED_LAW_NAMES` 单一真相源登记 10 部失效法名陷阱。
  - `--offline` / `--verify-demo` 开箱演示；`demo/` 严格内容级评测闭环。
  - GitHub Actions CI（py 3.8/3.11/3.12，离线跑测试与 `--offline`）。
  - 文档：`README.md`、`docs/DIFF_POLICY.md`、`docs/METHODOLOGY.md`、`docs/KB_EXPANSION_PLAN.md`、`CONTRIBUTING.md`。

### 文档 / CI
- README 增加 CI / Python / License 徽章（三绿布局）。
- CI actions 升级至 v7（Node 24），消除 Node 20 弃用告警；`pip` 升级至最新。
