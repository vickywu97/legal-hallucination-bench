# Legal-Hallucination-Bench — MVP 设计规格 (v0.1)

> 施工图，非介绍文。目标是消除歧义到"可交给另一名工程师实现"的程度。
> 所有 schema 字段、路径、探针编号均为定稿意图，非占位符。
>
> ⚠️ **本文件为早期设计规格（v0.1），记录初始构想，已被最终实现取代。** 最终判定政策以 [`docs/DIFF_POLICY.md`](DIFF_POLICY.md) 与 [`docs/METHODOLOGY.md`](METHODOLOGY.md) 为准；内容 diff 已从早期设计的"四级"收口为"二元"（逐字=1.0 / 否则=0）。

---

## 0. MVP 范围与非目标

**In-scope (6 周交付)**
- 5 部核心法律的条文级版本化 KB
- 司法解释子集 + 指导性案例全量 + 全国法院层级名录
- 20 条陷阱探针（Arm B）+ 10 条开放题（Arm A 占位）
- 引注抽取器 + 三层核验引擎 + 评分器 + 审计报告渲染器
- `--offline` 一条命令出榜（canned 模型输出，零网络）
- `--live` 接 2–3 家真实模型（可选，需 API key）
- 中英 README + 方法学文档 + 一份示范审计报告

**Non-goals (MVP 不做)**
- 不做 Web UI（Phase 2）
- 不爬裁判文书网 / 不接会员库
- 不对终端用户输出"法律意见"
- 不做自动法条库更新（手动策展 + 版本化快照）

---

## 1. 数据模型（schema）

所有 KB 文件为 JSON / JSONL（YAML 严格子集；人工可审、Git 可追溯、**零运行时依赖、stdlib 离线可跑**）。一条核心原则：**每条数据都带时间戳与来源 URL**。序列化格式在 `SIX_WEEK_PLAN.md` 中已锁定：`laws_index.json`（法律级元数据）+ `statutes.jsonl`（条文版本节点）。

### 1.1 Law（法律级元数据）→ Statute（条文版本节点）

条文级版本化是核心护城河：同一法条在不同修订版中位置/内容可能不同，必须按"题目上下文时间"解析到正确版本。**时间窗不存储、由 `revision_of` 推导**——这是 Week 1 加固后的关键纪律。

```json
// knowledge_base/laws/laws_index.json  — 每部法律一条元数据
{
  "COMPANY_LAW": {
    "name": "中华人民共和国公司法",
    "aliases": ["公司法", "旧公司法"],          // 含废止法名，抓"引旧法名"时序幻觉
    "type": "法律", "order": 2,
    "issuing_authority": "全国人民代表大会常务委员会",
    "jurisdiction": "全国", "status": "effective",
    "promulgation_date": "2023-12-29", "effective_date": "2024-07-01",
    "source_url": "https://flk.npc.gov.cn/detail2.html?...",
    "source_accessed_at": "2026-07-31"
  }
}
```

```json
// knowledge_base/laws/statutes.jsonl  — 每条文版本一行
{"id":"COMPANY_LAW_13_v1","law_code":"COMPANY_LAW","article_number":"第十三条",
 "article_sort_key":13,"content":"公司法定代表人依照公司章程的规定……","effective_date":"2018-10-26",
 "revision_of":null,"source_url":"https://flk.npc.gov.cn/detail2.html?...",
 "source_accessed_at":"2026-07-31","notes":"2023修订 relocation 至第10条"}
{"id":"COMPANY_LAW_10_v1","law_code":"COMPANY_LAW","article_number":"第十条",
 "article_sort_key":10,"content":"公司的法定代表人按照公司章程的规定……","effective_date":"2024-07-01",
 "revision_of":"COMPANY_LAW_13_v1",                              // 指向上一版本（迁移/修订链）
 "source_url":"https://flk.npc.gov.cn/detail2.html?...","source_accessed_at":"2026-07-31",
 "notes":"由旧法第13条 relocation 而来"}
```

**关键字段语义**：
- `revision_of` 是**向后指针**：新版本指向被其取代的旧版本（含 relocation，如旧法第13条→新法第10条，跨 `article_sort_key`）。
- **时间窗由 `revision_of` 推导、不存储 repeal_date**：节点 `n` 的窗口 `window(n) = [n.effective_date, s.effective_date)`，其中 `s` 是 `s.revision_of == n.id` 的节点；最后一条窗口为 `[eff_n, null)`。左闭右开、无间隙、无重叠。
- `aliases` 含废止法名（"合同法""民法总则"→《民法典》；"旧公司法"→《公司法》），使"引用已废止/旧法名"的时序幻觉可被捕获。
- 引擎据此在 `as_of_date` 选最新在施修订版，是检测"时序幻觉"（引未生效/已废止条文）的依据。详见 `loader.py` 的 `_build_law_from_index_and_nodes` 与 `tests/test_jsonl_adapter.py` 的窗口断言。

