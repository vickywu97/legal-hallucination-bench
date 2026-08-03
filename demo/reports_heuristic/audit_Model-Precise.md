# 审计报告：Model-Precise

- 引注数：2
- 法条幻觉率 HR_statutory：100.0%
- 内容级幻觉率 HR_content：100.0%
- 时序幻觉率 rate_deprecated：0.0%
- 不可验率 rate_unverifiable：0.0%
- 分域 HR：
  - CIVIL_CODE：100.0%
  - CRIMINAL_LAW：100.0%

## 逐条核验

| 引注 | 判定 | 子类 | 级别 | 得分 | 说明 |
| --- | --- | --- | --- | --- | --- |
| 《刑法》第232条 | HALLUCINATION | PARTIAL | FABRICATED | 0.00 | partial (non-exact): 100% of ground clauses present; counts as HALLUCINATION |
| 《民法典》第584条 | HALLUCINATION | PARTIAL | FABRICATED | 0.00 | partial (non-exact): 100% of ground clauses present; counts as HALLUCINATION |

## 逐条对照（模型输出 vs 已核验基准）

### 《刑法》第232条
- 判定：HALLUCINATION ｜ 子类：PARTIAL ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。。在本案中，被告持刀行凶，其行为完全符合该条规定，应当依法严惩。
关于违约损害赔偿，根据
- 官方原文（基准）：【故意杀人罪】故意杀人的，处死刑、无期徒刑或者十年以上有期徒刑；情节较轻的，处三年以上十年以下有期徒刑。

### 《民法典》第584条
- 判定：HALLUCINATION ｜ 子类：PARTIAL ｜ 级别：FABRICATED ｜ 得分：0.00
- 模型输出（候选）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。。这一规则确立了可预见性限制原则。
- 官方原文（基准）：当事人一方不履行合同义务或者履行合同义务不符合约定，造成对方损失的，损失赔偿额应当相当于因违约所造成的损失，包括合同履行后可以获得的利益；但是，不得超过违约一方订立合同时预见到或者应当预见到的因违约可能造成的损失。

