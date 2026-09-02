# 企业封闭指令遵循评测基准 · instruction-following-bench (v0.1 scaffold)

> ⚠️ **材料性质声明 / Materials disclaimer**
> 本项目（含任务样例、定位文档、规则设计与本 README）目前为**虚构示例 / 灵感草稿**，
> 不是真实产品、真实业绩或真实评测结果。文中所有公司名、发票、合同均为自造演示数据，
> 不构成对任何真实企业或模型的背书，也不构成税务 / 法律 / 专业意见。若将来对外发布，
> 必须保留本声明与项目根目录 `新项目构思_合规与IP保护备忘.md` 中的免责条款。

## 一句话定位（与 IFEval 的差异）

面向**中文企业 To B 封闭指令场景**（格式提取 / 条件规则 / Few-shot 归类 / 多轮约束 / 数值计算），带**难度门量化**
带**难度门量化**（区分度门 v3_discrimination：区分型子集分离 ≥ 0.30 / 强锚点不得满分；弱锚点 ≤ 0.60 结构地板为说明性参考）与**指令违背率**（instruction
violation rate）双指标，离线零依赖。区别于 IFEval：聚焦**中文企业真实业务指令**而非
通用指令遵循，且明确引入难度门与可量化的"违背率"而非仅断言准确率。（注：原"模型一≤35%/模型二≤60%"的
绝对门槛因三维加权评分自带 0.60 结构地板而在数学上不可达，已先后收口为 **v2_composite 复合门槛**（弱锚点 ≤ 0.60 结构地板、分离 ≥ 0.30、强锚点不得满分），并进一步**重框为区分度门 v3_discrimination**：分离（区分型子集）≥ 0.30 与强锚点不得满分为决定性条件，弱锚点 ≤ 0.60 结构地板降为**说明性**参考（引入 easy 校准题后弱锚点自然升高，属预期，不影响门判定）。当前权威口径以 `difficulty_gate.py` 的 `GATE_SPEC="v3_discrimination"` 常量与最新 `difficulty_gate_report.md`（含答案血缘 sha256）为准。）

## 任务类型

| 类型 | 说明 | 输出形态 |
|------|------|----------|
| `format_extraction` | 从非结构化文本抽取指定字段 | 严格 JSON |
| `condition_rule` | 按规则判断并给理由 | 严格 JSON `{eligible: bool, reason: str}` |
| `fewshot_classify` | 给定示例，对新输入分类 | 单个字母标签 |
| `multi_turn_constraint` | 对话中只能回指定 token | 精确匹配 token |
| `numeric_compute` | 数值计算并只输出结果数字 | 精确数字（数值容错） |
| `length_constraint` | 在给出固定短答案的同时严格遵守显式长度约束（恰好 N 字 / 不超过 N 字） | 固定短值（精确匹配）+ 长度校验 |

> 任务类型原为四类；`numeric_compute` 由 ADV2（复利计算题，原误标为 `fewshot_classify`）在 2026-08-19 整改中补入，使"按类型聚合"的难度分析准确。

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
├── config/tasks.json          # 38 个公开任务（虚构演示数据，含 difficulty 字段；easy/medium/hard 三级）
├── hidden_tasks.json          # ⛨ 隐藏测试集（防刷分，已被 .gitignore 忽略，不随仓库发布）
│                               #   18 个隐藏题（TH1–TH18），与公开集物理隔离，永不提交
├── score.py                   # 规则化评分（无 LLM judge）
├── report.py                  # 生成自包含 HTML 排行榜（离线、零依赖；含隐藏集综合列）
├── models.py                  # 真实模型适配层（复用 scripts/generate_answers.py 模式）
├── run.py                     # 离线运行 / 真实答案评分（支持 --include-hidden）
└── (tests/test_instruction_following_bench.py)   # 见仓库 tests/ 目录
```

## 快速开始

```bash
# 1) 离线 demo：用两个哑巴基线（随机 / 空输出）跑通整条 pipeline
#    同时输出 leaderboard.csv 与 leaderboard.html（DEMO 脚手架，非真实排名）
#    默认只包含公开 tasks.json（38 题），不含任何隐藏题。
python -S -m projects.instruction_following_bench.run --offline

# 1b) 含隐藏集：额外评分 hidden_tasks.json 中的题目（防刷分验证）。
#     HTML 标题旁会出现 "[含隐藏集]" 标记，并多出"隐藏集综合"列，
#     但绝不展示隐藏题的逐题内容（TH1… 不出现）。本地合并为 38+18=56 题。
python -S -m projects.instruction_following_bench.run --offline --include-hidden