### 1.2 JudicialInterpretation（司法解释）

```yaml
# knowledge_base/judicial_interpretations/<编号>.yaml
interpretation:
  doc_no: 法释〔2020〕17号          # 司法解释号，唯一
  title: 最高人民法院关于...
  issuing_court: 最高人民法院
  effective_date: 2020-12-05
  repealed_date: null
  source_url: ...
  articles: [...]                  # 同 Article schema
```

**用途**：模型引用"法释〔YYYY〕XX号"时做存在性核验（Tier1 硬）。

### 1.3 GuidingCase（指导性案例）

```yaml
# knowledge_base/guiding_cases/<编号>.yaml
case:
  case_no: "18"                     # 指导性案例编号
  title: ...
  court: 最高人民法院
  keyword_set: [买卖合同, 违约金]
  key_points:                       # 裁判要旨，结构化
    - point: ...
  effective_date: ...
  status: effective                  # 有界集合，全量收录
  source_url: ...
```

**用途**：模型引用"指导性案例第N号"时做存在性核验（Tier1 硬）；超过现存最大号=确定幻觉。

### 1.4 Court（法院层级图谱）

法院名录做成**层级关系图**而非扁平列表——这是 Tier2 案号核验从"正则"升级为"关系校验"的关键。

```yaml
# knowledge_base/courts.yaml
courts:
  - code: 最高法                    # 简码
    name: 最高人民法院
    level: supreme                   # supreme|high|intermediate|primary|specialized
    region: 全国
    parent_court: null
    established_date: 1949-10-22
    status: active
    case_type_prefixes: [民终, 刑终, 行终]   # 该法院可出的案号类型码
  - code: 京01
    name: 北京市第一中级人民法院
    level: intermediate
    region: 北京
    parent_court: 京高               # 管辖上级
    established_date: ...
    case_type_prefixes: [民初, 刑初, 行初]
```

**关系校验逻辑**：解析案号 `(2023)京01民终123号` → 法院=`京01`、类型=`民终`、年份=`2023` → 在图谱中查：①法院是否存在；②该法院层级是否可出`民终`（如基层法院不能出"终"字案号）；③年份是否在该法院存续期内。

### 1.5 时序解析算法

```
resolve_article(law_name, article_no, as_of_date):
    1. 查 law.aliases 命中
    2. 在该 law.revisions 中找 effective_date <= as_of_date 且 (repealed_date is null 或 repealed_date >= as_of_date) 的修订
    3. 在该修订 articles 中找 article_no（注意 amended_by 链：若 effective_until < as_of_date，沿链找替代条文）
    4. 返回 content 或 NOT_FOUND（含"此版本中无此条"vs"该法在 as_of 时尚未存在"两种 NOT_FOUND 语义）
```

---

## 2. 仓库结构

```
legal-hallucination-bench/
├── README.md                    # 中英双语；30 秒跑通；审计报告截图位
├── LICENSE                       # MIT（待定 Apache-2.0，见 §9）
├── pyproject.toml                # 纯 Python 依赖 pin；无 lxml/C 扩展
├── CONTRIBUTING.md               # 如何新增陷阱探针、贡献法条快照
├── docs/
│   ├── MVP_DESIGN.md            # 本文件
│   ├── METHODOLOGY.md           # 三层核验逻辑、局限性、数据来源（专业背书）
│   └── AUDIT_REPORT_TEMPLATE.md # 审计报告结构模板
├── knowledge_base/
│   ├── laws/laws_index.json     # 5 部法律级元数据（JSON，零依赖离线可跑）
│   ├── laws/statutes.jsonl      # 条文版本节点（一行一版本，含 revision_of 链）
│   ├── judicial_interpretations/*.json
│   ├── guiding_cases/*.json
│   └── courts.json
├── benchmark/
│   ├── probes/
│   │   ├── arm_b_time_displaced/     # 时间错位陷阱
│   │   ├── arm_b_abolished/          # 废止条文陷阱
│   │   ├── arm_b_fabricated_citation/ # 虚构引注陷阱
│   │   ├── arm_b_content_misquote/   # 法条内容错引
│   │   └── arm_a_open/              # 开放题（专家标注）
│   ├── sample_outputs/              # canned 模型回复，offline 模式用
│   ├── extract.py                   # 引注抽取（正则 + LLM 兜底）
│   ├── verify.py                    # Tier1/2/3 核验引擎
│   ├── score.py                     # 幻觉率计算 + bootstrap CI
│   ├── report.py                    # 审计报告渲染
│   └── run.py                       # CLI 入口
├── models/
│   └── adapters.py                  # OpenAI/Anthropic/智谱/通义/DeepSeek
├── results/                          # leaderboard.csv + 审计报告（.gitignore 或 LFS）
└── tests/                            # schema 校验、抽取召回、快照完整性
```

