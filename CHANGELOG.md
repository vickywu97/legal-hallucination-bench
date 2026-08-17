# Changelog

本项目所有重要变更记录在案。格式参考 [Keep a Changelog](https://keepachangelog.com/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## 2026-08-17 — 新增子项目：中文 To B 指令遵循评测基准（难度门收口）

> 模块位置：`projects/instruction_following_bench/`，与主 `benchmark/` 法条幻觉引擎并列，
> 把作品集从「法律幻觉评测」扩展到「指令遵循质量评测」双评测维度。纯标准库、离线、规则化评分，28 单测全绿。

### 新增（指令遵循基准 + 难度门）
- **中文企业 To B 封闭指令场景**：覆盖格式提取 / 条件规则 / Few-shot 归类 / 多轮约束四类；
  公开 21 题（hard/medium 标注）+ 隐藏 5 题（`hidden_tasks.json`，**gitignored 不入库**，防刷分）。
- **规则化三维评分（无 LLM 裁判）**：`total = 0.3·format + 0.4·content + 0.3·closure`；
  `multi_turn_constraint` 输出 `allowed` 之外 token → 三维全 0（total=0.0）；closure 零容忍（任何 JSON 代码块包裹或多余散文 = 0）。
- **难度门收口（关键设计洞察）**：原"强锚点 ≤0.60 / 弱锚点 ≤0.35"绝对门槛在三维加权评分下**数学上不可达**——
  任何合规结构化输出自带 **0.60 结构地板**（format 1.0 + closure 1.0），强模型只要遵循格式即 ≥0.60。
  重定义为复合 `v2_composite` 口径：弱锚点（GLM-4-Flash）≤ **0.60 结构性地板** + 强弱分离 ≥ **0.30** + 强锚点不得满分（avg<1.0 且 单题违背≥1）。
- **冻结锚点**：强锚点 = max(DeepSeek-V3, Qwen-Max)，弱锚点 = GLM-4-Flash（显式冻结，禁用"跑分最高模型"式漂移定义）。
  `score.py` 顶部 `GATE_SPEC="v2_composite"` 关联注释，与冻结评分口径一并可溯源。
- **真实数据验证（2026-08-17 复跑，PASS）**：DeepSeek-V3 0.936 / Qwen-Max 0.898 / GLM-4-Flash 0.525；
  弱 gap −0.075（≤0.60 地板）、分离 0.411（≥0.30）、强锚点违背 4（≥1，非满分）。`gate: weak_ok=True sep_ok=True strong_discrim=True → PASS`。
- 文档：`projects/instruction_following_bench/README.md`（复合门口径 + 锚点冻结段）、`difficulty_gate_report.md`（达标版含材料性质声明）。
- 适配真实模型采集脚本 `projects/instruction_following_bench/models.py`（stdlib urllib 调 3 个国产模型，环境变量读 key）。

### 实测（指令遵循基准，2026-08-17）
- 漏分题收敛：v2 设计末次 6 题全模型 1.000 → 经任务升级（派生计算 / 规范化 / 反直觉外部知识 / 复合约束例外）后仅剩 ADV1 一题三模型均 1.0，复合口径下不影响门判定，已在报告 §2.1 记为已知边缘题。
- 合规保护：材料为虚构 demo，`demo_note` 标注需核验的法规事实；绝不把虚构当真实排名 / 业绩。

### 改进（P0：值匹配评分 + 死代码清理 + 真实复跑，2026-08-17 收口）
- **评分口径升级（P0，值匹配）**：`score.py` 中 `format_extraction` 的 `content` 由"键名+值逐字段精确匹配"改为「值匹配（不卡键名）+ 数值容错（`_num_eq` 容差）」；`format` 重定义为「输出合法 JSON 对象即合规」（结构性评分），不再因主键名差异清零 content。三维度加权与 0.60 结构地板不变。
- **死代码清理**：移除 `score.py` 中 `_CLOSURE_KEYWORDS`/`_EXPLAIN_RE` 不可达分支（`_extract_json` 改非贪婪优先 + 贪婪回退）；移除 `difficulty_gate.py` 中已无必要的 `fair_format_total()` 与"情景 B"诊断（主键名差异不再导致 content 清零）。
- **任务去重 / 加固**：`config/tasks.json` 中 FN2 与 F3 字节级重复已去重；F5 原与 T5 近克隆已重写；任务集仍为公开 21 题（格式 8 / 条件 8 / 多轮 3 / fewshot 2，19 hard / 2 medium）。
- **models.py 原子写**：答案文件改为 `.tmp` + `os.replace` 原子落盘，避免中断产生半截文件。
- **测试同步**：`tests/test_instruction_following_bench.py` 的"缺字段"用例改为断言"content 下降、format 不变（结构性）"；全量 28 单测绿，并经取证脚本证明值匹配相对旧口径单调不回归（每题 format_extraction 增量 ≥0）。
- **真实复跑（2026-08-17，PASS）**：DeepSeek-V3 **0.956** / Qwen-Max **0.930** / GLM-4-Flash **0.559**；弱 gap −0.041（≤0.60 地板）、分离 0.397（≥0.30）、强锚点违背 2（≥1，非满分）。相对旧口径（0.936 / 0.898 / 0.525）：强锚点因值匹配补回"键名不同但值等价"的答案而上升、强违背由 4 降至 2，门仍 PASS（弱地板 + 分离 + 强非满分三条独立条件均满足）。漏分题仍仅 ADV1（复合门槛下不影响判定）。
- 修复：`difficulty_gate_report.md` 的 ADV1 边缘题注记原硬编码旧弱锚点 0.525，改为动态引用实测弱锚点（现 0.559），报告内部数字已一致。

---

## v1.3 (2026-08-07) — 评测 ground truth 全文本落地 + 管线 10× 提速

> 版本映射：`v1.3` 标签落在本次发布的 HEAD 提交上，涵盖 v1.2 之后的全部工作——
> 《法条库·按需下载版》(Packs 产品) 落地 + 方案B（评测 ground truth 由 212 节点扩容为 8 部法完整官方全文 2327 节点）+ 评测管线约 10× 提速。
> 引擎 CLI / 数据格式（statutes.jsonl）向后兼容，故为 MINOR 版本。

### 重大变更（方案B：评测 ground truth 扩容 212 → 2327 节点）
- **KB 由 212 精选节点扩容为 8 部法完整官方全文（2327 节点）**：`knowledge_base/laws/statutes.jsonl` 现含民法典 1260 / 刑法 505 / 公司法 266 / 税收征管法 94 / 专利法 82 / 企税 60 / 个税 22 / 增值税法 38。212 个 Tier A 专家节点保留原始 `verified_by/at` provenance；其余 2115 个节点在「官方源经专家确认完整 + 逐字提取」准则下升为 verified（来源可信度门禁 `refuse_unverified_ground_truth` 仍有效）。
- **致命回归修复**：`knowledge_base/loader.py` 合并浮点 `article_sort_key` 时 article key 写成 `"232.0"`，而引擎按整数 `"232"` 查找 → 全部引注解析失败。改为整数串 key（`float(sk).is_integer()` 则 `str(int(sk))`）。`build_statute._parse_sort_key` 由整数拼接改十进制（第234条之一 = 234.001），`validate()` 0 错。
- 新增 `scripts/expand_kb_to_full.py`（幂等扩容；修复 `to_arabic` 阿拉伯数字直通，避免 `cn2int('1')→0` 把已阿拉伯化节点清零）；`EXPECT_TOTAL=2327`。
- **6 个测试随方案B 同步**：解析级陷阱（原 NOT_FOUND）随全集覆盖变为内容级（`FABRICATED`/PARTIAL）；时序陷阱（`TEMPORAL_DEPRECATED`）保持不变；`test_kb_coverage` `MIN_TOTAL=2327`、各法地板计数对齐。
- **文档澄清（方案B 关系）**：README / `packs/README.md` / `docs/METHODOLOGY.md` §10 / `docs/PRODUCT_SPEC_法条库按需下载版.md` 明确「评测引擎 ground truth = `statutes.jsonl`（2327 已核验）；`packs/` 仅为同源按领域下载镜像，引擎从不读取 `packs/`」。

### 性能（评测管线 ~10× 提速，产物零变化）
- `benchmark/verify.py`：`normalize()` 记忆化（消除 2327 条文 × 每引注的重复正则）；移除 `content_diff` 中**从未被任何 verdict/指标/产物消费**的 `difflib.SequenceMatcher`（O(n²)，对每一对低覆盖条文计算却不影响任何判定，且不写入 `verifications.jsonl`）→ 产物**字节级不变**。单机 8 题 worker 21.6s → 2.0s；全量 115 题由 5 分钟级降至 30 秒级。
- 新增 `scripts/run_engine_chunked.py`：subprocess 隔离的分块驱动器（每个 worker 独立进程处理一小块、父进程仅合并 + 渲染报告），用于在受限运行环境跑通完整管线；产物与 `benchmark/run.py --offline --input answers.jsonl` 一致。
- 全量测试 **110 绿**（59s，较 198s 提速）。

### 实测（方案B 后真实排行榜，2026-08-07 复刷）
- **HVI（越低越好）全面下降——这是方案B 的预期效果，非模型变好**：ground truth 覆盖完整官方全文后，此前因 KB 稀疏而误判为 `NOT_FOUND` 的有效引注现在正确解析为 `OK`。Qwen-Max 54.5%→**33.3%** / DeepSeek-V3 55.0%→**45.0%** / GLM-4-Flash 55.0%→**45.0%** / DeepSeek-R1 50.0%→**47.6%** / Kimi 64.6%→**54.2%**。
- **CRFI 仍全员 0%**：真实模型失分形态为「引缺失/虚构条号 → NOT_FOUND」与「引对条号但概括改写内容 → PARTIAL/FABRICATED_GENERIC」，而非「条号对、内容错」（硬/软 MISATTRIBUTED 在 115 条中均 0 触发）。内容级幻觉率仍 100%（零逐字合规）；仅 R1 触发时序幻觉（~2.4%，Q7 引已废止《合同法》）。
- **VAT 域 HVI 76.2%→70.6%**（更多 VAT 条文进入 KB 正确解析）；`benchmark/reports/vat_domain_wipeout.html` 已随 `scripts/render_vat_domain.py` 同步刷新。

---

## 2026-08-06

### 修复（运维护栏：`--offline` 静默覆盖真实报告）
- `benchmark/run.py` 新增 `--offline` SAMPLE 覆盖护栏：无 `--input` 时若 `benchmark/reports/` 已存在真实报告（`verifications.jsonl` 非空），则**拒绝**运行并提示改用 `--input answers.jsonl` 评测真实答案或 `--force` 强制覆盖，返回码 1。避免手滑一条命令把 90 条真实复采结果覆盖成玩具 SAMPLE。
- 新增 `--out-dir <dir>`：`--offline` 可将 SAMPLE 演示写入独立目录（如 `sample_demo_reports/`），完全不碰真实报告；CI 烟测与 README 快速开始改用此路径。
- 清理 `benchmark/reports/` 中 3 个历史遗留的 SAMPLE 玩具模型审计报告（`audit_Model-A-good/B-bad/C-partial.md`）——它们与真实 `verifications.jsonl`（仅含真实模型）不一致，属误导孤儿文件。
- `tests/test_offline_guard.py`（8 用例）：护栏拒绝/放行、`--force` 覆盖、空目录放行、`--input` 模式不受护栏限制、`--out-dir` 隔离真实报告且字节级不变。全量测试 102→110 绿。
- `.github/workflows/ci.yml` 烟测改为 `python -S -m benchmark.run --offline --out-dir sample_demo_reports`；`.gitignore` 忽略 `sample_demo_reports/`。
- `README.md` 快速开始：测试计数 83→102；演示命令改为 `--out-dir sample_demo_reports` 并注明护栏语义。

### 新增（v1.2 KB 扩容：实体税法 + 专利法补强 → 212 节点 / 8 部法）
- **KB 由 116/6 法 → 212/8 法**：企业所得税法 EIT_LAW（2018 修正，全文 60 条）、个人所得税法 IIT_LAW（2018 修正，全文 22 条）从用户提供的官方 .doc 逐字提取入库；专利法补强 +14（职务发明/许可/申请日/优先权/授权/无效宣告/强制许可等）→ 30 条。条文经 `textutil` 转换并清洗 Word `\l` 超链接域代码与章标题泄漏。
- **专家核验台账**：`verifications.json` 逐条 `verified`（212/212，100%）；`laws_index.json` 注册 EIT_LAW（order 7）/ IIT_LAW（order 8）。
- **测试集扩至 23 题**：`questions.json` 新增 Q19–Q23 五道 EIT/IIT/专利张冠李戴陷阱——税率25%↔高新15%/小微20%（EIT 4↔28）、不征税↔免税（EIT 7↔26）、免征↔减征（IIT 4↔5）、职务发明↔合作委托（专利 6↔8）、跨法企业所得税免税收入↔个税免征（EIT 26 vs IIT 4）；`in_scope_laws` 扩为 8 部，`_meta.version` 1.1→1.2。
- **护栏放行新法域**：`scripts/generate_answers.py` 系统提示词由"六部"扩为"八部（含企业所得税法、个人所得税法）"，否则新法域引注会落入 NOT_FOUND；Q8 超范围拒绝题枚举同步补齐八部。
- **测试同步**：`tests/test_kb_coverage.py` 地板抬高（MIN_TOTAL 101→200，新增 EIT_LAW/IIT_LAW，PATENT_LAW 12→30）；全量 110 测试绿灯。
- 文档同步：README（6→8 部 / 116→212 节点）、KB_EXPANSION_PLAN（里程碑重标 v1.2=实体税法完成、v1.3=民法典纵深）、KB_V1.2_PREP（标记已落地）更新。

### 实测（v1.2 真实模型排行榜，2026-08-06 复采）
- **复采落地**：设 4 个国产平台 key 后 `--resume --only Q19 Q20 Q21 Q22 Q23` 仅补 5 题（25 次调用）→ 115 条（5×23），重跑管线刷新 `benchmark/reports/`。
- **排行榜（HVI，越低越好）**：R1 **50.0%**（n=42）/ Qwen-Max 54.5%（33）/ DeepSeek-V3 55.0%（40）/ GLM-4-Flash 55.0%（40）/ **Kimi 64.6%**（48，引注最多）。较 v1.1：Qwen-Max 反超 GLM-4-Flash 升至第二，R1 仍以 4.5pt 微弱优势居首。
- **CRFI（张冠李戴率）仍全员 0%——v1.2 未激活**：新增 Q19–Q23 五道 EIT/IIT/专利 张冠李戴陷阱后，5 模型在该 5 题失分形态为「引对正确条号但写概括/改写内容 → PARTIAL/FABRICATED_GENERIC」（Q20/Q21/Q22/Q23）与「引不存在条号/仅法律名 → NOT_FOUND」（Q19/Q20/Q21 的 suspected 启发式），**硬 MISATTRIBUTED 与软探针 SOFT_MISATTRIBUTED 在 115 条中均 0 触发**。结论：真实模型在税法域倾向"编/概括"而非"记混邻居条文"，CRFI 为 0 是评测归因能力的体现（非指标失效），详见 `docs/INTERVIEW_QA.md` Q3。
- **内容级幻觉率全员 100%**：零逐字合规；仅 R1 触发时序幻觉（约 2.4%，Q7 引已废止《合同法》）。`README.md` / `docs/MODEL_VERSIONS.md` / `docs/PROMOTION_DRAFTS.md` / `PORTFOLIO_SUMMARY.md` 同步至 115 条口径。

---

## 2026-08-05

### 新增（软探针 SOFT_MISATTRIBUTED — 诊断用）
- `benchmark/verify.py` 新增 `_soft_misattribution_check()`：在硬 `MISATTRIBUTED` 未触发时，对灰色带（同法 `cov'∈[0.50,0.80)`、跨法 `∈[0.70,0.90)`）做一次宽松比对，若候选与另一条已核验节点落入该带，仅在 `Verification.note` 追加 `SOFT_MISATTRIBUTED`（注明 cov 与"疑似改写式张冠李戴"）。**不影响** `category`/`score`/`diff_level`，**不计入** `crfi`。阈值 `SOFT_MIS_SAME_LAW=0.50`、`SOFT_MIS_CROSS_LAW=0.70`，与硬判定零重叠。动机：真实模型常以改写方式张冠李戴，硬阈值漏判使 CRFI 盲区；软探针把此类暴露到审计报告供二次研判。
- `tests/test_soft_misattribution.py`（6 用例）：改写式同法命中 / 真实部分答对不误报 / 无关文本不误报 / 硬 MISATTRIBUTED 优先不叠加 / VAT 域（引增值税法第11条、改写第10条）/ 单元返回 None。全量测试 96→102 绿。
- `docs/DIFF_POLICY.md` §5.1 增补软探针说明（单真相源阈值表同步）。

### 新增（增值税法域陷阱题 — 激活 CRFI）
- **测试集扩至 18 题**：`questions.json` 新增 Q16–Q18 三道增值税法张冠李戴（同法）陷阱——税率 vs 征收率（第10/11条）、起征点 vs 免税项目（第23/24条）、不得抵扣 vs 留抵退税（第22/21条）。`in_scope_laws` 增 VAT_LAW（共 6 部法），`scope_note` 与护栏说明同步 5→6；`_meta.version` 1.0→1.1。
- **护栏放行增值税法**：`scripts/generate_answers.py` 系统提示词由"五部"扩为"六部（含增值税法）"，否则 VAT 引注会落入 NOT_FOUND；Q8 超范围拒绝题枚举同步补齐六部。
- **生效日门禁（关键）**：增值税法 2026-01-01 施行，三道 VAT 题 `as_of_date` 设为 `2026-01-01`（默认 2025-01-01 会解析为 LAW_NOT_IN_FORCE → NOT_FOUND，使陷阱失效）。
- **回归测试**：新增 `tests/test_vat_traps.py`（10 用例），验证"引对条号、填错条文"确触发 MISATTRIBUTED（同法 cov≥0.80），并锁定生效日门禁与抽取器对《增值税法》别名的识别；全量测试 86→96 绿。
- 文档同步：README / PORTFOLIO_SUMMARY 题量（15→18）、法域（5→6）、节点（101→116）与护栏表述更新；`docs/KB_EXPANSION_PLAN.md` v1.1 标记增值税法域完成。

### 实测（v1.1 复采数据基线，2026-08-05）
- **复采落地**：设 4 个国产平台 key 后 `--resume` 仅补 Q16–Q18（15 次调用）→ 90 条（5×18），重跑管线生成 `benchmark/reports/`。
- **排行榜（HVI，越低越好）**：R1 **50.0%**（n=30）/ GLM-4-Flash 53.8%（26）/ Qwen-Max 56.5%（23）/ DeepSeek-V3 60.0%（30）/ **Kimi 62.5%**（32，引注最多）。五模型全部过半，较首轮（36.8%–60%）整体恶化。
- **增值税法域激活**：VAT_LAW 42 次引注、0 次 EXACT（5 模型全灭，其中 32/42（76.2%）为纯 NOT_FOUND）；失败以"虚构条文序号"（`NOT_FOUND`）为主，CRFI 与软探针 `SOFT_MISATTRIBUTED` 均 0 触发——失效形态是"乱编序号"而非"改写邻居条文"。
- **结论强化**：免费 GLM-4-Flash 仍优于付费 Qwen-Max；付费旗舰 R1 仍居首但优势由 8.2pt 收窄至 3.8pt；全员内容级幻觉率 100%（零逐字合规）；仅 R1 触发时序幻觉（3.3%，Q7 引已废止《合同法》）。`README.md` / `PORTFOLIO_SUMMARY.md` / `leaderboard.html` 同步至 90 条口径。

### 历史（v1.2 准备 → 已于 2026-08-06 落地，212 节点 / 8 部法，见上方 v1.2 条目）
- 新增 `docs/KB_V1.2_PREP.md`：v1.2 扩容执行准备清单。目标在 v1.1（116 节点/6 法）基础上补齐
  Phase 1 剩余三部法——企业所得税法 `EIT_LAW`(+30-40)、个人所得税法 `IIT_LAW`(+20-30)、
  专利法补强 `PATENT_LAW`(+14→30)——实际落地为 EIT 60 + IIT 22 + 专利补强 14 = 212 节点（全文入库，比规划更完整）。
- **阻塞已解除**：用户已提供三部法官方 .doc，逐字提取 + 专家核验已完成。
- **配套产物**：`benchmark/reports/vat_domain_wipeout.html` —— 增值税法域"全灭"独立可视化
  （42 引注 / 0 EXACT / 5 模型全灭 / 失败形态=虚构条文序号）；含分域 HVI 对比条形图（增值税法 76.2% 居首，全 6 域逐字 EXACT 均为 0%）与每模型 VAT 引注次数 n（R1/V3/Kimi 各 10、GLM/Qwen 各 6），可直接贴简历 / 作品集。
- **里程碑表重标建议**：`KB_EXPANSION_PLAN.md` 的 v1.2 当前标为"民法典纵深 ~370"，落地后实际对应
  Phase 1 完成（~230），民法典纵深应顺延为 v1.3（待落地前同步修改）。

## 2026-08-04

### 修复 / 改进
- **门禁与健壮性（P0/P1）**：删除空壳模块 `models/adapters.py`、`benchmark/report.py`；
  README 与 `pyproject.toml` 移除「`--live` 真实模型」误导表述（本工具模型无关，由用户外接模型产出 `answers.jsonl`）；
  `loader.normalize_as_of` 容错 `None`/空/`null`/非 ISO 日期；抽取支持引注区间拆分（如「第20-22条」→ 20/21/22）；
  跨法条张冠李戴检测扫描全部法律、阈值 0.90，并对失效法名走时序门禁。
- **死代码清理（P2）**：`extract._law_regex` 改为按 `law_map` 分桶缓存（原为单全局，对测试 fixture 等会静默漏抽取）；
  删除 `score.content_only` 死参数；删除 `loader` 中永不可达的 `amended_by` 重定位分支；
  审计报告新增 bootstrap 95% CI 行；历史文档归档至 `archive/`。
- **核验归属一致性**：`verifications.json` 全部 99 条 `verified_by` 改为具名签名
  「Vicky Wu (律师/税务师/专利代理师)」，官方来源溯源保留进新增 `source` 字段；
  `verify_kb.REPORT_FILE` 指向 `archive/`，避免运行工具时在 `knowledge_base/` 重新生成游离报告。
- 全量测试由 74 增至 **83 用例**（新增区间引注、跨法条、日期容错、空日期鲁棒性测试）。

### 修复（HVI 与内容级指标分离，2026-08-04）
- **指标修正（关键）**：`score.py` 的 `hr_statutory` 原把内容级失败（FABRICATED/PARTIAL/TRUNCATED/MISATTRIBUTED）一并计入引注幻觉率，与文档"HVI 只考核存在性与时效性"自相矛盾，且使 paraphrase 模型的 HVI 齐刷刷 100%、零区分度。现收紧为仅统计 `NOT_FOUND`+`TEMPORAL_DEPRECATED`（分母=全部 hard 引注）；内容失败单列 `hr_content`；内容子集改用 `diff_level` 非空过滤（顺手修掉 `NOT_FOUND` 被误算进 `hr_content` 的旁支 bug）。`_attrs` 补取 `diff_level`。
- SAMPLE 增 Q4 时序陷阱样本（旧公司法第16条→TEMPORAL_DEPRECATED）演示 HVI；同步更新 `test_verify.py`/`test_pipeline.py` 断言。审计/排行榜标签明确标注 HVI。`docs/METHODOLOGY.md` 同步澄清 `hr_statutory`=HVI（不含内容改写）。全量 83 用例绿。

### 新增（真实模型排行榜工作流）
- **测试集规格 `questions.json`（15 题）**：覆盖 5 部现行法的四类陷阱——基准 / 时序陷阱 / 硬幻觉 / 张冠李戴（同法 + 跨法）。
  每条含 `domain`、`trap_type`、`difficulty`、`as_of_date`、`target{law_code,article_no}`、`prompt`、`expected`，
  并附 `_meta`（评测范围、失效别名、5 法护栏、陷阱分类、双指标定义）。所有 `target` 条文号均经 KB 核验存在（除 Q8=虚构/超范围、Q12=第9999条两条故意的 `NOT_FOUND` 陷阱）。
- **零依赖采集脚本 `scripts/generate_answers.py`**：纯标准库 `urllib` 调用 **5 个纯国产模型**
  （DeepSeek-V3、DeepSeek-R1 付费旗舰、GLM-4-Flash、Qwen-Max、Kimi，全部 OpenAI 兼容协议、总成本≈零），
  `temperature=0` 可复现，从环境变量读 API Key（缺键跳过不报错），写出引擎可直接消费的 `answers.jsonl`
  （`{question_id, model, as_of_date, answer}`）。内置 5 法护栏系统提示词，把"超范围/虚构引用"转化为干净的硬幻觉判定。
  （同日收口：初稿含 GPT-4o-mini / Claude-Haiku 海外模型与 GLM-4，后剔除海外模型、GLM-4 升级为免费的 GLM-4-Flash。）
- **README 新增「真实模型排行榜」章节**：目标、15 题陷阱表、双指标 HVI（引注幻觉率+时序幻觉率）与 CRFI（张冠李戴率）、采集与 `--input` 评分命令（仅需 4 个国产平台 key）、逐题诊断矩阵说明。
- **`.gitignore`**：新增 `answers.jsonl`（个人 API 产物，不入库）。

### 引擎支撑（此前已实现，本版串接）
- `verify.Verification` 新增 `question_id` 字段；`pipeline.audit` 按模型**累加**引注（修复同模型多题被覆盖的 bug）；
  `pipeline.build_report` 新增**逐题诊断矩阵**（Question × Model，✓/✗子类/?/·）。
- 内置 `--offline` SAMPLE 重构为 3 题（Q1/Q3/Q10）× 3 玩具模型，开箱即演示逐题矩阵。

### 改进（评测严谨性收口，2026-08-04）
- **CRFI 指标落地**：`score.py` 计算 `crfi`（内容级 diff 子集中 `MISATTRIBUTED` 占比，专抓「条号对、内容错」）；`pipeline.py` 审计报告与排行榜新增「张冠李戴率(CRFI)」列，`_CAT_ABBR` 增 `MA=张冠李戴`；`test_pipeline.py`/`test_verify.py` 补 CRFI 断言。全量 83 用例绿。
- **10 题改为「逐字引用」提示**：Q1/Q2/Q5/Q6/Q9/Q10/Q11/Q13/Q14/Q15 在 prompt 明确要求逐字引用法条原文，与绝对二元 DIFF_POLICY（逐字一致才 EXACT，否则 0 分）对齐；时序/硬幻觉类陷阱题（Q3/Q4/Q7/Q8/Q12）保持原样。
- **修复内置 SAMPLE Q10 串题**：`run.py` `_SAMPLE_RECORDS` 的 Q10 块原误测刑法232/234，改为正确测试专利法65（gt65 正确 EXACT / gt69 张冠李戴 MISATTRIBUTED / 截断 gt65 FABRICATED）。
- **KB 增补民法典第1182条（100 节点）**：Q15 为跨法张冠李戴（专利法65 vs 民法典1182），原 KB 缺 1182 会导致跨法检测只判通用 FABRICATED、抓不到 MISATTRIBUTED。现补 SEED + verifications.json 具名签名 + 重建 statutes.jsonl（100 verified / 0 unverified）；`test_kb_coverage` 的 `MIN_TOTAL` 99→100。

---

## 2026-08-05

### 修复（评测公平性 + 排行榜可信度）
- **Q9 公平性 bug 修复（关键）**：原 Q9 目标写《公司法》第20条，但 2024 新《公司法》已把"法人人格否认"移至**第23条**；KB 旧节点存的是旧序号第20条，导致正确引用新法第23条的模型反而被判 `NOT_FOUND`（引擎 note 自标 "relocated article"），与 Q4 用新序号第15条自相矛盾。修复：KB 新增 `COMPANY_LAW 第23条` 节点（新法 3 款原文，含横向否认与一人公司）+ verifications.json 具名签名；Q9 目标与 `correct_citation` 改为第23条；旧第20条节点 notes 修正为"股东权利滥用（新法第20条）"。KB 增至 **101 节点 / 101 verified**；`test_kb_coverage` 的 `MIN_NODES[COMPANY_LAW]` 15→16、`MIN_TOTAL` 100→101。修复后 R1 的 HVI 由 42.1% 降至 **36.8%**（正确引用第23条者不再被误罚）。
- **排行榜排名修复**：`_write_leaderboard` 原按 HVI 升序但未排除 `n_citations==0`，导致 Kimi（0 引注、HTTP 400 全失败）被排到第 1。改为 `n_citations==0` 的模型置末位并标注"无数据"；逐题矩阵模型排序同步修正。

### 真实模型排行榜（5 国产模型，2026-08-05 采集）
- HVI：R1 **36.8%** / GLM-4-Flash 45.0% / Qwen-Max 47.1% / **Kimi 50.0%（引注数最多 22 条）** / DeepSeek-V3 60.0%（全员内容级幻觉率 100%、CRFI 0%；仅 R1 触发时序幻觉 5.3%，在 Q7 引已废止《合同法》第113条）。
- Kimi 采集完成（此前因 HTTP 400 暂缺）：`generate_answers.py` 对 `kimi-k2.6` 改发最小载荷（`model`+`messages`，去掉被端点拒绝的 `temperature`/`stream`）首调即通；长推理题 Q6/Q13 原读取超时，已将 `HTTP_TIMEOUT` 60→180s 后 `--resume` 补跑成功，最终 75 条（5×15）全部有效。
- README「真实模型排行榜」章节更新：5 模型完整排行榜表（Kimi 居中 50.0%）+ 关键发现同步为 5 模型口径；`PORTFOLIO_SUMMARY.md` 同步更新。排行榜权威产物见 `benchmark/reports/leaderboard.md`（含逐题诊断矩阵）。

---

## 2026-08-03

### 新增
- **初始发布 v1.0**：离线优先、零运行时依赖（`python -S` 可跑）的法律法条幻觉评测基准。
  - 抽取引擎 `benchmark/extract.py`、内容级二元 diff 与门禁 `benchmark/verify.py`、
    幻觉率聚合与 bootstrap CI `benchmark/score.py`、端到端管线 `benchmark/pipeline.py`。
  - 专家核验知识库 KB：99 节点 / 99 verified / 0 unverified，纯现行法；
    `DEPRECATED_LAW_NAMES` 单一真相源登记 10 部失效法名陷阱。
  - `--offline` / `--verify-demo` 开箱演示；`demo/` 严格内容级评测闭环。
  - GitHub Actions CI（py 3.8/3.11/3.12，离线跑测试与 `--offline`）。
  - 文档：`README.md`、`docs/DIFF_POLICY.md`、`docs/METHODOLOGY.md`、`docs/KB_EXPANSION_PLAN.md`、`CONTRIBUTING.md`。

### 文档 / CI
- README 增加 CI / Python / License 徽章（三绿布局）。
- CI actions 升级至 v7（Node 24），消除 Node 20 弃用告警；`pip` 升级至最新。
