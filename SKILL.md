---
name: pdf-maker
description: 中文 LaTeX 报告/书籍工程化工具（xelatex + ctexrep + xeCJK）。提供单章独立编译与整书合并双模式，并在关键节点设置质量关卡：素材强制阅读、URL 联网验活、编译日志体检、跨章 \label 去重。适用于「把零散章节稳定产出为排版合规的中文 PDF」「写一份像样的中文技术报告/白皮书/调研汇编/多章书籍」「从这些素材生成 LaTeX PDF」等请求。
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

## 前置要求（macOS）

- **TeX Live 2022+**（含 `xelatex`、`ctexrep`、`xeCJK`）。macOS 安装任选：
  - `brew install --cask mactex`（完整版，需 sudo）
  - `brew install --cask basictex`（精简版，装后 `sudo tlmgr install ctex xecjk tcolorbox booktabs multirow tabularx adjustbox enumitem`）
  - **免 sudo**：官方 `install-tl` 装到 `~/texlive/<年份>`（用户目录），或 TinyTeX 装到 `~/Library/TinyTeX`；`find_xelatex` 会自动探测这两类路径，无需改 PATH。
- **Python 3.10+**：工具仅用标准库，**无需 `pip install` 任何包**。macOS 建议用 Homebrew Python（`brew install python`）；系统自带的 `/usr/bin/python3` 版本可能低于 3.10。
- **`pdfinfo`**（poppler）：`brew install poppler`，用于 PDF 元数据/页数校验，可选。
  若 poppler 不可用而需渲染目检成品页，可改用 PyMuPDF（`pip install pymupdf`）：
  `python -c "import pymupdf; d=pymupdf.open('main.pdf'); [p.get_pixmap(dpi=60).save(f'pg{i+1}.png') for i,p in enumerate(d)]"`。

## 安装

两步缺一不可：

1. 把本技能目录放到 Claude Code 技能加载路径（装在哪都不影响使用，工具通过 CWD 定位书稿项目）：
   - 用户级：`~/.claude/skills/pdf-maker/`
   - 项目级：`<project>/.claude/skills/pdf-maker/`
2. 在技能目录内执行一次可编辑安装：`pip install -e .`（建议用 Homebrew Python 3.10+ 的 pip）。

**第 2 步不可省**：命令的实际执行目录是书稿项目根（而非技能目录），未安装时 `src/pdfmaker`
不在 `sys.path` 上，在书稿目录跑 `python -m pdfmaker ...` 会直接报 `No module named pdfmaker`。
安装后 `python -m pdfmaker` 与 `pdfmaker` 两种调用方式在任意目录均可用。

## 书稿目录结构

```
<PROJECT>/                # 标准布局（多章书籍）
├── main.tex              # 整书主控（从包内模板 pdfmaker.templates/main.tex 落地）
├── materials.json        # 章节 ↔ 素材阅读状态索引（track 维护）
├── figures/              # 图片资源
├── 第1章/
│   ├── 第1章.tex          # 每章一个目录 + 一个 .tex（\chapter 作顶层）
│   └── 素材-第1章.md      # 本章素材（多章约定：素材放章节文件夹内）
├── 第2章/...
└── ...

<PROJECT>/                # 扁平布局（单章写作推荐，scaffold --flat）
├── main.tex              # \input{第1章}（扁平路径）
├── 第1章.tex              # 章节源直接在项目根，不建章目录
├── 素材-第1章.md          # 素材在项目根（章的文件都在一级目录）
└── 第1章.pdf              # 成品 PDF 落一级目录（cleanup 自然落盘）
```

也可直接 `python -m pdfmaker scaffold <dir>` 生成上述骨架（加 `--flat` 得扁平布局）。
两种布局全链路兼容：fix / check / balance / verify / chapter / cleanup / track / build
均自动识别，无需额外参数。

**素材位置约定**：多章书稿的素材放**章节文件夹**（`第N章/素材-第N章.md`），与章节源
同级——素材是章的输入，随章走；扁平单章项目的素材在项目根。`chapter` / `scaffold
chapter` 的 `--material` 给裸文件名即可，两种约定自动解析（`resolve_material`）。

## 核心工作流（双模式）

- **单章独立编译**：每章用 `\chapter`，走完整闭环（读素材 → 写 → 预处理 → 校验 → 编译 → 体检） → 验证 → 下一章。
- **整书合并**：所有章节用 `\chapter`，主控 `main.tex` 用 `\input{第N章/第N章}` 装入 → 出 `main.pdf`。