**离线优先原则**（吸收 DD-007 教训）：MVP 仅依赖 `pyyaml`、`regex`、`httpx`（live 模式可选）；不引入任何 C 扩展；`requirements.txt` 全部 pin；CI 用 `python -S` 干净环境验证。

---

## 3. 陷阱探针分类与首批 20 条

每条探针是 YAML：`{probe_id, type, prompt, ground_truth, expected_verdict, domain}`。`ground_truth` 由构造已知，**无需人工标注**——这是科学可复现的核心。

| 类型 | 数量 | ground truth 来源 | 示例 |
|---|---|---|---|
| B1 废止条文陷阱 | 4 | 修订事件 | 问需《公司法》旧版第13条（法定代表人）的场景；模型引旧条=幻觉。新法2024-07-01施行，第10条已改。 |
| B2 虚构司法解释号 | 4 | 构造 | 题干种入"法释〔2025〕99号"；模型展开论述=幻觉 |
| B3 虚构指导性案例号 | 3 | 有界集合 | 问"指导性案例第200号"（现存最大约40+号）；模型煞有介事=幻觉 |
| B4 法条内容错引 | 4 | KB 快照 | 要模型复述《民法典》第584条；与快照 diff 判完全/部分/编造 |
| B5 时间错位陷阱 | 3 | 时序逻辑 | 2020年终审的案件，模型适用《民法典》（2021.1.1施行）=幻觉 |
| B6 虚构法院陷阱 | 2 | 法院名录 | 引"北京市第四中级知识产权法院"（不存在）；模型认可=幻觉 |
| **合计** | **20** | | |

**防作弊设计**：探针集合分公开版（~15 条，随 repo 发布）与隐藏版（~5 条，不入 repo，仅本地跑）。后续社区贡献探针走 PR + 审核流程。

---

## 4. 核验引擎（三层，回顾）

- **Tier 1 硬核验**：法条/司法解释/指导性案例 → 存在性 + 内容逐字/语义 diff。**能下"真/假"结论。**
- **Tier 2 软核验**：普通案号 → 结构性异常（格式、法院存在、层级-类型-年份自洽）。**只下"异常"结论，明确不宣称查实存在。**
- **Tier 3 透明不可验**：Tier1/2 覆盖不到的引注 → 报"不可验证率"，**不计入 HR 分母**。

内容 diff 早期设计为**四级判定**（完全一致 / 实质性一致 / 部分遗漏 / 完全编造）；**后在法律实务校准中收口为二元判定（逐字=1.0 / 否则=0，详见 `docs/DIFF_POLICY.md`）**——法律场景下"实质性一致"仍属幻觉，故取消全部中间档，PARTIAL 仅作诊断子类。

---

## 5. 评分指标

| 指标 | 硬度 | 分母 | 说明 |
|---|---|---|---|
| 法条引注幻觉率 | 硬 | Tier1 引注数 | 存在性 |
| 法条内容幻觉率 | 硬 | Tier1 引注数 | **headline**，逐字 diff |
| 废止条文误用率 | 硬 | B1 探针数 | 时序幻觉 |
| 指导性案例幻觉率 | 硬 | B3 探针数 | 有界集合 |
| 案号结构异常率 | 软 | Tier2 案号数 | 标注"非存在性" |
| 不可验证率 | 透明 | 全部引注 | 透明度指标，不进 HR |
| 分领域 HR | — | — | 民/刑/行政/税/知产（三证红利） |

置信区间：bootstrap 1000 次重采样；模型间差异显著性用 McNemar（配对探针）。

---

## 6. CLI 接口

```bash
# 离线默认：canned 输出 + 内置 KB → 出排行榜与审计报告
python -m benchmark.run --offline

# 接真实模型（需 API key，可选）
python -m benchmark.run --live --models glm-4,qwen-max,deepseek-chat

# 对单条模型回答做核验（律师粘贴文本即可）
python -m benchmark.verify --text "依据《民法典》第584条..."

# 渲染某模型的审计报告
python -m benchmark.report --model glm-4 --out results/audit_glm-4.md
```

---

## 7. 6 周施工计划

每周结束有**明确交付物 + 验证门**，不达标不进入下一周。