# 2) 接真实模型（需设置环境变量 API key；未设置的模型自动跳过，不会中断运行）
#    支持 4 家 OpenAI 兼容国产模型，env 变量名如下：
#      DEEPSEEK_API_KEY   -> DeepSeek-V3 (deepseek-chat)
#      ZHIPU_API_KEY      -> GLM-4-Flash (glm-4-flash)
#      DASHSCOPE_API_KEY  -> Qwen-Max   (qwen-max)
#      （Kimi / Moonshot 已因额度不足在 models.py 中禁用，需充值后取消注释方可启用）
#    ⚠️ .env 仅含占位符 `sk-你的真实key`，须替换为真实 key 后才会被加载（未设置 key 的模型自动跳过，不会中断运行）；本仓库 .env 被 gitignore，不会泄露。
export DEEPSEEK_API_KEY=sk-xxxx
export ZHIPU_API_KEY=zk-xxxx
# 只跑已设 key 的模型；或显式指定子集：--models DeepSeek-V3 GLM-4-Flash
python -S -m projects.instruction_following_bench.models \
    --out answers_ifb.jsonl          # 真实调用已配置 key 的模型

# 2b) 仅先验证 pipeline（不设任何 key 也会干净跳过，写空 jsonl，不报错）
python -S -m projects.instruction_following_bench.models --out answers_ifb.jsonl

# 2c) 重复采样估计稳定性：每 (模型,题) 调用 N 次并保留全部输出，
#     difficulty_gate 报告各模型 mean±std（std 为稳定性带，门按 mean 判定）
python -S -m projects.instruction_following_bench.models \
    --repeat 3 --out answers_ifb.jsonl

# 2d) 同时生成隐藏集答案（让"防刷分"真正可用）：加 --hidden 会把本地
#     hidden_tasks.json（gitignored）也跑一遍，写入 answers_ifb_hidden.jsonl
#     （与公开文件分离、同样 gitignored）。之后 run.py --include-hidden 才能
#     产出真正的"隐藏集综合"列（此前该列因无隐藏答案而恒为空）。
python -S -m projects.instruction_following_bench.models \
    --repeat 3 --out answers_ifb.jsonl --hidden

# 3) 用真实答案产出可复现排行榜（html 带"真实排行榜"横幅）
python -S -m projects.instruction_following_bench.run \
    --score-answers answers_ifb.jsonl
# 3b) 若已用 --hidden 生成隐藏答案，可一并评分（产出"隐藏集综合"列，防刷分信号）
python -S -m projects.instruction_following_bench.run \
    --score-answers answers_ifb.jsonl --include-hidden
