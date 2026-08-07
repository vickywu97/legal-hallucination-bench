# 法律引注幻觉排行榜 (Leaderboard)

| 排名 | 模型 | 引注幻觉率(HVI) | 内容级幻觉率 | 张冠李戴率(CRFI) | 时序幻觉率 | 不可验率 | 引注数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | Qwen-Max | 33.3% | 100.0% | 0.0% | 0.0% | 0.0% | 33 |
| 2 | DeepSeek-V3 | 45.0% | 100.0% | 0.0% | 0.0% | 0.0% | 40 |
| 3 | GLM-4-Flash | 45.0% | 100.0% | 0.0% | 0.0% | 0.0% | 40 |
| 4 | DeepSeek-R1 | 47.6% | 100.0% | 0.0% | 2.4% | 0.0% | 42 |
| 5 | Kimi | 54.2% | 100.0% | 0.0% | 0.0% | 0.0% | 48 |

## 逐题诊断矩阵 (Question × Model)

图例：✓ 通过(OK) ｜ ✗ 幻觉(HALLUCINATION) ｜ ? 不可验(UNVERIFIABLE) ｜ · 该题无引注

| 题号 | Qwen-Max | DeepSeek-V3 | GLM-4-Flash | DeepSeek-R1 | Kimi |
| --- | --- | --- | --- | --- | --- |
| Q1 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q2 | ✗PARTIAL | ✗PARTIAL | ✗NF/PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q3 | ✗F/NF | ✗NF | ✗F/NF | ✗PARTIAL | ✗NF/PARTIAL |
| Q4 | ✗F | ✗NF | ✗F | ✗NF | ✗PARTIAL |
| Q5 | ✗PARTIAL | ✗F | ✗F | ✗F | ✗NF/PARTIAL |
| Q6 | ✗PARTIAL | ✗PARTIAL | ✗F | ✗PARTIAL | ✗PARTIAL |
| Q7 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL/T | ✗PARTIAL |
| Q8 | ✗F | ✗PARTIAL | ✗F | ✗PARTIAL | ✗F |
| Q9 | ✗F/NF | ✗NF | ✗F/NF | ✗F/NF | ✗F/NF |
| Q10 | ✗F | ✗F | ✗F | ✗F | ✗PARTIAL |
| Q11 | ✗F | ✗PARTIAL | ✗TR | ✗F | ✗F |
| Q12 | · | ✗NF | · | · | · |
| Q13 | ✗F | ✗PARTIAL | ✗F | ✗NF/PARTIAL | ✗NF/PARTIAL |
| Q14 | ✗F | ✗F | ✗TR | ✗F | ✗F |
| Q15 | ✗F | ✗F | ✗F | ✗F/NF | ✗PARTIAL |
| Q16 | ✗F/NF | ✗F/NF | ✗NF | ✗F/NF | ✗F/NF |
| Q17 | ✗F/NF | ✗F/NF/PARTIAL | ✗F/NF | ✗NF/PARTIAL | ✗F/NF |
| Q18 | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF |
| Q19 | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF |
| Q20 | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL |
| Q21 | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL |
| Q22 | ✗F | ✗F | ✗F | ✗F | ✗F |
| Q23 | ✗F | ✗PARTIAL | ✗PARTIAL | ✗F/NF/PARTIAL | ✗NF/PARTIAL |

子类缩写：T=时序幻觉 NF=条文不存在 MA=张冠李戴 F=内容编造 TR=截断 UG=未核验基准
