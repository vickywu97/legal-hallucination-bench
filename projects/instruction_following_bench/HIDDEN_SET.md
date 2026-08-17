# 防刷分隐藏集（Hidden Set）使用说明

> 适用子项目：`projects/instruction_following_bench/`（项目 C · 中文 To B 指令遵循评测基准）。
> 本文说明隐藏集的**目的、运行方式、以及"绝不泄露"是如何被物理隔离 + gitignore 双重保证的**。

---

## 1. 这是什么

`hidden_tasks.json` 是与公开 `config/tasks.json`（21 题）**分离存放**的留底隐藏题集。
当前含 **5 题**：

| id | 类型 | 难度 |
| --- | --- | --- |
| TH1 | format_extraction（格式提取） | medium |
| TH2 | format_extraction（格式提取） | hard |
| TH3 | condition_rule（条件规则） | medium |
| TH4 | condition_rule（条件规则） | hard |
| TH5 | multi_turn_constraint（多轮约束） | hard |

每题带 `hidden: true` + `difficulty` + `demo_note`（虚构演示数据声明）。

## 2. 目的：防刷分（anti-gaming）

公开排行榜只展示公开 21 题的得分。如果有人**针对公开题刷分 / 过拟合**，隐藏集能独立验证
其泛化能力——隐藏集的**逐题内容永不外泄**，对外页面只聚合展示各模型的 `hidden_total`
（隐藏集综合得分）一列。这样即便公开题刷到满分，也藏不住真实水平。

## 3. 怎么跑

真实答案评分时加上 `--include-hidden`：

```bash
cd /Users/vickywu/WorkBuddy/2026-07-26-16-50-27/legal-hallucination-bench
python3 -S -m projects.instruction_following_bench.run --score-answers answers_ifb.jsonl --include-hidden
```

离线 DEMO（无需 API key，分数来自随机/空哑巴基线，**非真实排名**）：

```bash
python3 -S -m projects.instruction_following_bench.run --offline --include-hidden
```

加上该旗标后，报告（`leaderboard.html`）会：

- 标题与 `<h1>` 带 **`[含隐藏集]`** 标记；
- 表格新增 **`隐藏集综合(防刷分)`** 列（各模型在隐藏集上的综合得分）；
- 页面顶部出现 **⛨ 防刷分** 紫色横幅，说明隐藏题不公开、不随仓库发布。

若**不加** `--include-hidden`，或 `hidden_tasks.json` **不存在**（如克隆的公开仓库），
流水线照常运行，只是不评隐藏集、不显示该列——`run.py` 的 `load_hidden()` 在文件缺失时
返回 `[]`，绝不报错中断。

## 4. 物理隔离 + gitignore 双重保证"绝不泄露"

- **物理隔离**：隐藏集是独立文件 `hidden_tasks.json`，位于项目根，不与公开 `config/tasks.json`
  混放；评分时由 `HIDDEN_PATH` 单独加载并打 `hidden=True` 标记。
- **绝不入库**：`.gitignore` 显式忽略
  `projects/instruction_following_bench/hidden_tasks.json`，因此它**永远不会被 `git push` 发布**出去。
- **本地自检（推荐纳入 CI / 发布前检查）**：

  ```bash
  git check-ignore projects/instruction_following_bench/hidden_tasks.json
  # 若返回该路径 → 已被忽略（安全，不入库）；
  # 若无输出     → 泄露风险！需立即检查 .gitignore / git rm --cached。
  ```

- **代码层保险**：报告渲染**只输出聚合列**，无任何逐题内容出口；`load_hidden()` 缺失即降级为空，
  保证"公开仓库无隐藏集也能跑通"。

## 5. 维护约定

- 隐藏集与公开集**同口径**评分（三维 0.3·format + 0.4·content + 0.3·closure），不另设规则。
- 增删隐藏题**只改** `hidden_tasks.json`，**不要**并回 `config/tasks.json`，也**不要**在对外
  页面 / 文档 / 提交记录中粘贴逐题内容（连题面都不要）。
- 所有题目均为**虚构演示数据**（`demo_note` 标注），公开发布为真实基准前须经作者（税务师 / 律师）
  逐题核验并标注法规版本轴。

## 6. 合规保护

题目样例、公司名、发票、合同均为虚构示例，不构成对任何真实企业或模型的背书，也不构成
税务 / 法律 / 专业意见。隐藏集机制本身也服务于这一保护目标——避免对外暴露任何可被误当
"真实产品 / 业绩 / 测试结论"的材料。
