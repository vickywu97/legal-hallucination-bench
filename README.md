[![CI](https://github.com/vickywu97/legal-hallucination-bench/actions/workflows/ci.yml/badge.svg)](https://github.com/vickywu97/legal-hallucination-bench/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
[![Python](https://img.shields.io/badge/python-3.8%20%7C%203.11%20%7C%203.12-blue.svg)](https://www.python.org)
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
  只有专家签名能把节点翻转为 `verified`。
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

- **离线优先、零运行时依赖**：纯 Python 标准库（`python -S` 可跑），LLM 仅作可选的 `--live` 抽取兜底。
- **确定性**：无随机性（除评分 CI 的固定种子），结果可复现。
- **门禁不可绕过**：来源可信度门禁在 `verify.py` 物理阻断未核验条文参与判分。

---

## 快速开始

```bash
# 0) 仓库零依赖，直接用受管 Python 跑（-S 关闭 site-packages，纯标准库）
python -S -m unittest discover -s tests        # 全量测试（当前 74 用例绿灯）

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

## 方法论文档

- [`docs/DIFF_POLICY.md`](docs/DIFF_POLICY.md) — 二元内容 diff 政策、诊断子类、阈值常量。
- [`docs/METHODOLOGY.md`](docs/METHODOLOGY.md) — 整体方法论（抽取/核验/评分/时序陷阱）。
- [`docs/KB_EXPANSION_PLAN.md`](docs/KB_EXPANSION_PLAN.md) — KB 扩容路线图。

---

## 作者与定位

由具备 **律师 + 税务师 + 专利代理师** 三重资质的法律科技从业者构建，定位为
**AI 法律产品经理 / 法律合规岗**的转型作品集：证明三件事——（1）法律/税/专利领域的真实深度，
（2）能定义并量化 AI 质量（评测/跑分），（3）能交付可离线跑通、零依赖、可复现的产物。

---

## License

MIT（知识库条文文本来自官方公开数据源，仅作评测用途；如需商用请遵循官方版权声明）。
