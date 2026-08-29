---
name: pdf-maker
description: 中文 LaTeX 报告/书籍工程化工具（xelatex + ctexrep + xeCJK）。提供单章独立编译与整书合并双模式，并在关键节点设置质量关卡：素材强制阅读、URL 联网验活、编译日志体检、跨章 \label 去重。适用于「把零散章节稳定产出为排版合规的中文 PDF」「写一份像样的中文技术报告/白皮书/调研汇编/多章书籍」「从这些素材生成 LaTeX PDF」等请求。
agent_created: true
---

# pdf-maker

中文 LaTeX 报告/书籍工程化工具。基于 `xelatex + ctexrep + xeCJK`，把零散章节稳定产出为排版合规的中文 PDF。

本技能的核心代码是一个标准 Python 包 `pdfmaker`（位于 `src/pdfmaker/`），所有能力通过
`python -m pdfmaker <子命令>` 或安装后的 `pdfmaker` 命令调用。**完整安装、命令参考、URL 写法、
参考文献/标签约定、模板说明见 [`README.md`](README.md)**；本文件只给出触发、红线与流程概要。

## 何时使用

- 产出中文 PDF 报告、白皮书、调研汇编，或多章节书籍。
- 需要受控流程：单章独立编译 → 整书合并。
- 需要 URL 联网验活、编译日志体检、跨章 `\label` 去重等质量关卡。

## 前置要求

- **TeX Live 2022+**（含 `xelatex`、`ctexrep`、`xeCJK`）。
- **Python 3.10+**：工具仅用标准库，**无需 `pip install` 任何包**。
- **`pdfinfo`**（poppler，通常随 TeX Live 附带）：用于 PDF 元数据/页数校验，可选。

## 安装

把本技能目录放到任意技能加载路径（装在哪都不影响使用，工具通过 CWD 定位书稿项目）：

- 用户级：`~/.workbuddy/skills/pdf-maker/`
- 项目级：`<project>/.workbuddy/skills/pdf-maker/`

若想用 `pdfmaker` 命令而非 `python -m pdfmaker`，在技能目录内 `pip install -e .` 即可。

## 书稿目录结构

```
<PROJECT>/
├── main.tex              # 整书主控（从包内模板 pdfmaker.templates/main.tex 落地）
├── materials.json        # 章节 ↔ 素材阅读状态索引（track 维护）
├── figures/              # 图片资源
├── 第1章/第1章.tex        # 每章一个目录 + 一个 .tex（\chapter 作顶层）
├── 第2章/第2章.tex
└── ...
```

也可直接 `python -m pdfmaker scaffold <dir>` 生成上述骨架。

## 核心工作流（双模式）

- **单章独立编译**：每章用 `\chapter`，走完整闭环（读素材 → 写 → 预处理 → 校验 → 编译 → 体检）→ 验证 → 下一章。
- **整书合并**：所有章节用 `\chapter`，主控 `main.tex` 用 `\input{第N章/第N章}` 装入 → 出 `main.pdf`。

两种模式混用 = bug。一个书稿只选其一作为最终交付形态（推荐：单章开发 + 整书合并）。

## 单章 SOP（精确步骤）

每一步对应一个子命令，按此顺序执行：

1. **读素材**：`python -m pdfmaker reader ingest <素材 .md 路径>`（一步完成 index → chunk → verify 三阶段，5 字段全过才算读完）。
2. **写章节**：直接跑 `python -m pdfmaker chapter N --material 素材-第N章.md`——**章文件缺失时会自动生成合规富骨架**（内嵌可编译三线表 / TikZ 图 / `codeblock` 示例与预填文献，作者复制即用），从源头杜绝样式漂移（详见下方「素材→章节脚手架」）。若章文件已存在则跳过生成、不覆盖。无需记忆 `--scaffold` 开关。
3. **预处理**：`python -m pdfmaker fix N`（读包内 `templates/_tmp.tex`，`normalize_text()` 做 URL 规范化 + TikZ 图宽上限；写出 `chN.tex` 与 `_tmp.tex`）。
4. **结构校验**：`python -m pdfmaker check N` + `python -m pdfmaker balance N`（字数/层级/引用闭合，软告警不阻断）。
5. **联网验活（强制）**：`python -m pdfmaker verify N`（exit 0 继续 / 1 失效链接必改 / 2 离线须重跑）。
6. **编译**：在 `第N章/` 目录内执行 `xelatex _tmp.tex` **两次**。
7. **日志体检**：`python -m pdfmaker overflow _tmp.log`（拦截 Overfull / Missing character / 断链 / Fatal）。
8. **清理落盘**：`python -m pdfmaker cleanup N`（复制 `_tmp.pdf → 第N章.pdf`，中间文件归档到 `_tmp_old/`）。
9. **更新素材追踪**：`python -m pdfmaker track update <PROJECT> 第N章 <size> <lines> <chunks>`。