两种模式混用 = bug。一个书稿只选其一作为最终交付形态（推荐：单章开发 + 整书合并）。

> **批量操作 shell 注意（zsh）**：`for i in 1 2 3; do ... 第$i章 ...` 中 `$i章` 会被 zsh 当作变量 `i章`（CJK 字符是合法变量名成分），展开为空导致路径错误；必须写成 `${i}章`。bash 无此问题。

## 单章 SOP（精确步骤）

每一步对应一个子命令，按此顺序执行：

1. **读素材**：`python -m pdfmaker reader ingest 第N章/素材-第N章.md`（一步完成 index → chunk → verify 三阶段，5 字段全过才算读完；扁平单章项目素材在项目根，路径为 `素材-第1章.md`。素材自上次完整阅读后未变更时缓存短路、跳过逐块重读，`--force` 强制重读）。
2. **写章节**：直接跑 `python -m pdfmaker chapter N --material 第N章/素材-第N章.md`——**章文件缺失时自动生成合规富骨架**（内嵌可编译三线表 / TikZ 图 / `codeblock` 示例与预填文献，作者复制即用），从源头杜绝样式漂移（详见下方「素材 → 章节脚手架」）。章文件已存在则不覆盖；**唯一例外**是整书初始化落下的「未命名章标题」占位骨架——它不含作者劳动，给了 `--material` 会自动再生为素材富骨架，并在完成素材阅读后给出撰写指引、提前退出（不再空跑后续步骤）。无需记忆 `--scaffold` 开关。`--material` 给裸文件名 `素材-第N章.md` 也可，章节文件夹与项目根两种约定自动解析。撰写正文后重跑 `chapter N` 即可从断点继续；边写边查用 `lint N`（不阻断）。
3. **预处理**：`python -m pdfmaker fix N`（读包内 `templates/_tmp.tex`，`normalize_text()` 做 URL 规范化 + TikZ 图宽上限 + 字形修复 + 长 `\texttt` 自动拆词；写出 `chN.tex` 与 `_tmp.tex`）。
4. **结构校验**：`python -m pdfmaker check N` + `python -m pdfmaker balance N`。**阻断项**：排版样式退化（裸 `\hline`/竖线、缺顶底线、表题图题错位、裸 verbatim）与悬空 `\cite`；**告警项**：字数未达下限（默认只 WARN 不阻断——字数是内容厚度的主观代理指标，不应逼作者注水凑数；附录/短章用 `--no-gate`，需要严格把关时用 `--strict` 恢复硬阻断）。**写作期的正确节奏**：`lint N`（check+balance 合并且永不阻断）随写随查、快速迭代，满意后再跑 `chapter N` 完整流程一次，避免「改三个字重跑全链路」。
5. **联网验活（强制）**：`python -m pdfmaker verify N`（exit 0 继续 / 1 失效链接必改 / 2 离线须重跑）。
6. **编译 + 日志体检（一步）**：`python -m pdfmaker compile N`——自动定位 xelatex（与 build/chapter 同一套 `find_xelatex` 探测，**无需手工 export PATH**、无需 cd 进章目录），`_tmp.tex` 编译两遍（默认静默，失败回显末尾 40 行；`--verbose` 全量），随后自动 `overflow` 体检 `_tmp.log`（拦截 Overfull / Missing character / 断链 / Fatal）。overflow 对每条阻断级 Overfull 附**源文件行号定位**（内容锚定 → difflib 行对齐），落入表格时再列出含超长不可断长串的候选单元格。旧式手动写法（`cd 第N章/ && xelatex _tmp.tex` 两遍 + `overflow`）仍兼容。
7. **清理落盘**：`python -m pdfmaker cleanup N`（复制 `_tmp.pdf → 第N章.pdf`，中间文件归档到 `_tmp_old/`）。
8. **更新素材追踪**：`python -m pdfmaker track update <PROJECT> 第N章 --auto --material 第N章/素材-第N章.md`（`--auto` 免手抄：size/lines 取章节 .tex 实测、chunks 取素材 reader 状态；显式三整数旧用法仍兼容）。

## 整书合并 SOP（精确步骤）

统一用 `build` 一键完成。**合并前先确认 main.tex 的摘要已填写**（序言/术语表不需要则整块删除）——模板只留占位注释，忘记填写会出空白前置页；build 的预检会对「存在但正文为空」的前置部分打 WARN。它依次调用：

