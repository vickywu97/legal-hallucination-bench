# 法律引注幻觉排行榜 (Leaderboard)

| 排名 | 模型 | 引注幻觉率(HVI) | 内容级幻觉率 | 张冠李戴率(CRFI) | 时序幻觉率 | 不可验率 | 引注数 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | DeepSeek-R1 | 50.0% | 100.0% | 0.0% | 2.4% | 0.0% | 42 |
| 2 | Qwen-Max | 54.5% | 100.0% | 0.0% | 0.0% | 0.0% | 33 |
| 3 | DeepSeek-V3 | 55.0% | 100.0% | 0.0% | 0.0% | 0.0% | 40 |
| 4 | GLM-4-Flash | 55.0% | 100.0% | 0.0% | 0.0% | 0.0% | 40 |
| 5 | Kimi | 64.6% | 100.0% | 0.0% | 0.0% | 0.0% | 48 |

## 逐题诊断矩阵 (Question × Model)

图例：✓ 通过(OK) ｜ ✗ 幻觉(HALLUCINATION) ｜ ? 不可验(UNVERIFIABLE) ｜ · 该题无引注

| 题号 | DeepSeek-R1 | Qwen-Max | DeepSeek-V3 | GLM-4-Flash | Kimi |
| --- | --- | --- | --- | --- | --- |
| Q1 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q2 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗NF/PARTIAL | ✗PARTIAL |
| Q3 | ✗PARTIAL | ✗NF | ✗NF | ✗NF | ✗NF/PARTIAL |
| Q4 | ✗NF | ✗NF | ✗NF | ✗NF | ✗PARTIAL |
| Q5 | ✗F | ✗PARTIAL | ✗F | ✗F | ✗NF/PARTIAL |
| Q6 | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗F | ✗PARTIAL |
| Q7 | ✗PARTIAL/T | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL | ✗PARTIAL |
| Q8 | ✗NF | ✗NF | ✗NF | ✗NF | ✗NF |
| Q9 | ✗F/NF | ✗F/NF | ✗NF | ✗F/NF | ✗F/NF |
| Q10 | ✗F | ✗NF | ✗NF | ✗F | ✗NF |
| Q11 | ✗F | ✗F | ✗PARTIAL | ✗TR | ✗F |
| Q12 | · | · | ✗NF | · | · |
| Q13 | ✗NF/PARTIAL | ✗F | ✗PARTIAL | ✗F | ✗NF/PARTIAL |
| Q14 | ✗F | ✗F | ✗F | ✗TR | ✗F |
| Q15 | ✗F/NF | ✗NF | ✗NF | ✗F | ✗NF |
| Q16 | ✗F/NF | ✗F/NF | ✗F/NF | ✗NF | ✗NF |
| Q17 | ✗F/NF | ✗NF | ✗F/NF/PARTIAL | ✗NF | ✗NF |
| Q18 | ✗F/NF | ✗NF | ✗F/NF | ✗F/NF | ✗F/NF |
| Q19 | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF | ✗F/NF |
| Q20 | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL |
| Q21 | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL | ✗NF/PARTIAL |
| Q22 | ✗F | ✗F | ✗F | ✗TR | ✗F |
| Q23 | ✗F/NF/PARTIAL | ✗F | ✗PARTIAL | ✗PARTIAL | ✗NF/PARTIAL |

子类缩写：T=时序幻觉 NF=条文不存在 MA=张冠李戴 F=内容编造 TR=截断 UG=未核验基准