### Week 1 — KB 基石 I：schema + 3 部法律 ✅ 已完成
- 交付：`SCHEMA.md` 落地；`民法典`、`公司法(2023修订)`、`刑法` 的 **JSON**；`loader.py`（版本化 + 时序解析）；快照完整性单测 + 时序解析单测（8 项全绿）；`python -S` 干净环境零依赖可跑
- 验证门：`python3 -S -m unittest discover -s tests` 全绿（stdlib unittest，零第三方依赖）；每条文含 `source_url` + `effective_date`
- 风险点：条文级版本化首次落地，第13条（旧公司法法人代表）→ 第10条（新法）的 `amended_by` 链要打通

### Week 2 — KB 基石 II：2 部法律 + JI + 指导案例 + 法院名录
- 交付：`专利法`、`税收征管法` YAML；司法解释子集（覆盖 B2 探针用到的真实编号 + 1 个虚构对照）；指导性案例全量结构化；`courts.yaml`（含京/沪/粤主要层级）
- 验证门：`resolve_article()` 对 10 条时序查询返回正确版本；法院图谱可查 `京01`→`京高`→`最高法`

### Week 3 — 引注抽取器
- 交付：`extract.py`（正则为主 + LLM 兜底，默认不调 API）；覆盖 5 种引注模式；自建 50 条律师文书样本的标注集；召回率单测
- 验证门：在标注集上召回 ≥ 95%（漏抽直接低估 HR，必须先达标）
- 风险点：模型输出格式千奇百怪（中文数字/脚注/夹注），数据增强不可省

### Week 4 — 核验引擎 + 20 探针 + 评分器
- 交付：`verify.py` Tier1（存在+内容 diff 四级）+ Tier2（案号结构）；20 条 Arm B 探针 YAML；`score.py` 出 HR + bootstrap CI；5 条 canned 模型输出做 offline 烟测
- 验证门：20 探针对 canned 输出的判定与手工预期 100% 一致
- 风险点：内容 diff 的"实质性一致"阈值需调；先保守判"部分遗漏"

### Week 5 — live 模型 + 审计报告
- 交付：`adapters.py` 接 2–3 家（智谱/通义/DeepSeek，国产优先）；`report.py` 渲染审计报告（模仿审计报告格式：检查项/依据/发现/结论）；真实排行榜
- 验证门：至少 2 家模型出完整审计报告；报告律师审阅可懂
- 风险点：API 成本与限流；先用小题量（20 探针 + 10 开放题）

### Week 6 — 包装发布 v0.1.0
- 交付：中英 README（30 秒跑通 + 审计报告截图）；`METHODOLOGY.md`；`CONTRIBUTING.md`；示范审计报告入 repo；CI 干净环境 `python -S` 跑通
- 验证门：陌生人 clone → `pip install -e .` → `python -m benchmark.run --offline` 出榜，零报错
- 风险点：README 诚实风险声明必须在显眼位置

---

## 8. 风险登记册

| 风险 | 缓解 |
|---|---|
| KB 时效 | 每条带 `effective_date` + `source_accessed_at`；按题目上下文时间匹配；旧法被引归"时序幻觉" |
| 抽取召回不足 | 附 audit 召回数；召回不足时 HR 为下界 |
| 探针污染 | 隐藏子集不入 repo；探针类型公开、实例部分保密 |
| 合规 | 不输出法律意见；README 明确"非法律意见、不构成执业" |
| 公信力冷启动 | 先建立"诚实评测者"品牌，Phase 2 工具再叠加 |
| 法律修订追踪 | 手动策展 + 季度审查；不做自动爬取 |

---

## 9. 待你拍板的 3 个决策（其余我按默认推进）

1. **MVP 5 部法律**：默认 `民法典 / 公司法(2023修订) / 刑法 / 专利法 / 税收征收管理法`（覆盖你三证 + 高频）。要换/加吗？
2. **首批 live 模型**：默认 `智谱 GLM-4 / 通义千问-Max / DeepSeek-Chat`（国产优先，符合你转型国内 AI 企业的目标）。要加 GPT-4o / Claude 对照吗？
3. **License**：默认 `MIT`（最宽松、最易被引用）。要换 `Apache-2.0`（含专利反诉条款，更"企业向"）吗？

---

## 10. Phase 2 远景（不在 MVP，但 schema 已为它留位）

- 法律文书逻辑矛盾检测工具（复用本 repo 的法条 KB + 引注核验引擎，作为工具内部"自己不幻觉"的前置依赖）
- 税法 / 知产专项子基准（你的独占性领域）
- Web UI（律师粘贴文本即可核验，引流款）

**关键依赖关系**：Phase 2 的工具要可信，其内部引注必须先过本 bench 的幻觉核验——即 **bench 是工具的前置依赖，不是取舍关系**。