1. **前置预检（非阻断）** —— 前置整宽表格缺 `\noindent` 提醒（`_build` 副本自动补入，源文件不变）/ 前置部分（摘要/序言/术语表）存在性 + 空壳（存在但正文为空）/ `main.tex` 与共享补丁源漂移。
2. `labels <PROJECT>` —— 跨章重复 `\label` 去重（有跨章引用则中止）。
3. `xref <PROJECT>` —— 合并前静态预检（文字「第N章」章号越界 / 跨章 `\ref`，阻断则中止）。
4. 对每个章节调用与单章**完全相同**的 `normalize_text()`，写入 `_build/`，重写 `main.tex` 的 `\input` 指向归一副本。
5. 在 `_build/` 内 `xelatex` 两遍。
6. `overflow _build/main.log`（硬卡口，Overfull 给根因建议）。
7. 通过则复制 `_build/main.pdf → <PROJECT>/main.pdf`，并清理 `_build/`（删除失败留 `_build_bak*` 并告警）。

命令：

```bash
cd <PROJECT>
python -m pdfmaker build .                 # 合并（含 labels + xref + 规范化 + 编译 + 体检，默认静默输出）
python -m pdfmaker build . --verify        # 合并前额外联网验活全书 URL
python -m pdfmaker build . --verbose       # 全量回显 xelatex 输出（排障时用）
python -m pdfmaker build . --no-preflight  # 跳过 xref 预检（不推荐）
```

## 素材 → 章节脚手架

两档能力：

1. **单章从素材生成（推荐，已接进标准 SOP）**
   ```bash
   # 标准 SOP：章文件缺失时自动生成合规富骨架（无需 --scaffold）
   python -m pdfmaker chapter N --material 第N章/素材-第N章.md
   # 等价显式写法（兼容保留）：
   python -m pdfmaker scaffold chapter N --material 第N章/素材-第N章.md
   ```
   解析素材得到：章标题（首个 Markdown 标题）、二级节结构（`## ` 自动映射为 `\section`，标题中的「第N章」与手写小节编号「1. 」「2.3 」自动剥离，避免与 ctexrep 自动编号重复）、全部 URL（预填 `\bibitem{cNrK}\href{URL}{...}`，并在引言给引用示例保证 `bibitem==cite` 开箱一致）。`chapter N --material` 在章文件缺失时已默认触发上述生成，使写作流水线自我引导。

2. **整书初始化**
   ```bash
   python -m pdfmaker scaffold <dir> --chapters N   # 生成整书骨架
   ```

生成的单章骨架包含：头部强制约定注释（引用键前缀 `cN`、标签前缀 `cN`、禁止跨章 `\ref`、字形规则）、可直接编译的**合规示例节**（三线表表题在上 + TikZ 图题在下 + `codeblock` 全 ASCII 注释）、按素材预生成的 `\section`、以及预填文献的 `thebibliography`。该示例节标题醒目提示「撰写后删除」，作者删掉即可，不会带进成品。

**非破坏性**：`scaffold chapter` 与 `chapter --scaffold` 一律不覆盖已存在的章文件（除非 `--force`）。

## 设计约束（红线）

