# Contributing / 贡献指南

欢迎律师、法律科技同行、开源社区贡献。本基准的核心资产是**知识库**与**陷阱探针**，二者都需要领域专业性。

## 1. 贡献法条快照（knowledge_base/laws/*.json）

- 法条是公开政府信息，不受著作权保护；请在 `source_url` 填官方来源（flk.npc.gov.cn），`source_accessed_at` 填策展日期。
- **必须带版本化**：每条文记录 `content` + `effective_from` + `effective_until` + `amended_by`（如被后续修订单独替换）。
- KB 文件为 **JSON**（YAML 严格子集）以保证 loader 零依赖、完全离线可跑。提交前运行 `python -m unittest discover -s tests` 确认快照完整性通过。
- 受网络限制无法 `pip install` 时，本项目**无运行时第三方依赖**（stdlib 即可），直接用 `python -m unittest` 跑测试，无需 pytest。

## 2. 贡献陷阱探针（benchmark/probes/arm_b_*）

- 每条探针是 YAML：`{probe_id, type, prompt, ground_truth, expected_verdict, domain}`。
- `ground_truth` 必须由构造可知，**不依赖人工标注**。
- 探针类型（见 archive/MVP_DESIGN.md §3）：B1 废止条文 / B2 虚构法释号 / B3 虚构指导案例号 / B4 内容错引 / B5 时间错位 / B6 虚构法院。
- 请附带"为什么这是幻觉"的简短说明，便于审核。

## 3. 贡献开放题标注（benchmark/probes/arm_a_open）

- Arm A 是开放题，需专家标注引注真伪；请附标注依据。

## 4. 审核流程

- PR 经维护者审核（重点：ground truth 正确性、是否引入可作弊的公开实例）。
- 部分探针作为**隐藏测试集**不随 repo 发布，仅本地运行防作弊。

## 5. 代码规范

- 纯 Python，禁止引入 C 扩展依赖（保证离线可跑）。
- 所有 KB 读取走 `knowledge_base/loader.py`，勿硬编码路径。
