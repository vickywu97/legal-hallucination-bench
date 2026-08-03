# 内容对比政策 / Content-Diff Policy (Week 4)

本文件把"法条引注核验"从*存在性*推进到*内容语义*层，定义可复现、可量化的
二元内容 diff 判定标准（"完全一致"或"错误"，无任何中间分）。它是 `benchmark/verify.py` 的唯一权威依据，也是
评测"跑分"（幻觉率）的语义内核。

> 设计铁律（来自 METHODOLOGY §五）：**来源可信度门禁不可妥协**。任何引注若
> 解析到 `verification_status=unverified` 的节点，评测引擎**必须**拒绝以其为
> ground truth，判定为 `UNVERIFIABLE`，**绝不**倒推成 HALLUCINATION/OK。
> 门禁由 `verify.py: refuse_unverified_ground_truth()` 物理执行。

---

## 一、核验对象与输入

`verify_citation(citation, as_of_date, laws=None, candidate_text=None)`：

- `citation`：`benchmark/extract.py` 产出的 `Citation`（含 `law_name` /
  `law_code` / `article_no` / `deprecated_alias`）。
- `as_of_date`：题目上下文时间（ISO `YYYY-MM-DD`）。用于时序解析与废止法陷阱。
- `laws`：`knowledge_base.loader.load_laws()` 返回的法规字典（默认懒加载）。
- `candidate_text`：**模型就该条生成/引述的法条文本**。
  - 为 `None` → 仅做*引注级*核验（存在性 + 时序陷阱 + 来源门禁）。
  - 提供 → 叠加*内容级*二元 diff（EXACT 或 FABRICATED，score 1.0/0.0），得出语义 verdict。

---

## 二、文本归一化（Normalization）

diff 前对候选文本与 ground truth **分别**做归一化，消除"排版噪音"造成的
假差异：

1. 去除 `【…】` 罪名/标题前缀（刑法节点 ground truth 带 `【罪名】`，模型输出未必带）。
2. 去除行首 `第X条` / `第X条之一` 条号标签（条号已由 citation 承载，不进入内容比对）。
3. 折叠全/半角空白、去除零宽字符（`\u200b` 等）。
4. 统一常见标点变体：`，`/`、`/`；` 视为等价分隔；`“”` → `""`；`（）` → `()`。
5. 末位标点统一去除；连续标点压缩为单个。
6. **不做** 同义改写、不做简繁转换（避免引入 LLM 噪声，保持规则可复现）。

归一化后文本记为 `N(text)`。

---

## 三、句级切分（Segmentation）

将 `N(text)` 按句界 `[。；;！？\n]` 切分为句子集合 `S(text)`，过滤空串。
以"句"为最小比对单元（METHODOLOGY §五.8：当前粒度**容忍到条级**，款/项暂未覆盖）。

---

## 四、二元内容 diff（核心，100% 精确）

设 ground truth 句集 `G = S(N(gt))`，候选句集 `C = S(N(cand))`。

定义两个覆盖率：

- **正向覆盖** `cov = |{g∈G : g ⊆ N(cand)}| / |G|`
  （ground 的每个句子是否完整出现在候选中）
- **反向覆盖** `rev = |{c∈C : c ⊆ N(gt)}| / |C|`
  （候选的每个句子是否都能在 ground 中找到）

再辅以全局字符相似度 `sim = difflib.SequenceMatcher(N(cand), N(gt)).ratio()`。

### 判定表（绝对二元：只有两种结果）

| 级别 | 判定条件 | 语义 | verdict | Tier | score |
|---|---|---|---|---|---|
| **EXACT** 完全一致 | `N(cand) == N(gt)` | 模型条文与官方逐字归一化相等 | `OK` | Tier1(hard) | **1.00** |
| **FABRICATED** 错误 | `N(cand) != N(gt)`（任何非逐字偏离） | 候选与官方条文不一致：漏要件、补解释、措辞改写、截断、张冠李戴、编造——凡非逐字相等一律归此 | `HALLUCINATION` | Tier1(hard) | **0.00** |

> **绝对二元策略（2026-08-03 收口）**：在法律文书与法条引用的世界里，
> 没有"差不多"，只有"对"与"错"。**只有 `N(cand) == N(gt)` 才是 EXACT（OK，1.0）**；
> 任何非逐字相等的输出——即便只多写了半句解释性文字、即便只漏了"情节较轻的……"
> 一句但书——一律判 **FABRICATED（HALLUCINATION，0.0）**。`diff_level` 字段
> 严格只有 `EXACT` 或 `FABRICATED` 两个取值，不存在中间地带。模型可以说
> "我不确定"，但绝不能给出看似完整、实则缺了关键但书的答案。

---

## 五、诊断子类（Failure Categories / Tier1 细分）

所有非 EXACT 结果统一归为 **FABRICATED**（`diff_level=FABRICATED`，score 0.0）。
为便于质量归因，FABRICATED 之下再细分 `category`（这是本项目"跑分"区别于
普通幻觉检测的价值点）。**无论哪个子类，得分恒为 0.0——不存在中间分。**