```

> 两种模式都会同时写出 `leaderboard.csv` 与 `leaderboard.html`（单文件自包含，
> 内联 CSS、无外部依赖）。HTML 顶部横幅区分 DEMO / REAL，底部含材料性质声明。

> **保护红线**：`--offline` 的随机/空基线分数**不得**作为真实模型排名对外发布；
> 只有 `--score-answers` 配合真实模型输出才产生可复现的真实排行榜。

## 任务规模与难度门

当前 `config/tasks.json` 含 **公开 38 题**（格式提取 13 / 条件规则 14 / Few-shot 4 / 数值计算 1 / 多轮 3 / 长度约束 3），
另有 **隐藏集 18 题**（`hidden_tasks.json`，不随仓库发布），合计本地可评 56 题。
v3 任务集已重设计：format 题强制规范化/派生计算/方向/年份推断、condition 题含反直觉外部知识记忆型（不给出规则），
对抗/约束陷阱题升级为真实难度杠杆；并新增 5 道 **easy 校准题**（E1–E5，纯照抄提取）使难度成梯度。
**P2/P3 已落地**：condition_rule 法律题由 8 道降至 3 道（其余 5 道改写为非法律 To B 规则：审批流路由 / SLA 升级 / 折扣审批 / 库存补货 / 数据导出合规）；Few-shot 由 2 扩至 4（新增 S4/FS2/FS3），ADV2 后由 Few-shot 重分类为数值计算（现公开集 Few-shot 4 / 数值计算 1）；ADV1 加固为语义陷阱（弱模型误将「导出客户名单」判为外发而误拦，零漏分）；隐藏集由 5 扩至 15；排行榜新增 mean±std 稳定性带。**2026-08-24 扩充**：为抬高区分度门分离度，沿「condition_rule To B 规则」这一已证可区分维度新增 6 道 hard 题（N2/N4/P1/P2/P3/P4，均为复合条件/或条件阈值陷阱），公开 condition_rule 由 8 增至 14，公开题量 29→35；S4/ADV1 经实测 GLM-4-Flash 稳健、无干净陷阱，保留冻结为边缘样本。
**难度门已重框为区分度门 v3_discrimination（详见 `difficulty_gate_report.md` 与 `difficulty_gate.py`）**：
- 【决定性】区分型子集（标注 `hard`/`medium` 的题）分离度 = strong_avg − weak_avg ≥ 0.30；
- 【决定性】强锚点不得满分：avg_total < 1.0 且单题违背（total<0.85）≥ 1（最强模型须在≥1题上绊倒，证明 bench 非可被满分通关；真正区分力在"分离度≥0.30"，非此题数）；
- 【说明性】弱锚点 ≤ 0.60 结构地板（0.60 = 0.3·format + 0.3·closure 的合规基础分：任何**格式合规且闭包干净**的输出天然 ≥ 0.60，与任务难易无关；因此该地板测的是**内容维度（0.4 权重）的区分力**，而非"任务整体很难"。引入 easy 校准题后弱锚点升至地板之上是预期，不判定门失败）。
每题带 `difficulty` 字段（`easy` / `medium` / `hard`，当前 5 easy / 5 medium / 28 hard）。难度门量化
需在接真实模型后，用实测各题得分率来标定——**离线哑巴基线无法验证难度门**。

> ⚠️ **答案覆盖状态（可复现性）**：`answers_ifb.jsonl` 由 `models.generate_answers` 真实调用模型生成、每次覆盖写，且已被 gitignore。当前公开 38 题均已补齐真实模型答案（含 2026-08-24 补齐的 FS2/FS3/S4 与新增的 N2/N4/P1/P2/P3/P4），门报告无 `PRELIMINARY` 覆盖率告警。重算方式：`python -S -m projects.instruction_following_bench.models --repeat 3 --out answers_ifb.jsonl` 后重跑 `difficulty_gate.py`。报告头现含答案文件 **sha256 血缘**，请核对报告与答案同源后再引用结论。

> ⚠️ 任务中的规则型 expected 答案（如预提所得税率、试用期上限）仅作**演示设计**，
> 发布为真实公开基准前，须经作者（税务师/律师）逐题核验并做法规版本轴标注，避免
> 因法规变动或不准确导致的专业责任风险。带 `demo_note` 字段的新题已显式标注"需核验"。

## 难度门锚点与评分口径冻结（发布前必读）

为保证每次跑分的门槛**可比、可复现**，以下两项在 `score.py` 中冻结，非经评审不得改动：

1. **锚点模型（"模型一 / 模型二"）绑定固定 id**
   - **模型二（强锚点，不得满分：avg<1.0 且 单题违背≥1）**：固定为当前最强前沿模型，实测取 `DeepSeek-V3` 与 `Qwen-Max`
     （二者得分一致时并列）。注意：强模型本就该遵循指令，此条仅为"不得满分"的合理性天花板，
     门的牙齿在"弱失败 + 分离"，而非压低强模型。
   - **模型一（弱锚点，≤ 0.60 结构地板为说明性参考）**：固定为相对较弱模型，实测取 `GLM-4-Flash`。注意 0.60 是合规结构化输出的**结构地板**（format0.3+closure0.3，任何合规模型天然≥0.60），故"弱≤0.60"在 v2_composite 下对被测模型近乎恒真、区分力极弱；v3_discrimination 将其降为**说明性**展示——引入 easy 校准题后弱锚点升至地板之上是预期，门的牙齿在"分离 + 强非满分"，弱锚点是否≤0.60 不决定门成败。
   - 锚点随模型代际更新，但**每次正式发布必须显式写明所用 id 与版本**，禁止用"跑分最高的模型"
     这种漂移定义，否则门槛不可比。
   - 真实跑分命令见 `difficulty_gate.py` 的 `GATE_SPEC`(=`v3_discrimination`) / `GATE_WEAK_FLOOR`(说明性) / `GATE_SEP_MIN`(区分型子集分离下限) / `DISCRIMINATING_DIFFICULTIES`(参与分离度计算的子集) / `STRONG_VIOL_THRESHOLD` / `STRONG_VIOL_MIN` 常量与报告。

2. **封闭性（closure, 30%）零容忍口径冻结**
   - JSON 类任务：只要模型在目标 JSON **之外**残留任何字符（含 ```` ```json ```` 围栏、
     前后导文字、解释性句子），`closure` 即判 0（见 `score.py` 的 `_closure_broken`）。
   - 标签 / token 类任务：输出必须是**精确**的目标标签 / token，多一个字即判 0。
   - 该口径刻意严格——它测的就是"封闭指令遵循"，不容忍任何自由发挥；改动需评审。

## 下一步（按优先级）

