# 审计报告：Model-B-bad

- 引注数：3
- 法条幻觉率 HR_statutory：100.0% （bootstrap 95% CI 0.0%–0.0%）
- 内容级幻觉率 HR_content：100.0%
- 时序幻觉率 rate_deprecated：33.3%
- 不可验率 rate_unverifiable：0.0%
- 分域 HR：
  - COMPANY_LAW：100.0%
  - CRIMINAL_LAW：100.0%

## 逐条核验

| 引注 | 判定 | 子类 | 级别 | 得分 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 《刑法》第232条 | HALLUCINATION | MISATTRIBUTED | FABRICATED | 0.00 | misattributed: candidate text matches article 234 in same law (cov=0% vs cited 232) |
| 《旧公司法》第3条 | HALLUCINATION | TEMPORAL_DEPRECATED | - | 0.00 | temporal hallucination: abolished-law name used after repeal |
| 《公司法》第13条 | HALLUCINATION | NOT_FOUND | - | 0.00 | model cited a non-existent / relocated article |

## 逐条对照（模型输出 vs 已核验基准）

### 《刑法》第232条
- 判定：HALLUCINATION ｜ 子类：MISATTRIBUTED ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：【故意伤害罪】故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。犯前款罪，致人重伤的，处三年以上十年以下有期徒刑；致人死亡或者以特别残忍手段致人重伤造成严重残疾的，处十年以上有期徒刑、无期徒刑或者死刑。本法另有规定的，依照规定。
- 官方原文（基准）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。

### 《旧公司法》第3条
- 判定：HALLUCINATION ｜ 子类：TEMPORAL_DEPRECATED ｜ 级别：- ｜ 得分：0.00
- 模型输出（候选）：规定公司是企业法人。
- 官方原文（基准）：（无可用已核验基准 / 条文未找到）

### 《公司法》第13条
- 判定：HALLUCINATION ｜ 子类：NOT_FOUND ｜ 级别：- ｜ 得分：0.00
- 模型输出（候选）：法定代表人由董事会选举产生。
- 官方原文（基准）：（无可用已核验基准 / 条文未找到）

