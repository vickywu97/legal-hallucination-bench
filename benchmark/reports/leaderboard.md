# 法律引注幻觉排行榜 (Leaderboard)

| 排名 | 模型 | 引注幻觉率(HVI) | 内容级幻觉率 | 张冠李戴率(CRFI) | 时序幻觉率 | 不可验率 | 引注数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | DeepSeek-R1 | 36.8% | 100.0% | 0.0% | 5.3% | 0.0% | 19 |
| 2 | GLM-4-Flash | 45.0% | 100.0% | 0.0% | 0.0% | 0.0% | 20 |
| 3 | Qwen-Max | 47.1% | 100.0% | 0.0% | 0.0% | 0.0% | 17 |
| 4 | Kimi | 50.0% | 100.0% | 0.0% | 0.0% | 0.0% | 22 |
| 5 | DeepSeek-V3 | 60.0% | 100.0% | 0.0% | 0.0% | 0.0% | 20 |

## 逐题诊断矩阵 (Question × Model)

图例：✓ 通过(OK) ｜ ✗ 幻觉(HALLUCINATION) ｜ ? 不可验(UNVERIFIABLE) ｜ · 该题无引注

| 题号 | DeepSeek-R1 | GLM-4-Flash | Qwen-Max | Kimi | DeepSeek-V3 |
| --- | --- | --- | --- | --- | --- |
| Q1 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q2 | ✗PARTIAL | ✗NF/PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q3 | ✗PARTIAL | ✗NF | ✗NF | ✗NF/PARTIAL | ✗NF |
| Q4 | ✗NF | ✗NF | ✗NF | ✗PARTIAL | ✗NF |
| Q5 | ✗F | ✗F | ✗PARTIAL | ✗NF/PARTIAL | ✗F |
| Q6 | ✗PARTIAL | ✗F | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q7 | ✗PARTIAL/T | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q8 | ✗NF | ✗NF | ✗NF | ✗NF | ✗NF |
| Q9 | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF | ✗NF |
| Q10 | ✗F | ✗F | ✗NF | ✗NF | ✗NF |
| Q11 | ✗F | ✗TR | ✗F | ✗F | ✗PARTIAL |
| Q12 | · | · | · | · | ✗NF |
| Q13 | ✗NF/PARTIAL | ✗F | ✗F | ✗NF/PARTIAL | ✗PARTIAL |
| Q14 | ✗F | ✗TR | ✗F | ✗F | ✗F |
| Q15 | ✗F/NF | ✗F | ✗NF | ✗NF | ✗NF |

子类缩写：T=时序幻觉 NF=条文不存在 MA=张冠李戴 F=内容编造 TR=截断 UG=未核验基准
