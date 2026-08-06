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
| 包 | 条文数 | Tier A | Tier B | 来源 |
|---|---|---|---|---|
| `PATENT_LAW_full` | 82 | 30 | 52 | 专利法(2020)，flk.npc.gov.cn |

## 使用
- 网页浏览/下载：见 [`index.html`](./index.html)
- 重新生成某个包（需先 `textutil -convert txt 官方.doc -output /tmp/law.txt`）：
  ```bash
  python3 -S scripts/build_law_pack.py \
    --txt /tmp/law.txt --law-code PATENT_LAW \
    --law-name "中华人民共和国专利法（2020修正）" --effective-date 2021-06-01
  ```
- 规格书：[`docs/PRODUCT_SPEC_法条库按需下载版.md`](../docs/PRODUCT_SPEC_法条库按需下载版.md)
