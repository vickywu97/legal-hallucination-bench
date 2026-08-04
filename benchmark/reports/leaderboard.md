# 法律引注幻觉排行榜 (Leaderboard)

| 排名 | 模型 | 法条幻觉率 | 内容级幻觉率 | 时序幻觉率 | 不可验率 | 引注数 |
| --- | --- | --- | --- | --- | --- | --- |
| 1 | Model-A-good | 0.0% | 0.0% | 0.0% | 0.0% | 3 |
| 2 | Model-B-bad | 100.0% | 100.0% | 0.0% | 0.0% | 3 |
| 3 | Model-C-partial | 100.0% | 100.0% | 0.0% | 0.0% | 3 |

## 逐题诊断矩阵 (Question × Model)

图例：✓ 通过(OK) ｜ ✗ 幻觉(HALLUCINATION) ｜ ? 不可验(UNVERIFIABLE) ｜ · 该题无引注

| 题号 | Model-A-good | Model-B-bad | Model-C-partial |
| --- | --- | --- | --- |
| Q1 | ✓ | ✗PARTIAL | ✗PARTIAL |
| Q3 | ✓ | ✗NF | ✗NF |
| Q10 | ✓ | ✗MA | ✗PARTIAL |

子类缩写：T=时序幻觉 NF=条文不存在 MA=张冠李戴 F=内容编造 TR=截断 UG=未核验基准
