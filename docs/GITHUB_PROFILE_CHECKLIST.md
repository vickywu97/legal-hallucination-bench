# GitHub 仓库门面清单（对外前必做）

> 目的：让三个仓库在被人点开 / 分享链接时，第一时间显得"专业、可信、有作品集感"。
> 操作位置：全部在 GitHub **网页端**（你点，AI 推不上去）。预计 15 分钟。
> 顺序建议：先三个仓库各自设好 → 再设 profile 主页 Pinned。

---

## 1. legal-hallucination-bench（地基 / 评测基准）

**About 栏（右侧 About → Edit）**
- Description：`中文法律引注幻觉基准 · 离线零依赖 · 2327 条专家核验法条 · 5 国产模型真实跑分`
- Website：留空或填 profile 主页 `https://github.com/vickywu97`
- Topics（点 Add topics，输入后回车）：
  `llm-evaluation` `hallucination` `legal-ai` `benchmark` `chinese-law` `law` `tax-law` `patent` `ai-safety` `open-source` `python` `reproducible-research` `prompt-engineering` `ai-product` `legal-tech`

**Social preview 图（Settings → General → Social preview → Upload）**
- 用 `docs/portfolio_architecture.png`（已生成，1280×640 架构图，含 KB→引擎→双消费者+三证护城河），最完整地代表"这是个作品集地基"。
- 备选：用 `benchmark/reports/vat_domain_wipeout.html` 渲染的"5 模型全灭"图（钩子更强，但只讲基准不讲产品）。

**Pinned**：在自己 profile 主页把本仓库 Pin 为第一个（见第 4 节）。

---

## 2. compliance-triangle（产品）

**About 栏**
- Description：`法律/税务/IP 三域合规助手 · 复用同一套校验引擎 · 对 AI 法条引注做 🟢🟡🔴 三层核验 · 离线零依赖`
- Website：`https://github.com/vickywu97/legal-hallucination-bench`（反向导流到地基，说明数据同源）
- Topics：
  `legal-ai` `compliance` `tax` `ip` `hallucination-detection` `ai-product` `llm-evaluation` `verification` `open-source` `python` `zero-dependency` `legal-tech`

**Social preview 图**
- 用 `docs/dashboard_preview.png`（真实仪表盘截图，🟢🟡🔴 卡片，最有"产品感"）。

---

## 3. vickywu97（profile 主页 / 作品集人脸）

**Profile 设置（右上角头像 → Settings → Profile）**
- Name：`Vicky Wu`（或中文名，保持一致）
- Pronouns：可选
- Bio（一句话人设）：
  `律师 · 税务师 · 专利代理师 → AI 法律产品经理 ｜ 定义并量化 AI 质量（评测基准 + 合规产品）｜ 开源作品集👇`
- Location：`China`（或城市）
- Company / Website：可填 `legal-hallucination-bench` 或留空
- Link（加一个）：`https://github.com/vickywu97/legal-hallucination-bench`

**Pinned repositories（主页 → Customize pins / 编辑引脚）**
- 钉住 3 个：① legal-hallucination-bench ② compliance-triangle ③ 不需要第三个（profile 本身无 repo）。若想钉 2 个即可。
- 钉的时候勾选 "Show README" 可让卡片显示 README 首屏，更有料。

**README（已建并推送 `vickywu97-profile`）**
- 确认 github.com/vickywu97 已显示该 README（双仓库卡片 + 架构图 + 三证护城河）。
- 架构图用的 raw URL 指向 bench 的 `portfolio_architecture.svg` 与 ct 的 `dashboard_preview.png`，需两个仓库均已 push（✅ 已完成）才会显示。

---

## 4. 校验清单（做完打勾）

- [ ] bench：About + Topics（15 个）+ Social preview（架构图 PNG）
- [ ] ct：About + Topics + Social preview（dashboard_preview.png）
- [ ] profile：Bio 人设句 + Link + Pinned 两个仓库（Show README）
- [ ] 浏览器隐身窗口打开三个仓库 URL，确认图片/README 正常渲染、无破图

> 提示：Social preview 用 SVG 直接传可能不被 GitHub 接受，先用浏览器把 SVG 打开截图成 PNG（或我之前已帮你生成的 `dashboard_preview.png` 可直接用；架构图 PNG 需要你截一张，或用 Chrome 在本地打开 `portfolio_architecture.svg` 截图）。