- **单一真源**：章节 `.tex` 禁止保留 `.bak` 副本；preamble 只在 `templates/_tmp.tex`（单章）与 `templates/main.tex`（整书），两者的共用补丁统一来自 `templates/_preamble_shared.tex`（经 `{{SHARED_PREAMBLE}}` 占位符注入），不允许在命令内再内联副本（双源漂移）。
- **URL 必须真实可访问**：所有 `\href{}` 链接须通过 `verify` 验活（LIVE）；出现 DEAD 必须替换为真实可达源，不得虚构或保留死链。内网 / SSO 鉴权后可见的合法链接可列入豁免名单（`PDFMAKER_VERIFY_ALLOW_HOSTS` 或 `.pdfmaker.toml` 的 `verify_allow_hosts`，精确或子域名后缀匹配），标记 EXEMPT 按已验证处理；豁免只免验活，不免格式/截断预检。
- **参考文献按需引用（零引用是合法形态）**：引用是论证的需要而非章节配额；资料/代码无外部文献时完全不写参考文献，严禁为凑数而硬造引用（`MIN_REFS` 默认 0 不设下限，零引用章零告警）。有引用时必须闭合（键加章号前缀 `c1r1`、`\cite` 与 `\bibitem` 一一对应，无孤儿无悬空），且所有 `\href{}` 链接须经 `verify` 验活通过（LIVE）。
- **编译路径强约束**：单章必须 `cd 第N章/` 内编译（扁平布局则在项目根编译）；整书必须在项目根编译（本机 xelatex 不把主文件目录加入搜索路径）。用 `compile N` 可在项目根直接完成单章编译，无需 cd。
- **CWD 守卫**：`chapter` / `scaffold chapter` 拒绝在「不像书稿项目根」（无 main.tex / materials.json / 既有章节结构）的目录创建章骨架（exit 2；`--force-cwd` / `--force` 豁免）。在错误目录跑命令不会再产生游离的 `第N章/` 目录；素材裸文件名找不到时会下探一级子目录并给出 cd 提示。
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
| `commands/fix.py` | 单章预处理：`normalize_text()`（URL 规范化 + TikZ 图宽上限 + 字形修复 + 长 `\texttt` 自动拆词）+ 生成 `chN.tex`/`_tmp.tex` |
| `commands/compile.py` | 单章编译一体化：`find_xelatex()` 自动定位（免 PATH）→ `_tmp.tex` 两遍（默认静默，失败回显末尾 40 行）→ `overflow` 体检；`--verbose` 全量输出、`--no-overflow` 跳过体检 |
| `commands/build.py` | **整书合并唯一入口**：前置预检（`\noindent` 自动注入 `_build` 副本 / 前置部分存在性 / 补丁漂移） → labels → xref → 规范化 → xelatex×2 → overflow → 落盘 `main.pdf`；`--verify` 对 TRANSIENT 宽容；安全删除失败醒目告警；非阻断告警在末尾汇总重列，防长输出淹没 |
| `commands/verify.py` | **强制**联网验活：抽取 + 联网检测（重试/退避 + TRANSIENT 第二轮退避重试 + archive 兜底 + 软404 内容指纹 `SUSPECT` warning + 内网/鉴权主机豁免 `EXEMPT`）；exit 0/1/2 |
| `commands/check.py` | 内容结构统计 + 编译前风险预检（缺字字符 / 截断 URL / 跨章 `\ref` / TikZ `&` / 代码块非 ASCII / 标题手写前导编号 / `\texttt` 不可断行长串 / tabularx 单列挤压，warning 级不阻断）+ 反向引用预检 `scan_cite_undef`（cite 键无对应 `\bibitem` 即阻断 exit 1）+ 字数门禁（默认告警不阻断，`--strict` 阻断，`--no-gate` 关闭；visible 口径含表格单元格文字）+ 排版样式门禁（三线表 / 表题在上图题在下 / 伪代码，阻断级） |
| `commands/balance.py` | 结构/引用均衡；section/subsection/subsubsection 整章骨架校验（空 section 阻断）+ 阻断/建议分明（TikZ 节点 `\\` 换行无 `align=`、节点未转义 `&` 均为编译期 Fatal 预检阻断 exit 1） |
| `commands/lint.py` | 单章快速预检（check+balance 合并，永远 exit 0，边写边查不阻断） |
| `commands/xref.py` | 合并前静态预检：文字「第N章」章号越界 + 跨章 `\ref`；`--self-only` 供单章 SOP 早期自检 |
| `commands/overflow.py` | 编译日志体检（硬卡口）；代码块/显示公式内 Overfull 降级为警告；Overfull 额外给「根因 → 修复」建议 + **源文件行号定位**（内容锚定/difflib 行对齐）与表格单元格候选 |
| `commands/cleanup.py` | 成品落盘 + 中间文件归档（移动而非删除）；`_tmp_old/` 按 `(base,ext)` 分组保留最近 `PDFMAKER_TMP_OLD_KEEP`（默认 10）份、删更旧，杜绝无限堆积 |
| `commands/labels.py` | 跨章重复 `\label` 去重 |
| `commands/reader.py` | 素材强制阅读校验：`ingest` / `index` / `chunk` / `verify` / `toc` / `clean`（5 字段校验）；ingest 缓存短路（素材未变跳过逐块重读，`--force` 强制） |
| `commands/track.py` | 章节 ↔ 素材阅读状态追踪：`init` / `show` / `check` / `update`（verified 时记录 `content_hash` 源指纹；`--auto` 自动取章节 .tex 实测值与素材 chunks，免手抄）/ `stale`（比对源指纹，exit 0 新鲜 / 1 源已改 / 2 未 verified）/ `auto-init` / `bib-audit`（读写 `materials.json`） |
| `commands/scaffold.py` | 书稿骨架生成：**整书初始化**（`main.tex` + `_tmp.tex` + 章节占位）+ **单章从素材生成合规富骨架**（`scaffold chapter N --material`，内嵌可编译三线表/TikZ/`codeblock` 示例与预填 `\bibitem`） |
| `core/normalize.py` | **单一规范化真源** `normalize_text()` = `url_to_href()` + `wrap_tikz()` + `fix_glyphs()`（字形自动修覆盖 σ/π/±/℃/希腊字母，与 `scan_glyphs` 预警集一致）+ `relax_long_texttt()`（长 `\texttt` 自动 `\allowbreak`，幂等） |
| `core/lint.py` | 风险预检扫描器全集（缺字/截断URL/TikZ 坏节点与 `&`/代码块非 ASCII/三线表/表题图题位置/裸 verbatim/跨章 `\ref`/悬空 cite/标题重复编号/前置表格 `\noindent`/前置部分存在性/补丁漂移/`\texttt` 不可断行长串 Overfull 预警/tabularx 单列挤压预警） |
| `core/paths.py` | 路径定位 / UTF-8 / 模板定位（包内数据）/ 素材定位（`resolve_material`：章节文件夹与项目根两种约定） |
| `core/config.py` | 集中配置唯一真源（环境变量 + `.pdfmaker.toml` 覆盖） |
| `core/text.py` | 字数统计（`strip_blocks` / `chinese_count` / `char_count`）+ `strip_nonbody`（剔除图/代码/文献但**保留表格单元格**）+ `count_visible_body`（含表格文字，供 check 字数口径） |
| `core/chapters.py` | 章节枚举（`collect_chapters` / `chapter_range` / `chapter_sort_key`） |
| `core/xelatex.py` | 超时保护的 xelatex 调用封装（默认 300s，超时返回 124） |
| `core/watchdog.py` | 扫描看门狗（SIGALRM 墙钟时限，默认 30s）：`check`/`balance`/`xref`/`fix` 的正则扫描超时即抛 `ScanTimeoutError`，命令层收敛为 exit 1 阻断；非 Unix / 非主线程退化为 no-op |

