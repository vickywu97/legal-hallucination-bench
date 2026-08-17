# Changelog — 指令遵循评测基准 (instruction-following-bench)

> ⚠️ **材料性质声明 / Materials disclaimer**
> 本项目（含任务样例、评分规则、难度门设计与本 CHANGELOG）目前为**虚构示例 / 灵感草稿**，
> 不是真实产品、真实业绩或真实评测结果。文中所有公司名、发票、合同均为自造演示数据，
> 不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / 专业意见。若将来对外发布，
> 必须保留本声明与项目根目录 `新项目构思_合规与IP保护备忘.md` 中的免责条款。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## 2026-08-17 — 作品集双轴落地 + 防刷分隐藏集（v2_composite 难度门收口）

> 把作品集从「法律幻觉评测」扩展为「法律幻觉 + 指令遵循质量」**双评测维度**。
> 纯标准库、离线、规则化评分（无 LLM 裁判），28 单测全绿。
> 完整设计细节见**根目录 `CHANGELOG.md`（2026-08-17 条目）**与 `HIDDEN_SET.md`。

### 新增（指令遵循基准 + 难度门）
- **中文企业 To B 封闭指令场景**：覆盖格式提取 / 条件规则 / Few-shot 归类 / 多轮约束四类；
  公开 21 题（hard/medium 标注）+ 隐藏 5 题（`hidden_tasks.json`，**gitignored 不入库**，防刷分）。
- **规则化三维评分（无 LLM 裁判）**：`total = 0.3·format + 0.4·content + 0.3·closure`；
  `multi_turn_constraint` 输出 `allowed` 之外 token → 三维全 0；closure 零容忍（任何 JSON 代码块包裹或多余散文 = 0）。
- **难度门收口（关键设计洞察）**：原"强锚点 ≤0.60 / 弱锚点 ≤0.35"绝对门槛在三维加权评分下**数学上不可达**——
  任何合规结构化输出自带 **0.60 结构地板**（format 1.0 + closure 1.0）。重定义为复合 `v2_composite` 口径：
  弱锚点（GLM-4-Flash）≤ **0.60 结构性地板** + 强弱分离 ≥ **0.30** + 强锚点不得满分（avg<1.0 且 单题违背≥1）。
- **冻结锚点**：强锚点 = max(DeepSeek-V3, Qwen-Max)，弱锚点 = GLM-4-Flash（显式冻结，禁用"跑分最高模型"式漂移定义）。
- **真实数据验证（2026-08-17 复跑，PASS）**：DeepSeek-V3 0.936 / Qwen-Max 0.898 / GLM-4-Flash 0.525；
  弱 gap −0.075（≤0.60 地板）、分离 0.411（≥0.30）、强锚点违背 4（≥1，非满分）→ `gate: PASS`。

### 防刷分隐藏集（anti-gaming）
- 隐藏题放在 `hidden_tasks.json`（项目根），与公开 `config/tasks.json` **物理隔离**，
  **已被 `.gitignore` 忽略，永不随仓库发布**。
- 默认 `run.py` 只加载公开 21 题；`--include-hidden` 才合并隐藏集（本地 21+5=26 题），
  且报告标题旁加 **`[含隐藏集]`** 标记，公开排行榜只展示各模型"隐藏集综合"聚合分，
  **绝不泄露隐藏题的 id 或内容**。机制与自检命令见 `HIDDEN_SET.md`。

### 合规保护
- 材料为虚构 demo，规则型 expected 答案（如预提所得税率、试用期上限）带 `demo_note` 标注"需核验"；
  发布为真实公开基准前须经作者（税务师/律师）逐题核验并做法规版本轴标注。

---

## 2026-08-14 — v0.1 scaffold（初始脚手架）

- 四类任务类型（`format_extraction` / `condition_rule` / `fewshot_classify` / `multi_turn_constraint`）。
- 三维规则化评分骨架（`score.py`）+ 自包含 HTML 排行榜（`report.py`，离线零依赖）。
- 真实模型适配层（`models.py`，stdlib urllib 调国产模型，环境变量读 key；`.env` 被 gitignore）。
- 离线 CLI（`run.py`：`--offline` 哑巴基线 / `--score-answers` 真实评分 / `--include-hidden` 含隐藏集）。
- 初始测试套件（28 单测）覆盖评分、渲染、隐藏集加载降级、CLI 无 key 跳过等。
