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

---

## 2026-08-04

### 新增（真实模型排行榜工作流）
- **测试集规格 `questions.json`（15 题）**：覆盖 5 部现行法的四类陷阱——基准 / 时序陷阱 / 硬幻觉 / 张冠李戴（同法 + 跨法）。
  每条含 `domain`、`trap_type`、`difficulty`、`as_of_date`、`target{law_code,article_no}`、`prompt`、`expected`，
  并附 `_meta`（评测范围、失效别名、5 法护栏、陷阱分类、双指标定义）。所有 `target` 条文号均经 KB 核验存在（除 Q8=虚构/超范围、Q12=第9999条两条故意的 `NOT_FOUND` 陷阱）。
- **零依赖采集脚本 `scripts/generate_answers.py`**：纯标准库 `urllib` 调用 7 个便宜/高效模型
  （DeepSeek-V3、DeepSeek-R1 付费旗舰、GLM-4、Qwen-Max、Kimi、GPT-4o-mini、Claude-Haiku），
  `temperature=0` 可复现，从环境变量读 API Key（缺键跳过不报错），写出引擎可直接消费的 `answers.jsonl`
  （`{question_id, model, as_of_date, answer}`）。内置 5 法护栏系统提示词，把"超范围/虚构引用"转化为干净的硬幻觉判定。
- **README 新增「真实模型排行榜」章节**：目标、15 题陷阱表、双指标 HVI（引注幻觉率+时序幻觉率）与 CRFI（张冠李戴率）、采集与 `--input` 评分命令、逐题诊断矩阵说明。
- **`.gitignore`**：新增 `answers.jsonl`（个人 API 产物，不入库）。
- **阵容收敛为纯国产 5 模型（2026-08-04 收口）**：`generate_answers.py` 移除 GPT-4o-mini（OpenAI）与 Claude-Haiku（Anthropic），GLM-4 升级为免费的 GLM-4-Flash；最终阵容 = DeepSeek-V3 / DeepSeek-R1（付费旗舰）/ GLM-4-Flash / Qwen-Max / Kimi，全部 OpenAI 兼容协议、总成本≈零；删除脚本内已无用的 Anthropic 分支；`questions.json` 的 `_meta.models` 同步记录阵容。

### 引擎支撑（此前已实现，本版串接）
- `verify.Verification` 新增 `question_id` 字段；`pipeline.audit` 按模型**累加**引注（修复同模型多题被覆盖的 bug）；
  `pipeline.build_report` 新增**逐题诊断矩阵**（Question × Model，✓/✗子类/?/·）。
- 内置 `--offline` SAMPLE 重构为 3 题（Q1/Q3/Q10）× 3 玩具模型，开箱即演示逐题矩阵。

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