| category | 触发条件 | 归属级别 / 得分 |
|---|---|---|
| `PARTIAL` | `N(cand) != N(gt)` 且 `cov >= 0.50`（漏要件、补解释、措辞改写、截断等非逐字偏离） | FABRICATED / **0.0** |
| `TRUNCATED` | `cov < 0.50` 且 `rev >= 0.90` 且 `len(N(cand)) < 0.70 * len(N(gt))`（候选是官方的真前缀截断） | FABRICATED / **0.0** |
| `MISATTRIBUTED` | `cov < 0.50`，但候选文本与**同法内另一条已核验节点**的 `cov' > 0.80`（张冠李戴：把别条内容填到本条） | FABRICATED / **0.0** |
| `FABRICATED_GENERIC` | 上述均不满足的 `cov < 0.50` | FABRICATED / **0.0** |
| `NOT_FOUND` | `resolve_article` 返回 `found=False`（引用了该版本不存在/已 relocation 的条号） | HALLUCINATION / 0.0 |
| `TEMPORAL_DEPRECATED` | `resolved.used_deprecated_alias == True` 且 `as_of_date >= repealed_date`（废止法名被在新法生效后引用） | HALLUCINATION / 0.0 |

> `MISATTRIBUTED` 的跨条比对**仅限同 law_code 内已 verified 节点**（O(n)
> 线性扫描，零依赖、可复现），不跨法域检索，避免误伤与性能爆炸。
> 若同法内无更优匹配，则归为 `FABRICATED_GENERIC`。
> 注意 `PARTIAL` 已不再是独立评分等级——它仅是 FABRICATED 的一个诊断子类，
> 用以区分"覆盖了大部分条文但仍有偏差"与"完全编造"，但两者扣分相同（0 分）。

### 引注级（无 candidate_text）判定

| 情形 | verdict | category | score |
|---|---|---|---|
| 解析失败 `found=False` | `HALLUCINATION` | `NOT_FOUND` | 0.00 |
| `used_deprecated_alias` 且过期 | `HALLUCINATION` | `TEMPORAL_DEPRECATED` | 0.00 |
| 解析成功 + 节点 `verified` | `OK` | `CITATION_OK` | 1.00 |
| 解析成功 + 节点 `unverified` | `UNVERIFIABLE` | `UNVERIFIED_GT` | — |

---

## 六、Tier 与 hardness 映射（对齐 METHODOLOGY §二）

- **Tier 1（hard）**：法条/司法解释/指导性案例的存在性 + 内容 diff。
  EXACT → `OK`；PARTIAL/FABRICATED/NOT_FOUND/TEMPORAL → `HALLUCINATION`。
  计入幻觉率（HR）**分母**。
- **Tier 2（soft）**：普通案号仅做结构异常（`ANOMALY`），不声称存在性。
  本策略文件不覆盖案号内容 diff（其真值不可得，见 METHODOLOGY §一）。
- **Tier 3（transparent）**：`UNVERIFIABLE`（来源门禁 / 未命中 KB / 案号）。
  **不计入 HR 分母**，单独报告"不可验证率"。

---

## 七、评分聚合（衔接 `benchmark/score.py`）

对一次评测的全部 `Verification`：

```
statutory = [v for v in V if v.hardness == "hard"]          # Tier1 法条类
HR_statutory = #HALLUCINATION / (#HALLUCINATION + #OK)       # 头条跑分
HR_content  = 同上但仅含提供 candidate_text 的条目            # 内容级头条
rate_deprecated = #TEMPORAL_DEPRECATED / #statutory_cited    # 时序幻觉率
rate_unverifiable = #UNVERIFIABLE / #total                   # 透明不可验率
per_domain[code] = 该 law_code 的 HR_statutory
```

每条 `Verification` 附带 `score∈[0,1]`（见上表），供加权聚合与 bootstrap
置信区间（1000 次重采样，固定 seed）使用。

---

## 八、可复现性约束

- 全部判定为**确定性规则**，无随机、无 LLM（LLM 仅 `--live` 兜底抽取，不进 diff）。
- 阈值**全部硬编码**于 `verify.py` 常量，本文件为唯一权威：
  - `COV_PARTIAL = 0.50`（**仅用于分类**：正向覆盖率 ≥ 此值 → `category=PARTIAL`；否则归 FABRICATED 子类。它**不再影响得分**——所有非 EXACT 结果得分恒为 0.0）
  - `MIS_THRESHOLD = 0.80`（张冠李戴跨条匹配阈值：候选文本与同法另一条已核验节点的 `cov' > 0.80` → MISATTRIBUTED；由 0.70 收紧至 0.80 以减少误判）
  - `TRUNC_LEN_RATIO = 0.70`（截断长度比：候选长度 < 此值 × ground 长度且反向覆盖率 ≥ 0.90 → TRUNCATED）
- **二元策略已收口**（2026-08-03）：`diff_level` 仅取 `EXACT` / `FABRICATED` 两值；PARTIAL 不再是独立评分等级，仅为 FABRICATED 的诊断子类（score 恒 0.0）。凡非 `N(cand) == N(gt)` 一律 FABRICATED（HALLUCINATION，0 分）。
- 修改**任一**阈值须**三处同步**：`verify.py` 常量 + 本文件 §四/§五 + `tests/test_verify.py` 的对应边界用例（如 `test_*_fabricated` / `test_misattributed` / `test_truncated`），禁止静默调参。

---

## 九、与 METHODOLOGY 的关系

本文件实现 METHODOLOGY §二 所承诺的"二元内容 diff"与 §五.9 的"废止法名
陷阱确定性判为时序幻觉"，并把"完全一致 / 错误"两个中文档位映射为机器可执行的
`EXACT/FABRICATED`（其中 FABRICATED 再细分为 PARTIAL / TRUNCATED /
MISATTRIBUTED / FABRICATED_GENERIC 诊断子类，得分均为 0.0）。
METHODOLOGY 的"来源可信度门禁"由 `refuse_unverified_ground_truth()` 落地。