## 整书合并 SOP（精确步骤）

统一用 `build` 一键完成。它依次调用：

1. **前置表格自动修复** —— `main.tex` 前置部分（序言/术语表）的顶格整宽表格若缺 `\noindent`，`build` 会在 `_build` 副本自动补入（仅副本生效、源文件不变）。
2. `labels <PROJECT>` —— 跨章重复 `\label` 去重（有跨章引用则中止）。
3. `xref <PROJECT>` —— 合并前静态预检（文字「第N章」章号越界 / 跨章 `\ref`，阻断则中止）。
4. 对每个章节调用与单章**完全相同**的 `normalize_text()`，写入 `_build/`，重写 `main.tex` 的 `\input` 指向归一副本。
5. 在 `_build/` 内 `xelatex` 两遍。
6. `overflow _build/main.log`（硬卡口，Overfull 给根因建议）。
7. 通过则复制 `_build/main.pdf → <PROJECT>/main.pdf`，并清理 `_build/`（删除失败留 `_build_bak*` 并告警）。

命令：

```bash
cd <PROJECT>
python -m pdfmaker build .                 # 合并（含 labels + xref + 规范化 + 编译 + 体检）
python -m pdfmaker build . --verify        # 合并前额外联网验活全书 URL
python -m pdfmaker build . --no-preflight  # 跳过 xref 预检（不推荐）
```

两档能力：

1. **单章从素材生成（推荐，已接进标准 SOP）**
   ```bash
   # 标准 SOP：章文件缺失时自动生成合规富骨架（无需 --scaffold）
   python -m pdfmaker chapter N --material 素材-第N章.md
   # 等价显式写法（兼容保留）：
   python -m pdfmaker scaffold chapter N --material 素材-第N章.md
   ```
   解析素材得到：章标题（首个 Markdown 标题）、二级节结构（`## ` 自动映射为 `\section`）、全部 URL（预填 `\bibitem{cNrK}\href{URL}{...}`，并在引言给引用示例保证 `bibitem==cite` 开箱一致）。`chapter N --material` 在章文件缺失时已默认触发上述生成，使写作流水线自我引导。

2. **整书初始化（旧用法，向后兼容）**
   ```bash
   python -m pdfmaker scaffold <dir> --chapters N   # 生成整书骨架
   ```

生成的单章骨架包含：头部强制约定注释（引用键前缀 `cN`、标签前缀 `cN`、禁止跨章 `\ref`、字形规则）、可直接编译的**合规示例节**（三线表表题在上 + TikZ 图题在下 + `codeblock` 全 ASCII 注释）、按素材预生成的 `\section`、以及预填文献的 `thebibliography`。该示例节标题醒目提示"撰写后删除"，作者删掉即可，不会带进成品。

**非破坏性**：`scaffold chapter` 与 `chapter --scaffold` 一律不覆盖已存在的章文件（除非 `--force`）。

## 设计约束（红线）

- **单一真源**：章节 `.tex` 禁止保留 `.bak` 副本；preamble 只在 `templates/_tmp.tex`（单章）与 `templates/main.tex`（整书），两者同步关键补丁，不允许在命令内再内联副本（双源漂移）。
- **URL 必须真实可访问**：所有 `\href{}` 链接须通过 `verify` 验活（LIVE）；出现 DEAD 必须替换为真实可达源，不得虚构或保留死链。
- **参考文献闭合**：每章 `bibitem` 键加章号前缀（`c1r1`、`c2r3`…）；`\cite` 必须有对应 `\bibitem`。
- **参考文献数量**：每章至少 `MIN_REFS`（默认 6）条 LIVE 引用——**仅设下限、不设上限**（引用越多越好）；由 `balance` 给**建议级告警**（不阻断）。移除任何关于引用 / LIVE 引用的上限设置。
- **编译路径强约束**：单章必须 `cd 第N章/` 内编译；整书必须在项目根编译（本机 xelatex 不把主文件目录加入搜索路径）。
- **内容通用化**：文档与示例不出现具体项目名、绝对路径、具体日期。
- **整书合并唯一入口**：必须用 `build`，禁止手敲 `xelatex main.tex`。

