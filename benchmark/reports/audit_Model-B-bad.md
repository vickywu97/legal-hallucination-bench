# 审计报告：Model-B-bad

- 引注数：4
- 引注幻觉率 HVI(hr_statutory)：50.0% （bootstrap 95% CI 0.0%–100.0%；仅统计存在性/时序性幻觉）
- 内容级幻觉率 HR_content：100.0%（仅逐字 diff 子集；反映是否照抄法条）
- 时序幻觉率 rate_deprecated：25.0%
- 不可验率 rate_unverifiable：0.0%
- 分域 HR：
  - CIVIL_CODE：0.0%
  - COMPANY_LAW：100.0%
  - CRIMINAL_LAW：0.0%

## 逐条核验

| 题号 | 引注 | 判定 | 子类 | 级别 | 得分 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | 《民法典》第584条 | HALLUCINATION | PARTIAL | FABRICATED | 0.00 | partial (non-exact): 100% of ground clauses present; counts as HALLUCINATION |
| Q3 | 《公司法》第13条 | HALLUCINATION | NOT_FOUND | - | 0.00 | model cited a non-existent / relocated article |
| Q4 | 旧公司法第16条 | HALLUCINATION | TEMPORAL_DEPRECATED | - | 0.00 | temporal hallucination: abolished-law name used after repeal |
| Q10 | 《刑法》第232条 | HALLUCINATION | MISATTRIBUTED | FABRICATED | 0.00 | misattributed: candidate text matches article 234 in same law (cov=0% vs cited 232) |

## 逐条对照（模型输出 vs 已核验基准）

### 《民法典》第584条
- 判定：HALLUCINATION ｜ 子类：PARTIAL ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。（另据相关司法解释补充如下……）
- 官方原文（基准）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。

### 《公司法》第13条
- 判定：HALLUCINATION ｜ 子类：NOT_FOUND ｜ 级别：- ｜ 得分：0.00
- 模型输出（候选）：法定代表人由董事会选举产生。
- 官方原文（基准）：（无可用已核验基准 / 条文未找到）

### 旧公司法第16条
- 判定：HALLUCINATION ｜ 子类：TEMPORAL_DEPRECATED ｜ 级别：- ｜ 得分：0.00
- 模型输出（候选）：公司为股东提供担保须经股东会决议。
- 官方原文（基准）：（无可用已核验基准 / 条文未找到）

### 《刑法》第232条
- 判定：HALLUCINATION ｜ 子类：MISATTRIBUTED ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：【故意伤害罪】故意伤害他人身体的，处三年以下有期徒刑、拘役或者管制。犯前款罪，致人重伤的，处三年以上十年以下有期徒刑；致人死亡或者以特别残忍手段致人重伤造成严重残疾的，处十年以上有期徒刑、无期徒刑或者死刑。本法另有规定的，依照规定。
- 官方原文（基准）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。

