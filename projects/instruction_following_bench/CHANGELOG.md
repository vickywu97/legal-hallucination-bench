# Changelog — 指令遵循评测基准 (instruction-following-bench)

> ⚠️ **材料性质声明 / Materials disclaimer**
> 本项目（含任务样例、评分规则、难度门设计与本 CHANGELOG）目前为**虚构示例 / 灵感草稿**，
> 不是真实产品、真实业绩或真实评测结果。文中所有公司名、发票、合同均为自造演示数据，
> 不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / 专业意见。若将来对外发布，
> 必须保留本声明与项目根目录 `新项目构思_合规与IP保护备忘.md` 中的免责条款。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## 2026-08-19 — 彻底复查整改（计数纠偏 / 报告硬化 / ADV1 修复 / 类型补完）

> 基于 2026-08-18 全项目彻底复查报告落地修复。**虚构示例 / 灵感草稿，非真实评测结论。**

### 修复（按优先级）
- **P0 · ADV1 不可解**：题面输入原为"公司内部共享盘"，与规则触发词"仅限内部使用"不匹配，导致 `expected="可放行"` 数学上不可达、三模型全 0.000、陷阱零区分度。现已在题面字面补"（仅限内部使用，不得外发）"，使"可放行"可达、强模型能得 1.0，弱模型误拦仍落 allowed 之外得 0，陷阱恢复。改后须重新跑 `models --repeat 3` + `difficulty_gate` 复算（旧答案仍是修复前快照）。
- **P1 · 难度门报告硬化**：删去硬编码"ADV1=1.000"叙述（旧报告脚注与表格自相矛盾），改为从 `per_task` 数据派生 ADV1 状态；报告头新增**答案血缘**（sha256 / 路径 / 修改时间），杜绝"陈旧报告被当权威"；原"伪影已修复 artifact_tasks=0"恒空话改为数据派生的 flat-floor（齐平 0.60 地板、content 全 0）信号；导入改为 `try 相对 else 扁平`，兼容脚本与模块两种调用。
- **P1 · 文档计数纠偏**：README/CHANGELOG 多处计数漂移统一——公开 **29** 题（格式 13 / 条件 8 / Few-shot 4 / 数值计算 1 / 多轮 3）、隐藏 **15**（TH1–TH15，类型：格式 5 / 条件 5 / 多轮 3 / Few-shot 2）、本地合计 **44**；难度分布修正为 **5 easy / 4 medium / 20 hard**（区分型子集 24）；修正 S4 既"删"又"加"矛盾（删 4 道：S2/T3/M2/T4）；删除过期 "0.806" 引用；更正 ".env 已内置 key" 误导（实为占位符）与 Kimi 已禁用标注。
- **P1 · 生成产物治理**：`difficulty_gate_report.md` 加入 `.gitignore` 并 `git rm --cached` 取消跟踪（本地保留），避免陈旧报告入库显权威。
- **P2 · ADV2 重分类**：ADV2 实为数值复利计算题，误标 `fewshot_classify`；新增 `numeric_compute` 类型（score.py 加数值容错评分分支），tasks.json 改 type，README 类型表补为五类，测试补类型集合与评分用例。
- **P2 · 测试注释**：`hidden ≥ 10` 注释更新为反映当前 15；`range(21)` 注释标明为合成 fixture 计数（真实区分型子集 24）。
- **P3 · 清理**：删除 `config/tasks.json.bak(.bak2)` 本地残留备份（均已被 gitignore）。

### 待用户执行（需真实模型 / push 权限）
- 重跑 `models --repeat 3` 补齐 FS2/FS3/S4 答案并对 ADV1 复算，再重跑 `difficulty_gate` 刷新报告（含新 sha256）。
- 本地提交由 AI 完成，push 由用户执行（Mac）。

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