## 强制排版规范（三线表 / 伪代码）

本工具对表格与伪代码有统一强制样式，由 `check` 门禁在 SOP 阶段**阻断**退化写法。门禁范围：**禁用**裸 `\hline` / 列格式竖线 `|`（三线表规范）、**要求**表格含 `\toprule`/`\bottomrule` 顶底线、**要求**表题在上 / 图题在下、**禁用**裸 `verbatim`/`lstlisting`（伪代码规范）。

### 三线表（booktabs）
- 表格必须用 `booktabs` 三条规则线：表头上方 `\toprule`、表头下方 `\midrule`、表尾 `\bottomrule`。
- **严禁**裸 `\hline` 与列格式里的竖线 `|`（vertical rule）——二者会退化成「网格表」，与本工具范式冲突。
- 列格式用 `tabularx` 配合 `X` 自动撑满整宽：

```latex
\begin{table}[htbp]
\centering
\caption{...}
\label{tab:cN:name}
\begin{tabularx}{\textwidth}{l X X c}
\toprule
... & ... & ... & ... \\
\midrule
... & ... & ... & ... \\
... & ... & ... & ... \\
\bottomrule
\end{tabularx}
\end{table}
```

### 表题在上 / 图题在下
- `table` 浮动体内 `\caption` **必须位于表格上方**（表题在上）。
- `figure` 浮动体内 `\caption` **必须位于图形下方**（图题在下）。
- 覆盖 `table*` / `figure*` 星号变体。该位置规则由 `check` 门禁在 SOP 阶段**阻断**（强制校验）。

```latex
\begin{figure}[htbp]
\centering
\begin{tikzpicture}
  \node[draw] (a) {...};
  \node[draw, right=2cm of a] (b) {...};
  \draw[->] (a) -- (b);
\end{tikzpicture}
\caption{...}
\label{fig:cN:discriminate}
\end{figure}
```

### 伪代码 / 代码块（codeblock）
- 伪代码与代码块必须用共享 preamble 提供的 `codeblock` 环境（浅灰底 + 自动折行，与正文明显区分）。
- **严禁**裸 `\begin{verbatim}` / `\begin{lstlisting}`（不折行易溢出、无视觉样式）。
- 代码块内注释须为**纯 ASCII**（等宽字体不含希腊字母/中文/全角符号，否则 Missing character）：

```latex
\begin{codeblock}
def cusum_stat(x, theta0, theta1, thr):
    g, cps = 0, []                  # cumulative log-likelihood ratio
    for t, xt in enumerate(x):
        g = max(0, g + log(p(xt|theta1) / p(xt|theta0)))
        if g > thr:                 # alarm and reset on threshold exceed
            cps.append(t); g = 0
    return cps
\end{codeblock}
```

## 命令清单（模块 → 职责）

