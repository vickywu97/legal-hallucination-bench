# 法条库 · 按需下载版

基于 [legal-hallucination-bench](https://github.com/vickywu97/legal-hallucination-bench) 的已核验 KB pipeline，
把 8 部常用法律做成**按领域拆分、可单独下载的全集包**。律师下公司法全集、税务人下税务包、AI 开发者下自己要评测的那部——
比一个 monolithic 212 节点 KB 给人更多选择，也更好讲故事。

## 当前包（v1.0，9 包 / 2541 条）

| 包 | 条文数 | Tier A | Tier B | 说明 |
|---|---|---|---|---|
| `PATENT_LAW_full` | 82 | 30 | 52 | 专利法(2020修正) |
| `IIT_LAW_full` | 22 | 22 | 0 | 个人所得税法(2018修正) 全文 |
| `EIT_LAW_full` | 60 | 60 | 0 | 企业所得税法(2018修正) 全文 |
| `COMPANY_LAW_full` | 266 | 16 | 250 | 公司法(2023修订) |
| `CRIMINAL_LAW_full` | 505 | 27 | 478 | 刑法(2023修正)，含 第X条之一 修正案插入条 |
| `VAT_LAW_full` | 38 | 15 | 23 | 增值税法(2026生效) ⚠️ 见下方说明 |
| `CIVIL_CODE_full` | 1260 | 27 | 1233 | 民法典(2020) |
| `TAX_ADMIN_LAW_full` | 94 | 15 | 79 | 税收征收管理法(2015修正) |
| `TAX_full` | 214 | 112 | 102 | **税务合并包** = 企税60 + 个税22 + 增值税38 + 税收征管94 |

- **Tier A**（专家核验）：命中 `knowledge_base/laws/statutes.jsonl` 中已逐条签核的节点，可作 AI 评测 ground truth。
- **Tier B**（官方全文提取）：从官方 .doc 逐字提取、尚未逐条专家签核，仅作参考，**不作评测判分 ground truth**；升 A 需运行
  `python -S -m knowledge_base.verify_kb review`。

## ⚠️ 增值税法条数说明
本包《增值税法》依据所提供的官方源提取为 **38 条**（第38条即“本法自2026年1月1日起施行+暂行条例废止”的尾条）。
公开资料多称增值税法为 41 条，二者不符，**可能系所提供源文件截断**。使用前请核对全国人大法律法规数据库（flk.npc.gov.cn）原文；
若确为 41 条，请用完整官方 .doc 重新生成（见下）。

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
- **Tier A 专家核验**：现有 212 节点，逐条比对官方全文一致 → 继续作 AI 评测 ground truth。
- **Tier B 官方全文提取**：从官方 .doc 逐字提取的完整条文，结构化对齐（条号+正文），来源可信但**未逐条人工签核**
  → 用于“按需下载”参考，不作评测判分 ground truth（除非后续升 A）。
- 每条带 `trust_tier` + `source`（官方文件批次）+ `effective_date`（生效日）。诚实做到“全量覆盖”而不稀释评测可信度。

## 规格书
产品定义见 [`docs/PRODUCT_SPEC_法条库按需下载版.md`](../docs/PRODUCT_SPEC_法条库按需下载版.md)。
