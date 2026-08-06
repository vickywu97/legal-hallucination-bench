# 法条库 · 按需下载版（packs/）

把已核验 KB 按**法律领域**拆成可独立下载的全集包。每个包一份 `*{LAW_CODE}_full.jsonl`
（机器可读，同 Bench 的 `statutes.jsonl` schema，附加 `trust_tier` 字段），并派生 `.md` / `.csv` 方便非开发者。

## 信任分级（重要）
- **Tier A（`verification_status=verified`）**：命中 `knowledge_base/laws/statutes.jsonl` 中已由
  Vicky Wu（律师/税务师/专利代理师）逐条比对官方来源并具名签署的条文 → 可作 AI 评测 ground truth。
- **Tier B（`verification_status=unverified`）**：从官方 `.doc` 逐字提取、尚未逐条专家签核 →
  **仅作参考，不作 AI 评测 ground truth**。升 A 需运行
  `python -S -m knowledge_base.verify_kb review`。

> 全集包先以 Tier B 发布（覆盖全量条文），再随专家核验逐步升 A。这样"全量覆盖"与 Bench 的
> 评测门禁互不冲突：评测仍只用 Tier A。

## 当前包
| 包 | 条文数 | Tier A | Tier B | 内容 | 来源 |
|---|---|---|---|---|---|
| `PATENT_LAW_full` | 82 | 30 | 52 | 专利法(2020修正) 全文 | 专利法(2020)，flk.npc.gov.cn |
| `IIT_LAW_full` | 22 | 22 | 0 | 个人所得税法(2018修正) 全文 | 个税(2018)，flk.npc.gov.cn |
| `EIT_LAW_full` | 60 | 60 | 0 | 企业所得税法(2018修正) 全文 | 企税(2018)，flk.npc.gov.cn |
| `TAX_full` | 82 | 82 | 0 | **实体税法包** = 企税(60)+个税(22) 合并全集 | 同上 |

> `IIT_LAW_full` / `EIT_LAW_full` / `TAX_full` 当前 **Tier A 100%**（即本仓库已核验 KB 覆盖了这两部税的
> 全部条文），可直接作 AI 评测 ground truth。`PATENT_LAW_full` 的 52 条 Tier B 待逐条签核升 A。

## 待补包（需官方源）
| 计划包 | 缺口 | 阻塞 |
|---|---|---|
| 增值税法全集 | 15 → 41 条 | 缺官方 `.doc`（本地仅有专利/个税/企税三份） |
| 税收征收管理法全集 | 15 → 94 条 | 缺官方 `.doc` |
| 公司法全集 | 16 → 266 条 | 缺官方 `.doc` |
| 民法典全集 | 27 → 1260 条 | 缺官方 `.doc` |
| 刑法全集 | 27 → 452 条 | 缺官方 `.doc` |

> 拿到对应官方 `.doc` 后，复用 `scripts/build_law_pack.py` 即可一键生成；增值税法/税收征管法可与
> 现有 `TAX_full` 合并为完整「税务包」。

## 使用
- 网页浏览/下载：见 [`index.html`](./index.html)
- 重新生成某个包（需先 `textutil -convert txt 官方.doc -output /tmp/law.txt`）：
  ```bash
  python3 -S scripts/build_law_pack.py \
    --txt /tmp/law.txt --law-code PATENT_LAW \
    --law-name "中华人民共和国专利法（2020修正）" --effective-date 2021-06-01
  ```
- 规格书：[`docs/PRODUCT_SPEC_法条库按需下载版.md`](../docs/PRODUCT_SPEC_法条库按需下载版.md)
