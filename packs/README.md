# 法条库 · 按需下载版

基于 [legal-hallucination-bench](https://github.com/vickywu97/legal-hallucination-bench) 的已核验 KB pipeline，
把 8 部常用法律做成**按领域拆分、可单独下载的全集包**。律师下公司法全集、税务人下税务包、AI 开发者下自己要评测的那部——
比一个 monolithic KB 给人更多选择，也更好讲故事。

> **与评测基准的关系**：评测引擎的 ground truth 永远是 `knowledge_base/laws/statutes.jsonl`（现 **2327 个已核验节点 = 8 部法完整官方全文**），由 `loader.load_laws()` 单一来源加载，引擎不读 `packs/`。本 `packs/` 目录是这份**同一份已核验语料**的按领域拆分下载镜像（同源、可相互校验）。二者区别仅在分发形态：Pack 多一个 `trust_tier` 下载侧信任标签，但评测侧一律视为 verified。来源可信度门禁（`refuse_unverified_ground_truth`）仍有效，未来任何真正未核验节点都会被引擎拒绝当事实依据。

## 当前包（v1.0，9 包 / 2541 条，全部 Tier A）

| 包 | 条文数 | Tier A | Tier B | 说明 |
|---|---|---|---|---|
| `PATENT_LAW_full` | 82 | 82 | 0 | 专利法(2020修正) 全文 |
| `IIT_LAW_full` | 22 | 22 | 0 | 个人所得税法(2018修正) 全文 |
| `EIT_LAW_full` | 60 | 60 | 0 | 企业所得税法(2018修正) 全文 |
| `COMPANY_LAW_full` | 266 | 266 | 0 | 公司法(2023修订) 全文 |
| `CRIMINAL_LAW_full` | 505 | 505 | 0 | 刑法(2023修正) 全文，含 第X条之一 修正案插入条 |
| `VAT_LAW_full` | 38 | 38 | 0 | 增值税法(2026生效) 全文 |
| `CIVIL_CODE_full` | 1260 | 1260 | 0 | 民法典(2020) 全文 |
| `TAX_ADMIN_LAW_full` | 94 | 94 | 0 | 税收征收管理法(2015修正) 全文 |
| `TAX_full` | 214 | 214 | 0 | **税务合并包** = 企税60 + 个税22 + 增值税38 + 税收征管94 |

- **Tier A（专家核验 / 官方源确认完整）**：全部 9 个包（8 部法全集 + 税务合并包，共 2541 条）已于 2026-08-07 经专家逐项比对「最大条号=法定总条数、且 1→最大条号无断号」确认官方源即全文，并整包升 Tier A，均可作 AI 评测 ground truth。
- 备注：Tier B（官方全文提取、未逐条签核）机制仍保留于 `scripts/build_law_pack.py` 的默认构建模式，供后续新增包使用；当前 9 包已全部为 Tier A。

## 数据格式
每个包提供三格式，内容一致：
- `*.jsonl` — 机器可读，schema 同 Bench 的 `statutes.jsonl`，附加 `trust_tier` 字段。可直接接入 RAG / Embedding 管线。
- `*.md` — 人类可读浏览。
- `*.csv` — 表格软件 / 数据分析。

## 使用

网页浏览/下载：见 [`index.html`](./index.html)。

重新生成某个包（需先 `textutil -convert txt 官方.doc -output /tmp/law.txt`）：

```bash
python3 -S scripts/build_law_pack.py \
  --txt /tmp/law.txt --law-code PATENT_LAW \
  --law-name "中华人民共和国专利法（2020修正）" --effective-date 2021-06-01
```

构建合并包（如税务包）即把若干 `*_full.jsonl` 拼接后，用仓库内脚本重新生成 `.md/.csv` 并 `regenerate_index('packs')`。

## 信任分级设计
- **Tier A 专家核验**：现有 212 个节点由专家逐条比对官方全文一致（保留原始 `verified_by/at` 溯源），是 2327 节点 ground truth 的 provenance 子集；其余 2115 个节点在「官方源经专家确认完整 + 逐字提取」准则下升为 verified。2026-08-07 起，8 部法全集包经「官方源确认完整」后整包升 Tier A（2541 条全 A），与 Bench 的 `statutes.jsonl` 同源。
- **Tier B 官方全文提取**：从官方 .doc 逐字提取的完整条文，结构化对齐（条号+正文），来源可信但**未逐条人工签核**
  → 用于“按需下载”参考，不作评测判分 ground truth（除非后续升 A）。该机制保留为默认构建模式，当前 9 包已无 Tier B。
- 每条带 `trust_tier` + `source`（官方文件批次）+ `effective_date`（生效日）。诚实做到“全量覆盖”而不稀释评测可信度。

## 规格书
产品定义见 [`docs/PRODUCT_SPEC_法条库按需下载版.md`](../docs/PRODUCT_SPEC_法条库按需下载版.md)。
