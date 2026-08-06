# 模型版本追踪 · Model Version Tracker

> 用途：记录 benchmark 中每次真实采集所用的模型版本、API 端点、日期与参数。
> 当同一模型发布新版本后重跑对比时，本文件是版本锚定依据。
> 格式：每次采集追加一个新 section，不改动历史记录。

---

## 采集 #1: v1.1 真实模型基准（2026-08-05）

### 采集概况
- **日期**：2026-08-05（北京时间）
- **题目集**：`questions.json` v1.1（18 题，6 法域，含 Q16–Q18 增值税法）
- **系统提示词**：`scripts/generate_answers.py` 内 SYSTEM_PROMPT（限制仅可引用 6 部现行法，含增值税法）
- **温度参数**：`temperature=0`（全模型，保证可复现）
- **采集脚本**：`python -S scripts/generate_answers.py --out answers.jsonl --resume`
- **输出文件**：`answers.jsonl`（90 条记录）

### 模型明细

| # | 模型名（API 名称） | 提供方 | 费用类型 | API 端点 | 备注 |
|---|---|---|---|---|---|
| 1 | **DeepSeek-R1** (`deepseek-reasoner`) | DeepSeek | 付费旗舰 | `api.deepseek.com/v1` | 推理模型，响应较长 |
| 2 | **DeepSeek-V3** (`deepseek-chat`) | DeepSeek | 免费基础 | `api.deepseek.com/v1` | 主力对话模型 |
| 3 | **GLM-4-Flash** (`glm-4-flash`) | 智谱 AI (Zhipu) | 免费 | `open.bigmodel.cn/api/paas/v4` | 免费模型，性价比高 |
| 4 | **Qwen-Max** (`qwen-max-2025-01-25`) | 阿里云 (DashScope) | 付费 | `dashscope.aliyuncs.com/compatible-mode/v1` | 旗舰推理模型 |
| 5 | **Kimi** (`kimi-k2.6`) | 月之暗面 (Moonshot) | 付费 | `api.moonshot.cn/v1` | 长上下文模型 |

### 采集异常记录
- **Kimi**：接口对 `temperature`/`stream` 参数返回 HTTP 400 → 改为最小载荷（仅 `model` + `messages`）后首调通过。
- **Kimi**：长推理题 Q6/Q13 读取超时（默认 120s）→ 提至 180s 后补跑成功。
- **DeepSeek-R1**：推理链较长，单题响应耗时 15-60s，在正常范围内。

### 评测结果摘要
| 模型 | HVI | 引注数 | 内容幻觉率 | 时序幻觉率 | CRFI |
|---|---|---|---|---|---|
| DeepSeek-R1 | 50.0% | 30 | 100% | 5.3% | 0% |
| GLM-4-Flash | 53.8% | 26 | 100% | 0% | 0% |
| Qwen-Max | 56.5% | 23 | 100% | 0% | 0% |
| DeepSeek-V3 | 60.0% | 30 | 100% | 0% | 0% |
| Kimi | 62.5% | 32 | 100% | 0% | 0% |

---

## 版本对比规则（未来采集时遵循）

1. **同一模型不同版本对比**：例如 DeepSeek-V3 → V3.1 → V4，使用完全相同题目集 + 同参数重新采集，记录在此文件中。
2. **新增模型**：按同一 SYSTEM_PROMPT + 同一题目集采集，追加新 section，不覆盖历史数据。
3. **题目集版本**：若题目集从 18 题扩展，需注明各模型跑的是哪个版本的题目集（避免跨版本对比失公允）。
4. **API 变更**：若模型 API 名称变更（如 `qwen-max-2025-01-25` → `qwen-max-2025-06-01`），标注为"版本升级"而非"同一模型"。
5. **温度参数**：始终使用 `temperature=0`（除非刻意测试随机性对引注的影响，需特别标注）。

---

## 计划中的下一批采集

| 模型 | 接入方式 | 状态 |
|---|---|---|
| GPT-4o | SiliconFlow / Poe 代理 | 待选平台 |
| Claude 3.5 Sonnet | SiliconFlow / Poe 代理 | 待选平台 |
| 通义千问 Qwen3 (新版本) | DashScope 直接调用 | 待模型发布 |
