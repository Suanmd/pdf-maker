---
name: pdf-maker
description: This skill should be used when producing Chinese-language PDF reports or books from LaTeX (xelatex + ctexrep + xeCJK), especially multi-chapter works that need a controlled single-chapter-then-merge workflow with URL liveness verification, overflow checks, and cross-chapter label de-duplication. Trigger on requests such as "write/compile a PDF report", "generate a typeset Chinese book from research material", or "turn these notes into a LaTeX PDF".
agent_created: true
---

# pdf-maker

中文 LaTeX 报告/书籍工程化 skill。基于 `xelatex + ctexrep + xeCJK`，把零散章节稳定产出为排版合规的中文 PDF。

## 何时使用

- 产出中文 PDF 报告、白皮书、调研汇编，或多章节书籍。
- 需要受控流程：单章独立编译 → 整书合并。
- 需要 URL 联网验活、编译日志体检、跨章 `\label` 去重等质量关卡。

## 前置要求

- **TeX Live 2022+**（含 `xelatex`、`ctexrep`、`xeCJK`）。
- **Python 3.10+**：脚本仅用标准库，**无需 `pip install` 任何包**。
- **`pdfinfo`**（poppler，通常随 TeX Live 附带）：用于 PDF 元数据/页数校验，可选。

## 安装

把本 skill 目录放到任意 skill 加载路径，装在哪都不影响使用（脚本通过 CWD 定位书稿项目）：

- 用户级：`~/.workbuddy/skills/pdf-maker/`
- 项目级：`<project>/.workbuddy/skills/pdf-maker/`

## 书稿目录结构

```
<PROJECT>/
├── main.tex              # 整书主控（从 assets/templates/main.tex 复制而来）
├── materials.json        # 章节 ↔ 素材索引（track_materials.py 维护）
├── figures/              # 图片资源
├── 第1章/第1章.tex       # 每章一个目录 + 一个 .tex（\chapter 作顶层）
├── 第2章/第2章.tex
└── ...
```

## 核心工作流（双模式）

- **单章独立编译**：每章用 `\chapter`，走完整闭环（写 → 预处理 → 校验 → 编译 → 体检）→ 验证 → 下一章。
- **整书合并**：所有章节用 `\chapter`，主控 `main.tex` 用 `\input{第N章/第N章}` 装入 → 出 `main.pdf`。

两种模式混用 = bug。一个书稿只选其一作为最终交付形态（推荐：单章开发 + 整书合并）。

## 单章 SOP（概要）

> 完整命令、参数、踩坑与模板说明见 **`references/SOP.md`**。

1. **读素材**：`reader.py index/verify <素材 report.md>`（三阶段：index → chunk → verify，5 字段全过才算读完）。
2. **写章节**：`第N章/第N章.tex`（含 `\chapter{}` 与章末 `thebibliography`）。
3. **预处理**：`fix.py N`（生成 `chN.tex` + `_tmp.tex`；URL 规范化、TikZ 图宽上限）。
4. **结构校验**：`check.py N` + `check_balance.py N`（字数/层级/引用闭合，软告警不阻断）。
5. **联网验活（强制）**：`verify_urls.py N`（exit 0 继续 / 1 失效链接必改 / 2 离线须重跑）。
6. **编译**：`cd 第N章/` 内执行 `xelatex _tmp.tex` **两次**（`\input{chN.tex}` 依赖此路径）。
7. **日志体检**：`check_overflow.py _tmp.log`（拦 Overfull / Missing character / 断链 / Fatal）。
8. **清理落盘**：`cleanup.py N`（复制 `_tmp.pdf → 第N章.pdf`，中间文件归档到 `_tmp_old/`）。
9. **更新素材追踪**：`track_materials.py update <PROJECT> 第N章 <size> <lines> <chunks>`。

## 整书合并 SOP（概要）

1. `fix_labels.py <PROJECT>`（跨章重复 `\label` 去重）。
2. 在项目根执行 `xelatex main.tex` **两次**。
3. `check_overflow.py main.log`。
4. `pdfinfo main.pdf` 校验标题/作者元数据。
5. 收尾：保留 `main.tex` 与 `main.pdf`，删 `main.aux/log/out/toc`。

## 红线（强制）

- **单一真源**：章节 `.tex` 禁止保留 `.bak` 副本；模板 preamble 只在 `assets/templates/_tmp.tex`（单章）与 `assets/templates/main.tex`（整书），两者同步关键补丁，不允许在 `fix.py` 内再内联副本（双源漂移）。
- **URL 必须真实可访问**：所有 `\href{}` 链接须通过 `verify_urls.py` 验活（LIVE）；出现 DEAD 必须替换为真实可达源，不得虚构或保留死链。
- **参考文献闭合**：每章 `bibitem` 键加章号前缀（`c1r1`、`c2r3`…）；`\cite` 必须有对应 `\bibitem`。
- **编译路径强约束**：单章必须 `cd 第N章/` 内编译；整书必须在项目根编译（本机 xelatex 不把主文件目录加入搜索路径）。
- **内容通用化**：文档与示例不出现具体项目名、绝对路径、具体日期。

## 脚本清单

| 脚本 | 职责 |
|------|------|
| `scripts/fix.py` | 单章预处理：URL 规范化 + 图宽上限 + 生成 `chN.tex`/`_tmp.tex` |
| `scripts/verify_urls.py` | **【强制】** 联网验活：逐 URL 检测可达性（exit 0/1/2） |
| `scripts/check.py` | 内容结构统计（字数 / 层级 / 元素） |
| `scripts/check_balance.py` | 结构 / 引用均衡性检查（软告警） |
| `scripts/check_overflow.py` | 编译日志体检（硬卡口：溢出 / 断链 / 缺字符） |
| `scripts/cleanup.py` | 成品落盘 + 中间文件归档（移动而非删除） |
| `scripts/fix_labels.py` | 跨章重复 `\label` 去重 |
| `scripts/reader.py` | 素材强制阅读三阶段校验（index / chunk / verify / toc） |
| `scripts/track_materials.py` | 章节 ↔ 素材阅读状态追踪 |
| `scripts/common.py` | 各脚本共享工具（路径定位 / 编码 / 文本统计），**不被单独运行** |

所有 CLI 均支持 `-h` 查看准确参数与示例。

## 资源

- `assets/templates/main.tex` — 整书主控模板（含扉页/目录/页眉页脚/参考文献降级补丁）。
- `assets/templates/_tmp.tex` — 单章编译 preamble 唯一真源。
- `assets/examples/chapter_init_notes_template.md` — 章节阅读笔记模板。
- `references/SOP.md` — **完整 SOP、命令参考、模板说明、URL 写法、踩坑速查**（本文件的详细版）。

## 与其他组件的边界

- **协同**：素材采集工具提供素材 → 本 skill 整章节 → 后处理 PDF 工具（如需）。
- **不重复**：SVG/HTML 图表生成、编辑既有 PDF、创建 skill 自身。