1. ~~接入真实模型 API~~ ✅ 已完成（适配层就绪，Mac 实测 DeepSeek-V3 / GLM-4-Flash / Qwen-Max）。
2. ~~难度门量化~~ ✅ 已完成（见 `difficulty_gate_report.md`，报告头含答案血缘 sha256；当前口径为区分度门 v3_discrimination：分离度 ≥ 0.30 与强锚点不得满分双决定性、弱锚点 ≤ 0.60 结构地板为说明性）。
3. ~~加固（先修伪影 → 删漏分题 → 扩 condition_rule hard）~~ ✅ 已完成：
   - 修格式题伪影：5 道 `format_extraction` 的 `expected` 改为中文键名 + 照原文值，消除齐平 0.3 伪影。
   - 删 4 道漏分题（S2/T3/M2/T4，全模型 ≥0.9）；原漏分清单中的 S4 在 Few-shot 扩类时重新纳入（见下条），故不计入删除。
   - 扩 8 道 `condition_rule` 真·hard（CR1–CR8，自含规则、带 `demo_note` 需核验）。
   - 当前 38 题（含 5 道 easy 校准题）；难度门已重框为区分度门 v3_discrimination（权威数字见 `difficulty_gate_report.md`，区分度门 + 强非满分双决定性、弱锚点说明性）；P2/P3 已落地（condition 法律题降至 3、fewshot 4 + 数值计算 1（ADV2 重分类）、ADV1 零漏分、隐藏集扩至 18、排行榜误差棒）。
4. ~~输出 HTML 排行榜~~ ✅ 已完成（`report.py`，两种模式均产出 `leaderboard.html`）。
5. ~~隐藏测试集~~ ✅ 已完成（防刷分机制）：
   - 隐藏题放在 `hidden_tasks.json`（项目根），与公开 `config/tasks.json` **物理隔离**，
     **已被 `.gitignore` 忽略，永不随仓库发布**。
   - 默认 `run.py` 只加载公开 38 题；`leaderboard.csv / html` **均不含隐藏题**；`--score-answers` 结合 `--repeat N` 时排行榜额外给出各模型 mean±std 稳定性带。
   - `--include-hidden` 才合并隐藏集（本地 38+18=56 题），且生成的报告标题旁加
     **`[含隐藏集]`** 标记，便于内部刷分监控；公开排行榜只展示各模型"隐藏集综合"得分，
     **绝不泄露隐藏题的 id 或内容**（HTML 中不含 `TH1…`）。
   - 真实评测时，隐藏集由评测方私存，模型训练方无法据此过拟合，从而保护排行榜公信力。
   - 已有 `HiddenTaskTests`（4 项）校验：隐藏题数 ≥5、四类至少三类、每题 `hidden:true`
     且不在公开集、默认加载不含隐藏题、`--include-hidden` 后合并数量正确。
   - 注：当前 `hidden_tasks.json` 含 18 题本地样本（虚构演示）用于防刷分验证，git-ignored 不随仓库发布；正式发布前应再扩充并加密保管。
6. ⬜ 待办：正式发布前扩充隐藏集、加密保管；对全部规则型 expected 做法规版本轴核验。

7. ✅ P1 已提交（`cf375d5`，区分度门 + easy 校准题 + `--repeat N`）；✅ P2/P3 代码已落地（condition 法律题降至 3、fewshot 扩至 4 + 数值计算 1（ADV2）、ADV1 零漏分加固、隐藏集扩至 15、排行榜 mean±std 误差棒）：待 Mac 复跑 `models --repeat 3` + `difficulty_gate` 确认权威数字后刷新 `difficulty_gate_report.md` 并提交（惯例：本地提交由 AI 做，push 由用户做）。

## 隐藏测试集机制（防刷分）

| 维度 | 公开集 `config/tasks.json` | 隐藏集 `hidden_tasks.json` |
|------|---------------------------|----------------------------|
| 是否随仓库发布 | 是 | **否**（gitignore，物理隔离） |
| 题量（当前） | 38 | 18（本地样本，TH1–TH18） |
| 类型分布 | 格式提取 13 / 条件规则 14 / Few-shot 4 / 数值计算 1 / 多轮 3 / 长度约束 3 | 格式提取 5 / 条件规则 5 / 多轮 3 / Few-shot 2 / 长度约束 3 |
| 用途 | 练习 / 公开可复现 | 防过拟合、验证榜单公信力 |
| 对外可见内容 | 全公开 | 仅"隐藏集综合"聚合分，不展示逐题 |

接入真实模型后，用 `--include-hidden` 跑出的"隐藏集综合"列，是判断模型是否只背公开题的
关键信号——若公开集高、隐藏集低，则说明存在针对公开集的过拟合，榜单可信度下降。默认
（不带 `--include-hidden`）排行榜完全不含隐藏题，确保对外发布版本无可泄露内容。
