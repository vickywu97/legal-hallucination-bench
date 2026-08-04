# 审计报告：Model-C-partial

- 引注数：3
- 法条幻觉率 HR_statutory：100.0% （bootstrap 95% CI 0.0%–0.0%）
- 内容级幻觉率 HR_content：100.0%
- 时序幻觉率 rate_deprecated：0.0%
- 不可验率 rate_unverifiable：0.0%
- 分域 HR：
  - CIVIL_CODE：100.0%
  - COMPANY_LAW：100.0%
  - CRIMINAL_LAW：100.0%

## 逐条核验

| 题号 | 引注 | 判定 | 子类 | 级别 | 得分 | 说明 |
| --- | --- | --- | --- | --- | --- | --- |
| Q1 | 《民法典》第584条 | HALLUCINATION | PARTIAL | FABRICATED | 0.00 | partial (non-exact): 50% of ground clauses present; counts as HALLUCINATION |
| Q3 | 《公司法》第13条 | HALLUCINATION | NOT_FOUND | - | 0.00 | model cited a non-existent / relocated article |
| Q10 | 《刑法》第232条 | HALLUCINATION | PARTIAL | FABRICATED | 0.00 | partial (non-exact): 50% of ground clauses present; counts as HALLUCINATION |

## 逐条对照（模型输出 vs 已核验基准）

### 《民法典》第584条
- 判定：HALLUCINATION ｜ 子类：PARTIAL ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益
- 官方原文（基准）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。

### 《公司法》第13条
- 判定：HALLUCINATION ｜ 子类：NOT_FOUND ｜ 级别：- ｜ 得分：0.00
- 模型输出（候选）：法定代表人由公司章程规定。
- 官方原文（基准）：（无可用已核验基准 / 条文未找到）

### 《刑法》第232条
- 判定：HALLUCINATION ｜ 子类：PARTIAL ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑
- 官方原文（基准）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。

