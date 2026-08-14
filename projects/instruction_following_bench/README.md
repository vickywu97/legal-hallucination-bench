# 企业封闭指令遵循评测基准 · instruction-following-bench (v0.1 scaffold)

> ⚠️ **材料性质声明 / Materials disclaimer**
> 本项目（含任务样例、定位文档、规则设计与本 README）目前为**虚构示例 / 灵感草稿**，
> 不是真实产品、真实业绩或真实评测结果。文中所有公司名、发票、合同均为自造演示数据，
> 不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / 专业意见。若将来对外发布，
> 必须保留本声明与项目根目录 `新项目构思_合规与IP保护备忘.md` 中的免责条款。

## 一句话定位（与 IFEval 的差异）

面向**中文企业 To B 封闭指令场景**（格式提取 / 条件规则 / Few-shot 归类 / 多轮约束），
带**难度门量化**（模型一 ≤ 35% / 模型二 ≤ 60%）与**指令违背率**（instruction
violation rate）双指标，离线零依赖。区别于 IFEval：聚焦**中文企业真实业务指令**而非
通用指令遵循，且明确引入难度门与可量化的"违背率"而非仅断言准确率。

## 任务类型

| 类型 | 说明 | 输出形态 |
|------|------|----------|
| `format_extraction` | 从非结构化文本抽取指定字段 | 严格 JSON |
| `condition_rule` | 按规则判断并给理由 | 严格 JSON `{eligible: bool, reason: str}` |
| `fewshot_classify` | 给定示例，对新输入分类 | 单个字母标签 |
| `multi_turn_constraint` | 对话中只能回指定 token | 精确匹配 token |

## 评分体系（规则化，无 LLM judge）

每条输出在三个维度上打分，均为**确定性规则**（正则 / 精确匹配），保证离线可复现：

- **格式符合度 (30%)**：输出是否可被解析为目标结构（JSON 字段完整 / 标签合法 / token 合法）。
- **内容正确性 (40%)**：抽取 / 判断 / 分类结果与标准答案逐字段比对。
- **封闭性 (30%)**：是否严格等于期望格式、是否含额外解释性 token（规则检测，不用 LLM 评判）。

`total = 0.3*format + 0.4*content + 0.3*closure`
`instruction_violation_rate = 1 - total`

## 目录结构

```
projects/instruction_following_bench/
├── README.md
├── __init__.py
├── config/tasks.json          # 18 个任务（虚构演示数据，含 difficulty 字段）
├── score.py                   # 规则化评分（无 LLM judge）
├── report.py                  # 生成自包含 HTML 排行榜（离线、零依赖）
├── models.py                  # 真实模型适配层（复用 scripts/generate_answers.py 模式）
├── run.py                     # 离线运行 / 真实答案评分
└── (tests/test_instruction_following_bench.py)   # 见仓库 tests/ 目录
```

## 快速开始

```bash
# 1) 离线 demo：用两个哑巴基线（随机 / 空输出）跑通整条 pipeline
#    同时输出 leaderboard.csv 与 leaderboard.html（DEMO 脚手架，非真实排名）
python -S -m projects.instruction_following_bench.run --offline

# 2) 接真实模型（需设置环境变量 API key，否则该模型被跳过）
export DEEPSEEK_API_KEY=sk-xxx
export ZHIPU_API_KEY=zk-xxx
python -S -m projects.instruction_following_bench.models \
    --out answers_ifb.jsonl          # 真实调用 DeepSeek / GLM / Qwen / Kimi

# 3) 用真实答案产出可复现排行榜（html 带"真实排行榜"横幅）
python -S -m projects.instruction_following_bench.run \
    --score-answers answers_ifb.jsonl
```

> 两种模式都会同时写出 `leaderboard.csv` 与 `leaderboard.html`（单文件自包含，
> 内联 CSS、无外部依赖）。HTML 顶部横幅区分 DEMO / REAL，底部含材料性质声明。

> **保护红线**：`--offline` 的随机/空基线分数**不得**作为真实模型排名对外发布；
> 只有 `--score-answers` 配合真实模型输出才产生可复现的真实排行榜。

## 任务规模与难度门

当前 `config/tasks.json` 含 **18 题**（四类任务各 4–5 题），每题带 `difficulty` 字段
（`easy` / `medium` / `hard`）。难度门量化（"模型一 ≤ 35% / 模型二 ≤ 60%"）需在接真实模型
后，用 DeepSeek-V3 / GLM-4 等实测各题通过率来标定——**离线哑巴基线无法验证难度门**。

> ⚠️ 任务中的规则型 expected 答案（如预提所得税率、试用期上限）仅作**演示设计**，
> 发布为真实公开基准前，须经作者（税务师/律师）逐题核验并做法规版本轴标注，避免
> 因法规变动或不准确导致的专业责任风险。

## 下一步（按优先级，尚未实现）

1. 接入真实模型 API（适配层已就绪，复用 `scripts/generate_answers.py` 的零依赖 REST 模式）。
2. **难度门量化**：用 DeepSeek-V3 / GLM-4 实测验证"模型一≤35% / 模型二≤60%"，回填到各题。
3. ~~输出 HTML 排行榜~~ ✅ 已完成（`report.py`，两种模式均产出 `leaderboard.html`）。
4. 隐藏测试集（防刷分，部分题目不入默认集）。