所有 CLI 均支持 `-h` 查看准确参数与示例。

## 单一规范化真源

`URL 规范化（url_to_href）+ TikZ 图宽上限（wrap_tikz）+ 字形修复（fix_glyphs）+ 长 \texttt 自动拆词（relax_long_texttt）`四步合并后写入 `chN.tex`（单章）与合并时写入 `_build/第N章.tex`，**必须完全一致**，否则会出现「单章编译不溢出、合并却 Overfull」。因此这四步逻辑统一放在 `core/normalize.py: normalize_text()`：

- `fix`（单章）：`text = normalize_text(src.read_text(...))` → 写 `chN.tex` + `_tmp.tex`。
- `build`（合并）：对每个章节源调用同一个 `normalize_text()` → 写 `_build/第N章.tex`，再重写 `main.tex` 的 `\input` 指向归一副本。

两者共用同一函数、同样幂等，从根上消除双源漂移。绝不要在 `build` 或 `fix` 里再各写一份 URL/TikZ/拆词处理。

**长 \texttt 自动拆词**：等宽字体禁用断词，`/` `.` `_` 也不构成断点，长标识符是 Overfull 的第一来源。`relax_long_texttt` 在规范化时对 ≥ 阈值（默认 20 字形）的 `\texttt` 内容在分隔符后自动插入 `\allowbreak{}`（只许断行、不改排版，幂等）；相邻 `\texttt` 的 `/` 接缝同样补断点。`PDFMAKER_TEXTTT_RELAX_CHARS` 调整，0 关闭。它治理「正文行内」溢出；`check`/`lint` 的 `scan_unbreakable_runs`（预警）与 `scan_squeezed_tables`（表格单列挤压预警）则覆盖「写作期即知」的两道前哨，三层配合。

## 资源

- `src/pdfmaker/templates/main.tex` — 整书主控模板（含扉页/目录/页眉页脚/参考文献降级补丁）。
- `src/pdfmaker/templates/_tmp.tex` — 单章编译 preamble 唯一真源。
- `src/pdfmaker/templates/_preamble_shared.tex` — 单章/整书共用补丁片段唯一真源。
- `src/pdfmaker/templates/chapter_init_notes_template.md` — 章节阅读笔记模板。

## 与其他组件的边界

- **协同**：素材采集工具提供素材 → 本技能整章节 → 后处理 PDF 工具（如需）。
- **不重复**：SVG/HTML 图表生成、编辑既有 PDF、创建技能自身。