| 模块 | 职责 |
|------|------|
| `commands/fix.py` | 单章预处理：`normalize_text()`（URL 规范化 + TikZ 图宽上限）+ 生成 `chN.tex`/`_tmp.tex` |
| `commands/build.py` | **整书合并唯一入口**：前置表格 `\noindent` 自动注入 `_build` 副本 → labels → xref → 规范化 → xelatex×2 → overflow → 落盘 `main.pdf`；`--verify` 对 TRANSIENT 宽容；安全删除失败醒目告警 |
| `commands/verify.py` | **强制**联网验活：抽取 + 联网检测（重试/退避 + TRANSIENT 第二轮退避重试 + archive 兜底 + 软404 内容指纹 `SUSPECT` warning）；exit 0/1/2 |
| `commands/check.py` | 内容结构统计 + 编译前风险预检（缺字字符 / 截断 URL / 跨章 `\\ref` / TikZ `&` / 代码块非 ASCII，warning 级不阻断）+ **反向引用预检 `scan_cite_undef`（cite 键无对应 `\\bibitem` 即阻断 exit 1，编译期前暴露悬空引用）** + 字数硬门禁（下限 `--min-chars`、上限 `--max-chars`，可阻断；visible 口径含表格单元格文字）+ **排版样式门禁（三线表禁用 `\hline`/`|` 且须含 `\toprule`/`\bottomrule`、表题须在上 / 图题须在下、伪代码禁用裸 `verbatim`/`lstlisting`，阻断级）** |
| `commands/balance.py` | 结构/引用均衡；section/subsubsection 整章骨架校验（空 section 阻断）+ **阻断/建议分明**（TikZ 节点 `\\` 换行无 `align=` 编译期 Fatal 预检阻断 exit 1） |
| `commands/xref.py` | 合并前静态预检：文字「第N章」章号越界 + 跨章 `\ref` |
| `commands/overflow.py` | 编译日志体检（硬卡口）；Overfull 额外给「根因→修复」建议 |
| `commands/cleanup.py` | 成品落盘 + 中间文件归档（移动而非删除）；`_tmp_old/` 按 `(base,ext)` 分组保留最近 `PDFMAKER_TMP_OLD_KEEP`（默认 10）份、删更旧，杜绝无限堆积 |
| `commands/labels.py` | 跨章重复 `\label` 去重 |
| `commands/reader.py` | 素材强制阅读校验：`ingest` / `index` / `chunk` / `verify` / `toc`（5 字段校验） |
| `commands/track.py` | 章节 ↔ 素材阅读状态追踪：`init` / `show` / `check` / `update`（verified 时记录 `content_hash` 源指纹）/ `auto-init` / `bib-audit` / **`stale`（比对源指纹，exit 0 新鲜 / 1 源已改 / 2 未 verified，防「改坏仍显示已核验」信任陷阱）**（读写 `materials.json`） |
| `commands/scaffold.py` | 书稿骨架生成：**整书初始化**（`main.tex` + `_tmp.tex` + 章节占位）+ **单章从素材生成合规富骨架**（`scaffold chapter N --material`，内嵌可编译三线表/TikZ/`codeblock` 示例与预填 `\bibitem`）|
| `core/normalize.py` | **单一规范化真源** `normalize_text()` = `url_to_href()` + `wrap_tikz()` + `fix_glyphs()`（字形自动修已拓宽至 σ/π/±/℃/希腊字母，与 `scan_glyphs` 预警集一致） |
| `core/lint.py` | 风险预检：`scan_glyphs`（数学模式感知，覆盖希腊字母/±/℃等缺字字符）/ `scan_truncated_urls` / `scan_tikz_badbreak` / `scan_frontmatter_tables` / `inject_frontmatter_noindent` / `scan_codeblock_nonascii` / `scan_table_style`（三线表禁用 `\hline`/`|`）/ `scan_table_rules`（三线表须含 `\toprule`/`\bottomrule`）/ `scan_caption_position`（表题在上 / 图题在下）/ `scan_raw_verbatim`（伪代码禁用裸 `verbatim`/`lstlisting`）/ `scan_crossref`（跨章 `\\ref` 预检，warning 不阻断）/ `scan_cite_undef`（反向引用预检：cite 键无对应 `\\bibitem` 即 warning/阻断，编译期前暴露悬空引用） |
| `core/paths.py` | 路径定位 / UTF-8 / 模板定位（CWD 优先，包内数据兜底） |
| `core/text.py` | 字数统计（`strip_blocks` / `chinese_count` / `char_count`）+ `strip_nonbody`（剔除图/代码/文献但**保留表格单元格**）+ `count_visible_body`（含表格文字，供 check 字数口径） |
| `core/chapters.py` | 章节枚举（`collect_chapters` / `chapter_range`） |

所有 CLI 均支持 `-h` 查看准确参数与示例。

## 单一规范化真源

`URL 规范化（url_to_href）+ TikZ 图宽上限（wrap_tikz）`两步合并后写入 `chN.tex`（单章）与合并时写入 `_build/第N章.tex`，**必须完全一致**，否则会出现「单章编译不溢出、合并却 Overfull」。因此这两步逻辑统一放在 `core/normalize.py: normalize_text()`：

- `fix`（单章）：`text = normalize_text(src.read_text(...))` → 写 `chN.tex` + `_tmp.tex`。
- `build`（合并）：对每个章节源调用同一个 `normalize_text()` → 写 `_build/第N章.tex`，再重写 `main.tex` 的 `\input` 指向归一副本。

两者共用同一函数、同样幂等，从根上消除双源漂移。绝不要在 `build` 或 `fix` 里再各写一份 URL/TikZ 处理。

## 资源

- `src/pdfmaker/templates/main.tex` — 整书主控模板（含扉页/目录/页眉页脚/参考文献降级补丁）。
- `src/pdfmaker/templates/_tmp.tex` — 单章编译 preamble 唯一真源。
- `src/pdfmaker/templates/chapter_init_notes_template.md` — 章节阅读笔记模板。

## 与其他组件的边界

- **协同**：素材采集工具提供素材 → 本技能整章节 → 后处理 PDF 工具（如需）。
- **不重复**：SVG/HTML 图表生成、编辑既有 PDF、创建技能自身。
