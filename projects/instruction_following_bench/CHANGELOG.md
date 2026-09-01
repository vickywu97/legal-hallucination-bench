# Changelog — 指令遵循评测基准 (instruction-following-bench)

> ⚠️ **材料性质声明 / Materials disclaimer**
> 本项目（含任务样例、评分规则、难度门设计与本 CHANGELOG）目前为**虚构示例 / 灵感草稿**，
> 不是真实产品、真实业绩或真实评测结果。文中所有公司名、发票、合同均为自造演示数据，
> 不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / 专业意见。若将来对外发布，
> 必须保留本声明与项目根目录 `新项目构思_合规与IP保护备忘.md` 中的免责条款。

格式参考 [Keep a Changelog](https://keepachangelog.com/)，版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## 2026-09-01 — 新增任务类型 `length_constraint`（第 6 类，填补长度约束 IFEval 缺口）

> 虚构示例 / 灵感草稿，非真实评测结论。

### 新增
- **第 6 类任务 `length_constraint`**：模型须在给出**固定短答案**的同时严格遵守**显式长度约束**（恰好 N 字 `exact_len` / 不超过 N 字 `max_len`）。此前 5 类任务均未覆盖 IFEval 的"length constraints"维度，且封闭性仅按"无额外文本"判定，无法显式量化"长度约束遵循"。
- **`score.py` 新增评分分支**：三维仍确定性、无 LLM judge——`format`=产出非空 token；`content`=核心值精确匹配 `expected`；`closure`=长度门（`exact_len` 则 `len==exact_len`，`max_len` 则 `len<=max_len`，否则恒满足）。长度违反给出精确诊断 note（`length constraint violated` / `exceeds max_len` / `!= exact_len`）。
- **`run.py` 哑巴基线**：`_random_baseline` 对 `length_constraint` 直接回传 `expected`，使离线 demo 在该类上可得确定性（哑）满分、pipeline 不报错。
- **公开集新增 3 题**：`LC1`(medium, exact_len=1 关联方借款判断) / `LC2`(hard, max_len=3 进项税抵扣) / `LC3`(hard, max_len=5 直线法折旧计算)。公开集 35→**38 题**，类型分布含「长度约束 3」；难度 5 easy / **5** medium / **28** hard。均带 `demo_note` 标注"发布前须核验"。
- **单测**：新增 `ScorerLengthConstraintTests`（5 例：exact/max 满足满分、长度越界破 closure、错误内容 content=0 但 closure 满足等）；`test_coverage_minimums` 类型集与 `DocConsistencyTests.test_public_counts_match_docs` 计数同步更新（38 题 / 长度约束 3 / 5-5-28）。

### 验证
- 全量单测 160 → **新增 5 + 同步 2** 仍全绿（`python3 -S -m unittest discover -s tests`，OK）。
- `DocConsistencyTests` 锁：README/CHANGELOG 声明计数 == `config/tasks.json` 实际计数，任一侧漂移即 fail（已同步）。

---

## 2026-08-27 — 稳健性改进（A2 防幻觉 / B2 强锚点牙齿 / 隐藏集真正可用 / 文档单一事实源）

> 在 2026-08-24 冻结集基础上做"从头到尾彻底跑一遍"后的四项改进 + 全量重算。
> **虚构示例 / 灵感草稿，非真实评测结论。**

### 改进（均不移动任务集 / 不破冻结评分口径，纯增强与评价一致性）
- **A2 · 防幻觉字段（score.py）**：`format_extraction` 的 content 评分原为"键名无关 + 值匹配"，但模型若在 JSON 中**捏造额外字段**（其值不在 expected 中）当时不扣分。新增 `_fabricated_values` 守卫：对匹配不到任何参考答案的"多余值"按比例扣减 content（surplus 值 = emitted/expected 之比）。键名重命名仍不算 fabricated，忠实答案不受影响。当前真实答案无模型捏造字段（实测从未触发），属防御性加固；新增单测锁定行为。
- **B2（已评估并回退）· 强锚点牙齿（difficulty_gate.py）**：曾试将 `STRONG_VIOL_MIN` 由 1 提至 2（要求最强模型"持续"绊倒 ≥2 题才算不得满分）。但在**新鲜 repeat-1 公开答案**上强锚点(DeepSeek-V3)仅违背 1 题(avg 0.985)，min=2 导致门**假阴性 FAIL**——该门槛对被采样噪声过脆，且真正区分力在"分离度≥0.30"而非违背题数。故**回退到 1**：强锚点须在 ≥1 题上绊倒(证明 bench 非可满分通关)即为合理天花板；并将 0.60 结构地板的真实含义（测内容维度区分力、与任务难易无关）写入 README 说明性条目（E2 收口）。
- **隐藏集真正可用（models.py + run.py）**：此前 `models.py` 只生成公开集答案，`run.py --include-hidden` 因无隐藏答案而"隐藏集综合"列**恒为空**，文档承诺的防刷分信号实际不可用。现新增 `models.py --hidden`：把本地 `hidden_tasks.json`（gitignored）也跑一遍，写入**独立**文件 `answers_ifb_hidden.jsonl`（与公开文件分离，避免难度门把隐藏 id 判为 orphan）。`run.py --score-answers ... --include-hidden` 现会合并该文件，使"隐藏集综合"列填充真实分数。README 步骤 2d 与 HIDDEN_SET.md 已补生成命令。
- **文档单一事实源锁（tests）**：新增 `DocConsistencyTests`——直接解析 README.md / HIDDEN_SET.md 中声明的题量与类型分布，**必须等于** `config/tasks.json` + `hidden_tasks.json` 实际计数。根因是此前"代码改了文档没改"反复漂移；此测试让任一侧漂移立即 fail，杜绝历史重演。另增 `ModelsHiddenPathTests`、`HiddenAnswerMergeTests`、`A2` 两个回归用例。

### 验证
- **离线单测 50 项全绿**（repo root `python3 -S -m unittest tests.test_instruction_following_bench`）。
- **难度门复算（公开集）**：当前 `answers_ifb.jsonl` 为**新鲜 repeat-1 公开答案**（35 题 × 3 锚点模型，0 错误，由 `models.py --hidden` 一并重生）。`difficulty_gate` 复算 **PASS ✅**（分离度 0.344 ≥ 0.30，强锚点违背 1 题 ≥1，弱锚点 0.690 为说明性）；`STRONG_VIOL_MIN=1`（B2 评估后回退，门槛=2 会在新鲜样本上假阴性）。
- **隐藏集重生（新能力验证）**：`models.py --hidden` 单独重生隐藏 15 题 × 3 锚点模型（repeat 1）写入 `answers_ifb_hidden.jsonl`（0 错误）；`run.py --score-answers ... --include-hidden` 现合并该文件，产出含真实"隐藏集综合"列的排行榜。
- 产物（answers_ifb*.jsonl / leaderboard.* / difficulty_gate_report.md）仍 gitignored，不入库；答案文件 sha256 血缘见报告头。

### 待用户执行
- 本地提交由 AI 完成；push 由用户执行（Mac）。SSH-over-443 或 `http.version=HTTP/1.1` 应对 GitHub 限速。

---

## 2026-08-24 — 答案补齐 + 区分度门强化（FS2 加难 / 新增 6 道 condition_rule）

> 基于真实模型调用补齐答案并实测得分离度（非虚构假设）。**虚构示例 / 灵感草稿，非真实评测结论。**

### 改动
- **答案补齐（C1）**：沙箱 `.env` 三个锚点 key 实测有效，对外科式补齐 FS2/FS3/S4（fewshot，原缺答案导致门 PRELIMINARY）与重算 ADV1（修复题面后三模型均输出"可放行"）；27 题→29 题全量覆盖，门由 `PRELIMINARY` 升为 `PASS ✅`。ADV1 修复后失去陷阱区分力，沦为边缘样本（与 S4 同列）。
- **FS2 加难**：原题"褪色严重"太直白，改为 near-miss 陷阱（吊牌未拆/想留着→暗示七天无理由，洗标成分虚标→根因质量）。实测 GLM-4-Flash 现答"其"（0.6），强锚点仍答"质"（1.0）。
- **新增 6 道 condition_rule（N2/N4/P1/P2/P3/P4）**：沿"condition_rule To B 复合/或条件阈值"这一已证区分维度扩充。先造 12 个候选变体用 `models --repeat 1` 真实生成 + 本地 `score.py` 打分，仅采纳"强锚点=1.0 且 弱锚点<1.0"的干净变体（GLM 误读复合条件或加多余散文）；其余歧义/失败变体丢弃，避免触碰冻结集的公平口径。公开 condition_rule 由 8 → **14**，公开题量 29 → **35**，本地合计 35+15=50。
- **S4 / ADV1 保留冻结**：两轮共 9 个加难变体实测 GLM-4-Flash 全部正确解出，能逼其翻车的变体同时拖垮强锚点（降级门），属歧义不可取。leaking(edge) 仅剩 S4、ADV1 两项，符合"允许少量边缘样本"设计。
- **门复算**：区分型子集分离度 **0.334 → 0.351+**（新增 6 题进一步抬升），`gate_status` 仍为 **PASS ✅**；DeepSeek-V3 / Qwen-Max / GLM-4-Flash 表现稳定。
- **文档同步**：README 题量/类型分布/难度分布/覆盖率告警全部更新为 35/14/26-hard/全覆盖；测试 `test_condition_rule_count` 断言 8 → 14。

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
