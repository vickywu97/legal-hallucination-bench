[![CI](https://github.com/vickywu97/legal-hallucination-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/vickywu97/legal-hallucination-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-brightgreen.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.11%20%7C%203.12-brightgreen.svg)](https://www.python.org)
# legal-hallucination-bench · 中文法律引注幻觉基准

> **Chinese Legal Citation Hallucination Benchmark** — an offline, expert-verified
> benchmark that scores how faithfully LLMs quote Chinese statute text, with
> zero tolerance for repealed-law citations and a strict binary (verbatim-or-zero)
> content evaluator.

---

## 一句话定位

大模型在法律问答里会**编造条文、张冠李戴、引用已废止的法律**。本项目用一个
**专家逐条核验的知识库** + **100% 精确的二元判定引擎** + **零容忍的旧法陷阱**，
把"法条引用幻觉"量化成可复现的跑分（HR / 排行榜），而不是靠主观感受。

- ✅ **专家核验知识库**：每条法条都带 `flk.npc.gov.cn` 官方来源 + 人工签名台账，**100% verified、100% 现行法**。
- ✅ **100% 精确二元评测**：逐字一致 = 1.0 分，否则 = 0 分。没有"差不多""部分分"。
- ✅ **零容忍旧法陷阱**：10 部已废止法律的旧名（旧公司法/合同法/物权法等）被单列捕获，模型在废止日后引用即判时序幻觉。

---

## 为什么需要它

法律文本有强约束力。模型常见的三类失效：

| 失效类型 | 例子 | 本项目如何抓 |
| --- | --- | --- |
| **张冠李戴**（引错条文） | 引《刑法》第232条却填了第234条文本 | `MISATTRIBUTED → FABRICATED / 0.0` |
| ** paraphrasing 幻觉** | 漏掉关键但书（如"情节较轻的，处三年以上十年以下有期徒刑"） | 非逐字即 `PARTIAL → FABRICATED / 0.0` |
| **时序幻觉**（引用废止法） | 2025 年还引《合同法》《旧公司法》 | `TEMPORAL_DEPRECATED / 0.0` |

现有通用评测要么不校验法条原文，要么给"部分分"掩盖实质性偏差。本项目用**二元硬门禁**
让每一次细微偏差都现形——这正是法律场景不可妥协的精度要求。

---

## 三大核心亮点（作品集硬通货）

### 1. 专家核验知识库（Expert-Verified KB）
- 条文**只从官方法律法规数据库 `flk.npc.gov.cn` 粘贴**，绝不停靠模型生成。
- `SEED`（LLM 草稿脚手架，默认 `unverified`）与 `verifications.json`（人类签名台账）**物理分离**：
  每条文均由作者本人（**Vicky Wu，律师 / 税务师 / 专利代理师**）逐条对照官方源具名核验，
  `verified_by` 字段记为具名签名，只有该签名能把节点翻转为 `verified`。
- `verify_kb.py` 走查工具 + `test_kb_integrity` 双重守卫，保证 **零 `unverified` 节点进入判分面**。
- KB 纯现行法：失效法名**不进 KB**，只在代码级 `DEPRECATED_LAW_NAMES` 单一真相源登记（见 §4）。

### 2. 100% 精确二元评测（Binary Content Eval）
- 候选文本与已核验基准做**归一化逐字比对**：`N(cand) == N(gt)` 才判 `EXACT (1.0)`，
  其余一律 `FABRICATED (0.0)`。
- `PARTIAL / TRUNCATED / MISATTRIBUTED / FABRICATED_GENERIC` 仅作为**诊断子类**保留（帮助归因），
  **得分恒为 0**——法律上没有"差不多"。
- 评分面永远只用**最新已核验版本**；`UNVERIFIED_GT` 门禁物理阻断用未核验条文当 ground truth。

### 3. 零容忍旧法陷阱（Repealed-Law Trap, Single Source of Truth）
- 10 部已废止法律（旧公司法 + 合同法/民法总则/侵权责任法/物权法/担保法/婚姻法/继承法/收养法/民法通则）
  统一登记在 `benchmark/extract.DEPRECATED_LAW_NAMES`（law_code + 废止日）。
- 提取器按名称**最长优先**匹配，确保"旧公司法"逐字命中而非被"公司法"子串吞掉（防假阴性）。
- 模型即便把旧法条文**一字不差**地复述成现行法内容，仍判 `TEMPORAL_DEPRECATED`——零误判、零漏判。

---

## 架构与设计原则

```
模型答案 (text)
   │  benchmark/extract.py      法定引注抽取（含失效法名陷阱标记）
   ▼
逐条引注 Citation
   │  benchmark/verify.py       内容 diff + 时序/来源门禁
   ▼
Verification (verdict / category / diff_level / score / candidate / ground_truth)
   │  benchmark/score.py        幻觉率 HR + 分域 HR + bootstrap CI
   ▼
审计报告 + 排行榜  (benchmark/reports/)
```

- **离线优先、零运行时依赖**：纯 Python 标准库（`python -S` 可跑）。**模型无关**——任何模型只要产出 `answers.jsonl`（每条含 `model` / `as_of_date` / `answer`），本工具即离线评分；不内置任何 LLM 调用。
- **确定性**：无随机性（除评分 CI 的固定种子），结果可复现。
- **门禁不可绕过**：来源可信度门禁在 `verify.py` 物理阻断未核验条文参与判分。

---

## 快速开始

```bash
# 0) 仓库零依赖，直接用受管 Python 跑（-S 关闭 site-packages，纯标准库）
python -S -m unittest discover -s tests        # 全量测试（当前 83 用例绿灯）

# 1) 开箱即用的离线评测（内置 good/bad/partial 三个玩具模型）
python -S -m benchmark.run --offline

# 2) 内容 diff 引擎演示（二元判定：逐字=1.0 / 否则=0、时序陷阱）
python -S -m benchmark.run --verify-demo

# 3) 专家标注 → 严格内容级评测闭环
#    3a. 准备模型答案 answers.jsonl（每行 {"model","as_of_date","answer"}）
#    3b. 生成标注骨架（含启发式候选 + 基准预览）
python -S -m benchmark.annotate --input answers.jsonl --output candidates.jsonl
#    3c. 专家编辑 candidates.jsonl 的 "candidates" 值（隔离模型真实引文）
#    3d. 严格评测
python -S -m benchmark.run --input answers.jsonl --candidates candidates.jsonl
# 若已 `pip install -e .`，上述命令可简写为 `lhb`（如 `lhb --offline` / `lhb --verify-demo`）
```

`demo/` 目录内置一套可复现的端到端示例（见下）。

---

## 评测流水线字段

每条 `Verification` 输出：`citation_raw`、`verdict`（OK / HALLUCINATION / UNVERIFIABLE）、
`category`（EXACT / PARTIAL / MISATTRIBUTED / TEMPORAL_DEPRECATED / …）、`diff_level`（EXACT / FABRICATED）、
`score`（1.0 / 0.0）、`candidate`（模型输出）、`ground_truth`（官方原文）。
审计报告 `audit_<model>.md` 含"逐条对照"段，可直接当**证据**用。

---

## 当前规模与规划

| 指标 | 现状 (v1.0) | 规划 (v2.0) |
| --- | --- | --- |
| 法律部数 | 5（民法典/公司法/刑法/专利法/税收征管法） | 15–20 |
| 条文节点 | 99（100% verified） | 700+ |
| 覆盖域 | civil / criminal / tax / ip | + admin / 程序法 |
| 失效法陷阱 | 10 部（单源） | 10 部（持续维护） |

扩容规划见 [`docs/KB_EXPANSION_PLAN.md`](docs/KB_EXPANSION_PLAN.md)：优先补强**实体税法**
（增值税法/企业所得税法/个人所得税法）与**知产**纵深——这正是最稀缺的差异化覆盖。

---

## 端到端示例（demo/）

`demo/` 内含一套可复现的"专家标注 → 严格评测"闭环，亲手验证三件事：

1. **标注价值**：启发式窗口会吞入尾部散文，把满分答案**误判**为幻觉；专家标注隔离出纯逐字引文后，假阳性消失（HR_content 100% → 0%）。
2. **细微偏差被抓**：漏掉一个但书分句 → `PARTIAL/FABRICATED 0.0`。
3. **张冠李戴被抓**：引 A 条填 B 条文本 → `MISATTRIBUTED/FABRICATED 0.0`。

```bash
python -S demo/gen_answers.py     # 生成 answers.jsonl + 专家版 candidates
python -S -m benchmark.annotate --input demo/answers.jsonl --output demo/candidates.raw.jsonl
python -S demo/run_eval.py        # 启发式 vs 严格 双跑对比，落到 demo/reports_*/
```

---

## 真实模型排行榜（Real-Model Leaderboard）

> **目的**：用无可辩驳的硬核验数据证明——主流法律 AI 模型在看似最基础的"引用法条"
> 任务上，依然会犯严重、危险的错误。测试集是一份严谨的法律交叉审查备忘录：
> 有体系、有陷阱、有对照、无死角。

### 1. 测试集 `questions.json`（15 题）

覆盖 5 部现行法，四类陷阱（详见 `questions.json` 的 `_meta.trap_taxonomy`）：

| 陷阱类别 | 含义 | 引擎判定 | 代表题 |
| --- | --- | --- | --- |
| **基准** | 正确条文 + 逐字原文（应得满分） | `OK / EXACT` | Q1 民法典584、Q2 刑法232 |
| **时序陷阱** | 引用已废止法律**名称** | `TEMPORAL_DEPRECATED` | Q3 旧公司法13→新10、Q7 合同法113（2021 废止） |
| **新法序号未更新** | 2024 新《公司法》重排条文序号，仍引旧序号 | `NOT_FOUND` | Q4 担保旧16→新15 |
| **硬幻觉** | 引用不存在的法律/法条号 | `NOT_FOUND` | Q8 虚构法、Q12 第9999条 |
| **张冠李戴** | 条号对、内容错（同法/跨法） | `MISATTRIBUTED` | Q5/Q9/Q10/Q13/Q14/Q15 |

`questions.json` 只作为**测试设计规格**与采集脚本的输入；评测引擎并不读取它，
所有判定都只来自模型答案文本本身（因此结论无可辩驳）。

### 2. 双指标评测（HVI + CRFI）

- **HVI（引注幻觉率）** = `hr_statutory`：硬引注中 `NOT_FOUND`（条文不存在）或
  `TEMPORAL_DEPRECATED`（引用已废止法律）的占比。**已内含时效陷阱**，不要求逐字——
  是对模型最宽容、也最无可辩驳的尺度。
- **时序幻觉率** = `rate_deprecated`：上述 HVI 中"引用已废止法律"的子项（单列示警）。
- **CRFI（内容级吹哨指标）** = 张冠李戴率（同法/跨法 `MISATTRIBUTED` 占已核验引注之比）
  ——专门暴露最危险的错误：**条号伪装正确、内容实为别条**。

### 3. 采集真实模型答案（零依赖脚本）

`scripts/generate_answers.py` 纯标准库（`urllib`）调用 5 个**纯国产**便宜/高效模型，
`temperature=0` 保证可复现，写入 `answers.jsonl`：

```bash
# 设置 API Key（均为国产平台；缺哪个就跳过哪个模型，不报错）
export DEEPSEEK_API_KEY=... ZHIPU_API_KEY=... DASHSCOPE_API_KEY=... MOONSHOT_API_KEY=...

# 跑全部 5 个模型 × 15 题（也可 --models / --only 指定子集）
python -S scripts/generate_answers.py --out answers.jsonl

# 内置 5 个纯国产模型：DeepSeek-V3、DeepSeek-R1(付费旗舰)、GLM-4-Flash(免费)、
#                      Qwen-Max、Kimi（全部 OpenAI 兼容协议，总成本≈零）
```

**关键护栏**：系统提示词强制模型"仅可引用 5 部现行法；超出范围或虚构的法律一律说明无法回答"。
这把"引用范围外法律"从"不公平罚分"转化为"违背明确指令 + 硬幻觉（NOT_FOUND）"，
使排行榜结论经得起质疑。

### 4. 离线评分（同一条引擎）

```bash
python -S -m benchmark.run --offline --input answers.jsonl
```

产出 `benchmark/reports/`：每模型 `audit_<model>.md` + `leaderboard.md`
（含**逐题诊断矩阵** Question × Model，一眼看出"哪个模型在哪题翻车"）。

> 注：本基准**仅覆盖 5 部法律**（`questions.json` 的 `_meta.in_scope_laws`）。
> 超出这 5 部的真实法律不在评测范围内——护栏已通过系统提示词约束模型不引用它们。

### 5. 实测结果（Real-Model Results，2026-08-05 采集）

15 题 × 4 个国产模型 = 60 条有效回答（Kimi 因接口 400 暂缺，见下）。评分完全离线、零依赖、可复现。

| 排名 | 模型 | 引注幻觉率 HVI | 内容级幻觉率 | 张冠李戴率 CRFI | 时序幻觉率 | 引注数 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | DeepSeek-R1（付费旗舰） | **36.8%** | 100% | 0% | 5.3% | 19 |
| 2 | GLM-4-Flash（免费） | 45.0% | 100% | 0% | 0% | 20 |
| 3 | Qwen-Max（阿里云主力） | 47.1% | 100% | 0% | 0% | 17 |
| 4 | DeepSeek-V3（免费基础版） | 60.0% | 100% | 0% | 0% | 20 |
| 5 | Kimi（无数据） | — | — | — | — | 0 |

**核心结论**：即使在最宽容的 HVI 尺度下（只查"条文是否存在 / 是否废止"，不要求逐字），
表现最好的付费旗舰 DeepSeek-R1 也有 **36.8%** 的引注是幻觉；完全免费的 GLM-4-Flash（45.0%）
反而优于付费的 Qwen-Max（47.1%）。这意味着**主流法律 AI 在"引用法条"这一基础动作上可靠性堪忧**。

**关键发现（逐题诊断矩阵印证）**：
- **内容级幻觉率全员 100%**：4 个模型没有任何一条逐字复述法条原文——真实模型做不到精确引用，全部概括/改写。
- **张冠李戴率(CRFI) 全员 0%**：受限于 KB 仅 101 节点，未触发"条号对、内容错"的精准诊断；这是覆盖率问题，非模型干净。
- **时序幻觉仅 R1 触发（5.3%）**：R1 在 Q7 引用了已废止的《合同法》第113条（合同法 2021 已废止，Q7 题干已警示）。
- **Q4 暴露"新法序号盲区"**：4 模型全部引用旧《公司法》第16条（公司对外担保），而 2024 新法已移至第15条 → 全员 `NOT_FOUND`。模型锚定 2024 年前的法条序号。
- **Q8 全员 `NOT_FOUND`**：虚构法律（"中华人民共和国虚拟法"）无一被识破。
- **Q9 已修正为公平陷阱**：法人人格否认在新《公司法》为第23条（旧法第20条）；正确引用新序号的模型不再被误判，引用旧序号者仍以 `NOT_FOUND` 计（与 Q4 逻辑一致）。
- **Q12 仅 DeepSeek-V3 上钩**：仅 V3 引用了不存在的"第9999条"，其余模型未引用该条。

> **Kimi 状态**：采集脚本已改为 `kimi-k2.6`，但月之暗面接口返回 HTTP 400（请求格式问题，非鉴权），
> 15 题全失败，故排行榜将其列为"无数据"置于末位，不影响上述 4 模型结论。修复适配器后可单独 `--resume` 补跑。

---

## 方法论文档

- [`docs/DIFF_POLICY.md`](docs/DIFF_POLICY.md) — 二元内容 diff 政策、诊断子类、阈值常量。
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — 整体方法论（抽取/核验/评分/时序陷阱）。
- [`docs/KB_EXPANSION_PLAN.md`](docs/KB_EXPANSION_PLAN.md) — KB 扩容路线图。
- [`CHANGELOG.md`](CHANGELOG.md) — 版本变更记录。
- 历史设计文档（早期 MVP 设计、六周计划、核验报告）已归档至 [`archive/`](archive/)，供追溯，不再反映当前设计。

---

## 作者与定位

由具备 **律师 + 税务师 + 专利代理师** 三重资质的法律科技从业者构建，定位为
**AI 法律产品经理 / 法律合规岗**的转型作品集：证明三件事——（1）法律/税/专利领域的真实深度，
（2）能定义并量化 AI 质量（评测/跑分），（3）能交付可离线跑通、零依赖、可复现的产物。

---

## License

MIT（知识库条文文本来自官方公开数据源，仅作评测用途；如需商用请遵循官方版权声明）。
