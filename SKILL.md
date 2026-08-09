---
name: "pdf-maker"
version: "1.1.0"
description: "中文 LaTeX 报告工程化 skill。基于 xelatex + ctexrep + xeCJK，提供单章独立编译与整书合并双模式、源代码预处理修复、强制素材阅读校验、编译日志体检、表格/图/URL 排版约定与分类踩坑速查。适用于中文技术报告、调研报告、白皮书、论文。"
---

# pdf-maker

> 一句话：把零散的中文 LaTeX 章节，按「预处理 → 编译 → 日志体检 → 视觉确认」的闭环，稳定产出排版合规的 PDF。

本 skill 解决中文 LaTeX 报告最大的几类工程化痛点：源码里散落的中文/编码/表格/图/URL 坑在编译期才暴露；多章同时写容易互相污染；素材「读一半就下笔」导致事实失真。它通过一批小而专的脚本 + 一套强制 SOP，把这些问题挡在交付之前。

---

## 目录

- [§ 0 适用场景](#0-适用场景)
- [§ 1 强制规范（红线）](#1-强制规范红线)
- [§ 2 核心心法](#2-核心心法)
- [§ 3 双模式工作流](#3-双模式工作流)
- [§ 4 标准目录结构](#4-标准目录结构)
- [§ 5 素材阅读 SOP](#5-素材阅读-sop)
- [§ 6 单章编译 SOP](#6-单章编译-sop)
- [§ 7 整书合并 SOP](#7-整书合并-sop)
- [§ 8 脚本清单](#8-脚本清单)
- [§ 9 模板与示例约定](#9-模板与示例约定)
- [§ 10 表格排版约定（注意事项）](#10-表格排版约定注意事项)
- [§ 11 图排版约定（注意事项）](#11-图排版约定注意事项)
- [§ 12 URL 与超链接约定](#12-url-与超链接约定)
- [§ 13 编译环境注意事项](#13-编译环境注意事项)
- [§ 14 参考文献样式](#14-参考文献样式)
- [§ 15 页眉页脚](#15-页眉页脚)
- [§ 16 踩坑分类速查](#16-踩坑分类速查)
- [§ 17 反例清单](#17-反例清单)
- [§ 18 章节内容体量基线](#18-章节内容体量基线)
- [§ 19 与其他 skill 的边界](#19-与其他-skill-的边界)
- [§ 20 触发关键词](#20-触发关键词)

---

## 0. 适用场景

- 中文技术报告、调研报告、白皮书、论文类文档（基于 `xelatex + xeCJK + ctexrep`）。
- 文档规模：每章 5–15 页，全书 ≤ 30 章。
- 章节写作方式二选一：
  - 单章用 `\chapter{...}` + `\section`/`\subsection`（单章独立编译模式）；
  - 整书用 `\chapter`（主控 `\input` 合并）模式。
- 不适用：纯 HTML 报告、Markdown→PDF（pandoc 即可）、无中文的英文论文（本 skill 的中文/编码补丁无意义）。

---

## 1. 强制规范（红线）

> 任何新会话开始时，先读完本节。违反一次返工一次。

### A. 只用当前生效目录

本 skill 可能以多个副本存在（例如带 `.bak` 后缀的备份）。**只用当前生效的 `pdf-maker/` 目录**，任何 `.bak` / 旧版本目录都禁止作为工作目录——选错版本会走错 SOP，导致整章返工。

> **已注册（canonical）位置**：`~/.workbuddy/skills/pdf-maker/`（用户级，框架自动发现）。若在其它位置发现副本，**以注册位置为准**，不要并行维护多份导致 SOP 漂移。开源仓库（GitHub）是唯一权威源，本地注册副本应与之保持一致。

### B. 单章模式：每章独立编译

当用户要求「一章一章写」「按章节推进」时，每一章必须走单章独立编译 SOP（§ 6），验证通过后才进下一章。全部章节通过后才做整书合并。

### C. 完整阅读素材（铁律）

写每章之前必须**完整读完**对应素材：

- 逐块通读全文，**不跳读**；
- ❌ 只读前 N 行（`head` / 只读开头）；
- ❌ 用关键词 `grep` 抓片段代替通读；
- ❌ 凭记忆 / 推断 / 领域知识写素材之外的内容。

只靠「读过」的状态标记不算读完——必须用 `reader.py` 的三阶段（`index → chunk → verify`）把每个 chunk 真正读过，详见 § 5。

### D. 不得偷懒

以上三条无例外。走 SOP → 通过 → 进下一章；偷懒 → 报错 / 不合规 → 重做（唯一结果）。

### E. 工具故障诊断

当多个并发工具调用「看起来全部无响应」时，先**用最简单的工具 ping 一次**验证假设，再下结论：

```
e1. 用一个只读小工具验证通路
e2. 读一个已知存在的小文件验证读通路
e3. 若单工具也失败 = 工具层真挂；否则原工具重试
```

**绝对禁止**：仅凭「看起来挂了」或某个文件 ENOENT，就断言「所有工具都没响应」并跳过后续步骤。

### F. 阅读证明行（必备格式）

每章动笔前，必须在回复首行输出：

```
📖 完整读完 <绝对路径> (<大小> / <总行数> 行 / <N> chunks) verify ✅ @<HH:MM:SS>
```

不输出此行就开始写章节 = 违规。verify 失败也输出 = 违规。

---

## 2. 核心心法

1. **一次编译通过为核心标准**：所有 LaTeX 语法、编码、样式冲突问题，统一在 `fix.py` 预处理阶段批量修复，**禁止在编译环节临时改源码**。
2. **单章独立编译，验证后写下一章**。多章同时写几乎等于必然翻车。
3. **`-halt-on-error` 严格模式**：不允许 silent fallback。「Output written」不等于成功，必须看日志里的错误数。
4. **PDF 内容必须眼见为实**：每章成品 PDF 至少看第 1 页 + 带图/带表那一页。
5. **临时文件清干净**：每章交付后跑 `cleanup.py`，禁止 `.bak` / 一次性工具 / `_tmp.*` 留在章节目录。
6. **完整读完素材再动笔**：禁止部分阅读 / 凭记忆 / 推断（见 § 1.C）。

---

## 3. 双模式工作流

| 模式 | 适用 | 章节顶层命令 | 输出 |
|------|------|--------------|------|
| **单章独立编译** | 单章验证、调试 | `\chapter{...}` + `\section`/`\subsection` | `_tmp.pdf` → 复制为 `第N章.pdf` |
| **整书合并** | 最终交付 | `\chapter` + `\section` + `\subsection`（ctexrep 默认行为） | `main.pdf` |

整书模式要点：

- 用 ctexrep 默认的 `\chapter` 行为（自动 clearpage + 「第 X 章」前缀 + X.Y / X.Y.Z 编号），**不要**去 hack `\chapter` 去掉 clearpage，也**不要**冗余 `\renewcommand{\thechapter}` 之类的重定义——默认即可。
- twoside + `\geometry{margin=2.5cm}`：整书必加（页面利用率 + 奇偶页页眉）。
- **参考文献策略**：整书合并时**保持每章参考文献独立**，不合并为单一文献（每章自带 `thebibliography`，各自从 [1] 起编、互不干扰）。详见 § 14。
- **preamble 按场景取用，不得串用**：单章编译取 `assets/templates/_tmp.tex` 模板的 preamble（由 `fix.py` 读取并填入章节文件名，模板是唯一真源，见 § 9）；整书合并取 `main.tex` 模板的 preamble（含 `twoside` / `geometry` / `fancyhdr` / PDF 元数据）。**整书合并禁止误用单章 `_tmp.tex` 模板的 preamble**——它只含单章级补丁、缺 twoside / 页眉 / 元数据，见 § 9。

---

## 4. 标准目录结构

一个使用本 skill 的项目，**强制**每章一个独立子目录（章节源、中间文件、成品都收在章目录内）：

```
<项目名>/
├── main.tex                       # 整书主控（所有章节 OK 后才编译）
├── materials.json                 # 章节素材阅读状态（track_materials.py 维护）
├── figures/                       # 全部图形资源
├── 第1章/
│   ├── 第1章.tex                  # 章节源（手写，顶层 \chapter）
│   ├── ch1.tex                    # fix.py 生成的英文名中间文件
│   ├── _tmp.tex                   # fix.py 生成的单章编译入口
│   ├── 第1章.pdf                  # 单章成品
│   └── chapter_init_notes/        # 素材逐块通读笔记（可选但推荐）
├── 第2章/...
```

- 整书 `main.tex` 用 `\input{第N章/第N章}` 引入各章（见 `assets/templates/main.tex` 的章节列表占位符）。
- `fix.py` 优先读 `第N章/第N章.tex`；若章目录不存在，回退旧的扁平 `第N章.tex`（兼容存量项目）。
- **禁止**留在章节目录的文件：`*.bak` / `test_*.tex`。（`_tmp.*` / `chN.tex` 由 `cleanup.py` 在单章交付后清理，见 § 6 step 8。）

---

## 5. 素材阅读 SOP

写任何章节之前，先把对应素材「逐块完整通读」并校验，杜绝「读一半就写」。

> **路径约定（贯穿 § 5–§ 7）**：`<PDF_MAKER>` = pdf-maker 技能的安装根目录（如 `~/.workbuddy/skills/pdf-maker/` 或你存放本仓库的任意路径）；`<PROJECT>` = 你的书稿项目根目录（含 `第N章/` 与各 `*.tex`）。所有脚本都从 `<PROJECT>` 执行，用技能的实际安装路径调用（例如 `python <PDF_MAKER>/scripts/reader.py ...`）。脚本从「当前工作目录（`<PROJECT>`）」定位源文件；模板从「技能自身安装目录」向上定位，因此无需复制脚本或模板进项目。

```
[素材阅读 SOP - 每章动笔前必跑]
  S1. 定位素材源
      若为首次：python <PDF_MAKER>/scripts/track_materials.py init <项目目录>
      否则：     python <PDF_MAKER>/scripts/track_materials.py show <项目目录>

  S2. 对每个素材跑 reader.py 三阶段：
      a. python <PDF_MAKER>/scripts/reader.py index  <素材文件>   # 总览 + 初始化阅读状态
      b. python <PDF_MAKER>/scripts/reader.py chunk  <素材文件> N  # 逐块读（0-based，循环到末尾）
      c. python <PDF_MAKER>/scripts/reader.py verify <素材文件>    # 5 字段全过才算读完

  S3. verify 全过后，标记状态：
      python <PDF_MAKER>/scripts/track_materials.py update <项目> <章> <size> <lines> <N>

  S4. 输出 § 1.F 的阅读证明行到回复首行

  S5. 进 § 6 写章节
```

**关键约束**：

- `reader.py verify` 只校验「覆盖完整性」（文件被完整分块读过），**不等于**人类读过正文。必须真正逐 chunk 读正文 + 写笔记（参照 `assets/examples/chapter_init_notes_template.md`）。
- 禁止「只读 chunk 0 就跳到 verify」，禁止「基于标题记忆就扩写」，禁止「跳读最长的那个素材」。
- 每章写完后应能回答抽查：「这个事实来自哪个素材的哪个 chunk / 哪一行」。答不出 = 该章作废。

---

## 6. 单章编译 SOP（每章一循环）

> 路径约定见 § 5 开头（`<PDF_MAKER>` / `<PROJECT>`）：所有脚本从 `<PROJECT>` 执行。

```
[单章 N 循环]
  # 约定：在「书稿项目根目录 <PROJECT>」下执行；<PDF_MAKER> = skill 安装根目录
  #   cd <PROJECT>
  0. 跑 § 5 素材阅读 SOP（若未跑）                  ← 强制前置
  1. write 第N章/第N章.tex           # 按素材大纲写（标准子目录布局，见 § 4）
  2. python <PDF_MAKER>/scripts/fix.py N         # URL 规范化 + 图片宽度上限 + 生成 chN.tex + 第N章/_tmp.tex
  3. python <PDF_MAKER>/scripts/verify_urls.py N # URL 真实可达，全部 200 才继续
      注意：本步发起真实 HTTP 请求，需在「允许联网」环境下运行（本宿主沙箱
            默认拦截出站 TLS，运行前需放行网络；报错 SSL EOF 多为沙箱拦截而非 URL 真坏）。
      失败 → 替换源文件里的 URL → 回到 step 2。
      脚本已内置 archive.org 快照兜底：直连 202/SSL EOF 等不可达时自动改查
            web.archive.org 稳定镜像，多数 DOI/IEEE/ACM 死链可因此通过，无需手写探测脚本。
  4. python <PDF_MAKER>/scripts/check.py N       # 内容结构统计（参考用）
     python <PDF_MAKER>/scripts/check_balance.py N  # 结构/引用均衡（告警/阻断）
  5. xelatex -halt-on-error -interaction=nonstopmode 第N章/_tmp.tex   # 第 1 遍（日志/PDF 落在 第N章/）
     xelatex -halt-on-error -interaction=nonstopmode 第N章/_tmp.tex   # 第 2 遍（交叉引用）
  6. 看 第N章/_tmp.log → "X errors" 必须为 0
     python <PDF_MAKER>/scripts/check_overflow.py 第N章/_tmp.log   # 抓 Overfull/缺失字符/重复label/断链/Fatal，必须为 0
     # 参考文献三项约定（约定见 § 14，合并阶段不再重复，见 § 7）：
     #   (a) 本章 \bibitem 尽量不使用可选标签 [n]（check_balance 会提示，非阻断；目的是保证从 [1] 顺序编号）；
     #   (b) 本章内 bibitem 键唯一（无 multiply-defined）；
     #   (c) 本章每个 \cite 都有对应 \bibitem（无 ?? 断链）。
     #   (b)(c) 由 check_overflow（multiply-defined / undefined references）覆盖；(a) 人工确认编号从 [1] 起。
  7. 看 第N章/_tmp.pdf：
       - 第 1 页
       - 抽样看带图 / 带表那一页
       - 确认页数符合预期
  8. python <PDF_MAKER>/scripts/cleanup.py N     # 复制 第N章/_tmp.pdf → 第N章.pdf + 清理临时
  9. 记录本章交付 OK
[下一章]
```

**绝对禁止**：

- 跳过 step 0（素材阅读）；
- 跳过 step 4（check）或 step 6（日志体检）；
- 跳过 step 6/7 看日志 / 看 PDF；
- 把「Output written on _tmp.pdf」直接当成功；
- 整书合并前没有完成所有章节的单章验证。

---

## 7. 整书合并 SOP

模板见 `assets/templates/main.tex`。**整书合并使用 `main.tex` 模板的 preamble（含 twoside / geometry / fancyhdr / PDF 元数据）；不要手写 preamble，也不要误用单章 `_tmp.tex` 模板的 preamble（缺整书级格式）**（见 § 3 / § 9）。

```
1. 关闭所有 PDF 阅读器（见 § 13，否则 xelatex 写 PDF 会被锁）
2. 确认所有 第N章/第N章.pdf 存在且页数合理
3. python <PDF_MAKER>/scripts/fix_labels.py <项目目录>   # 整书级：去重跨章重复 label
4. xelatex -halt-on-error -interaction=nonstopmode main.tex   # 第 1 遍
   xelatex -halt-on-error -interaction=nonstopmode main.tex   # 第 2 遍
5. python <PDF_MAKER>/scripts/check_overflow.py main.log   # 整书日志体检，必须为 0
6. 看 main.pdf：封面 / 序言 / 目录 / 每章第 1 页 / 偶数页（验证 twoside 页眉）
7. 校验 PDF 元数据（标题 / 作者 / 主题）已写入
8. cleanup：删 main.aux/log/out/toc（保留 main.tex main.pdf）
```

`fix_labels.py` 修改了章节源文件后，需重跑 `fix.py` + 编译 + `check_overflow.py` 确认 0 冲突。

> **参考文献正确性不在合并阶段检查**：每章从 [1] 起编、键全局唯一、0 断链已在单章 SOP § 6 step 6 中保证（check_overflow 覆盖 multiply-defined / undefined references，并人工确认编号）。合并只需确认整体视觉与 PDF 元数据，无需重复校验参考文献。

---

## 8. 脚本清单

每个脚本都遵循统一说明格式：**用途 / 检查或处理项 / 是否调用 / 调用时机 / 退出码**。
导入了 `scripts/` 下的其它模块时会显式 `import`；不存在隐藏依赖。

| 脚本（`scripts/` 目录下） | 职责 | 是否自动调用 | 调用时机 |
|------|------|--------------|----------|
| `scripts/fix.py` | 单章预处理：URL 规范化 + 图片宽度上限 + 生成 `chN.tex`/`_tmp.tex`。源文件优先 `第N章/第N章.tex`，章目录不存在则回退扁平 `第N章.tex` | 是（每章必跑） | § 6 step 2 |
| `scripts/verify_urls.py` | 章节 URL 真实可达校验（HTTP 200） | 是（每章必跑） | § 6 step 3 |
| `scripts/find_urls.py` | 候选权威源兜底探测（verify 失败时找替代） | 否（按需手动） | verify 失败时 |
| `scripts/check.py` | 内容结构统计（字数 / 层级 / 元素计数） | 是（参考用） | § 6 step 4 |
| `scripts/check_balance.py` | 结构/引用均衡（小节字数下限、表格数、bibitem==url、孤儿 bibitem 检测、悬空 \cite 检测；兼容 \bibitem{key} 与 \bibitem[label]{key}） | 是（告警/阻断） | § 6 step 4 |
| `scripts/check_overflow.py` | 编译日志体检（Overfull/缺失字符/重复label/断链/Fatal） | 是（硬卡口） | § 6 step 6 / § 7 step 5 |
| `scripts/cleanup.py` | 复制成品 PDF + 清理临时文件 | 是（每章必跑） | § 6 step 8 |
| `scripts/fix_labels.py` | 跨章重复 `\label` 去重（整书级修复） | 否（整书合并前一次） | § 7 step 3 |
| `scripts/reader.py` | 素材强制阅读三阶段校验（index/chunk/verify/toc） | 是（写章前） | § 5 S2 |
| `scripts/track_materials.py` | 章节↔素材阅读状态追踪 + 引用质量审计 | 是（写章前/合并前） | § 5 / § 7 |

**三类 check 脚本的统一语义**：

- `check.py`：只统计，不阻断（给作者密度参考）。
- `check_balance.py`：质量告警；严重不均衡（如 bibitem≠url、孤儿 bibitem 未被引用、悬空 \cite 无对应条目）非零退出，但通常作为告警由作者判断。
- `check_overflow.py`：硬卡口；存在阻断级日志信号即非零退出，必须先修源码。

> 注：旧版曾有一个「检查图节点几何重叠」的脚本，已移除——图的排版规范已在 § 11 作为**前置约定**明确，写作时即遵守，无需事后检查。

---

## 9. 模板与示例约定

完整代码见 `assets/` 下对应文件，**不要把完整模板代码复制进本 SKILL.md**。

| 文件 | 用途 |
|------|------|
| `assets/templates/main.tex` | 整书主控模板（twoside + 默认 chapter + margin=2.5cm + 封面 + PDF 元数据 + 页眉页脚 + 中文 URL + 代码块 + 防溢出） |
| `assets/templates/_tmp.tex` | 单章独立编译 preamble 的**唯一真源**。`fix.py` 读取本文件，把占位符 `CHAPTER_TEX` 替换为实际章节中间文件名（chN.tex / 附录X_ch.tex），写出章节目录的 `_tmp.tex`。单章与整书两套 preamble 的关键补丁（中文 URL / 参考文献降级 / 代码块 / 防溢出）必须保持一致，详见 § 3 |
| `assets/templates/url-href.tex` | 中文 / 特殊字符 URL 写法参考（§ 12） |
| `assets/examples/chapter_init_notes_template.md` | 素材逐块通读笔记模板（§ 5） |

> `_tmp.tex` 文件名带下划线前缀，但它**不是临时文件**：它是 `fix.py` 写出的**单章编译入口**（含完整 preamble + `\input{实际章节中间文件}`）。其 preamble 来自 `assets/templates/_tmp.tex` 模板——`fix.py` 读取该模板并把占位符 `CHAPTER_TEX` 替换为真实文件名（如 `ch1.tex`），模板是唯一真源，`fix.py` 不再内联副本。

---

## 10. 表格排版约定（注意事项）

> 本节只讲**规则与注意事项**，不提供可直接复制的整表样例——请按当前数据的列数、内容自行组织，避免照抄导致结构失真。

硬规则：

1. 必须用 `tabularx` 而非 `tabular{p{...}}`（前者自动撑满列宽，后者易超宽溢出）。
2. 列格式：首列用 `l`（短标签），其余列用 `X`（自动分配剩余宽度）。列数 = `l` + N 个 `X`。
3. 顺序固定：`\centering` → `\small` → `\begin{tabularx}{\textwidth}{lXXX}` → 表头 → 三线。
4. 表头每个列都必须 `\textbf{...}`（不允许只加粗首列）。
5. `\caption{...}` 放在表格**之前**（表顶）。
6. 三线表：用 `\toprule` / `\midrule` / `\bottomrule`（booktabs），**严禁** `\hline`。
7. 浮动体位置参数写全四个：`[htbp]`。
8. 表格是「全宽三线表」：固定 `\begin{tabularx}{\textwidth}` 即可撑满版心。

常见错误：用 `tabular{p{2.6cm}...}` 导致列宽算错、字溢出表边界；`[ht]` 导致浮动位置告警；只加粗首列表头。

---

## 11. 图排版约定（注意事项）

> 本节只讲**规则与注意事项**，不提供可直接复制的整图样例——请按当前节点的数量、布局、文字长度自行组织。

硬规则：

1. 用 `tikzpicture` 画图时，**节点必须包含**：`rounded corners` + `minimum width` + `minimum height` + `text width` + `align=center` + `font=\small`。尤其不能省 `text width`，否则中文字会溢出节点边界。
2. 统一箭头风格：`arrow/.style={->, >=stealth, thick}`，所有连线用 `\draw[arrow]`，不要散用 `\draw[->]`（粗细不一致）。
3. 同层节点在 y 方向错开半个 `node distance`，防止多行文字重叠。
4. `\centering` 放在 `tikzpicture` 之前。
5. 横向间距统一：`\begin{tikzpicture}[node distance=1.2cm, ...]`。
6. 节点上的长文字必要时用 `\\` 手动断行，或用 `\scriptsize` 缩小。
7. 颜色绑定（如需分级着色）应全局一致，不要凭喜好换色导致语义冲突。
8. 图片宽度：由 `fix.py` 的 wrap_tikz 自动给每个 `tikzpicture` 套 `adjustbox{max width=\textwidth}`，**只缩放超宽图**，正常图不动——这是「图不超出版心」的结构性保证，无需手工量宽度。

常见错误：节点不加 `text width`（文字溢出）；同层节点同 y 坐标（文字重叠）；用 `\draw[->]`（箭头粗细不一）；图整体宽于版心。

---

## 12. URL 与超链接约定

核心结论：

- 中文 / 含特殊字符的 URL，**必须用** `\href{raw-url}{display-text}`，**不要用** `\url{...}`，也**不要**预先 percent-encode。
- `hyperref` 会把 raw-url 自动 percent-encode 写入 PDF 注解（不会双编码）；显示文本走 verbatim 解析，其中的 LaTeX 特殊字符必须转义（`_ & $ # % \`）。
- 整书 / 单章模板已预置「中文 URL 支持」补丁（重写 `\Url@FormatString` 去掉 math mode），因此即便保留 `\url{}` 也能正常显示中文，不会变成豆腐块。但若手写，仍推荐 `\href{raw}{display}` 以显式可控。

反例：`\let\url\nolinkurl`（杀掉所有超链接）；预 percent-encode 后再进 `\href`（双编码）；`\urlstyle{rm/same}` 三件套（对中文豆腐无效，不要浪费时间）。

---

## 13. 编译环境注意事项

### 锁文件（最常见编译失败）

症状：`xdvipdfmx:fatal: Unable to open "main.pdf"` / `No output PDF file written` / `fwrite: Broken pipe`。源 `.tex` 没报错，xelatex 进入写 PDF 阶段才失败。

根因：`main.pdf`（`_tmp.pdf` 同理）被 PDF 阅读器锁住读句柄（Acrobat / Chrome / SumatraPDF / Foxit 等），xelatex 拿不到写权限。

处理：编译前先关闭相关 PDF 阅读器，或等 2 秒再编译；也可用 `-jobname book` 绕开（输出 `book.pdf` 后再改名）。

### 编码

- 所有 `.tex` 必须是 **UTF-8**。用 PowerShell `Set-Content -Encoding UTF8` 写中文会加 BOM，导致 silent corruption；统一用工具/脚本写文件。
- 不要对 `.tex` 做 `Get-Content | ForEach | Set-Content` 的 round-trip 改写（编码不一致会偷偷损坏）。

### 退出码伪信号

PowerShell 下某些情况的 exit 1 是伪信号。判定成功与否看「PDF 是否生成 + 页数是否符合预期 + 日志错误数」，不要仅凭退出码。

### 环境与工具链备注

- **用 `pymupdf`（`import pymupdf`）而非 `fitz`**：`fitz` 已弃用，会打印 `DeprecationWarning`，功能不受影响，但日志噪声大。
- **`chardet` 可能不可用**：脚本不要依赖它做编码探测；统一以 UTF-8 读写 `.tex` / `.py`。
- **sandbox safe-delete 守卫**：`rm` / `cleanup.py` 删除临时文件时可能被 `SAFE_DELETE_BULK_CONFIRM_REQUIRED` 拦截而退出非零——**无害**，临时文件下次编译自动覆盖，不要误判为失败。
- **`verify_urls.py` 需要联网**：本脚本对章节内每个 URL 发起真实 HTTP 请求，必须在「允许出站网络」的环境下运行（本宿主沙箱默认拦截出站 TLS，运行前需放行；若报 `SSL: UNEXPECTED_EOF_WHILE_READING` 多为沙箱拦截而非 URL 真坏）。脚本已内置 `archive.org` 快照兜底——直连返回 202 / 瞬断 SSL 等不可达时自动改查 web.archive.org 稳定镜像，多数 DOI/IEEE/ACM 链接可因此校验通过，无需手写探测脚本。
- **生成器 / 构建脚本务必写成 `.py` 文件再运行**：合并主控、批量替换占位符等脚本若含反斜杠（正则、`\\` 换行、LaTeX 转义），**不要**在 Bash 里用 heredoc 内联——shell 会吞掉 `\`，导致正则与 LaTeX 转义全部失效。写文件后 `python x.py` 运行。
- **Git Bash 下 `seq` 不可用**：章节遍历用 Python `for n in range(1, N+1)`，不要 `seq`。

---

## 14. 参考文献样式

### 策略：每章独立、从 [1] 起编

- **整书合并时每章参考文献保持独立**，不合并为单一「全书参考文献」。每章自带 `thebibliography`，各自从 [1] 起顺序编号、互不干扰——这是本 skill 的**默认合并策略**（见 § 3 整书模式要点）。
- **单章写作约定（推荐）**：`\bibitem` **尽量不写可选标签** `[n]`（如 `\bibitem[5]{r5}` 会让编号变成 5、6、8、10 乱序）。省略可选标签，LaTeX 自动从 [1] 顺序编号。`check_balance.py` 已能兼容可选标签写法并自动检出、以「建议」形式提示（非阻断），作者据此确认编号从 [1] 起即可。

### 键全局唯一（作者约定，非脚本缺陷）

- `thebibliography` 环境计数器每章自动重置，所以「编号从 [1] 起」天然成立；但 **bibitem 的键（如 `r1`）必须全书唯一**，否则合并时同名键触发 `multiply-defined` 编译错误。
- 多章写作时，**给 bibitem 键加章号前缀**（如第 4 章用 `c4r1`、`c4r2`…），这是作者侧的命名约定，不是脚本 bug——键重名是写章节时自己引入的，须由作者保证唯一（或使用合并构建脚本统一加前缀）。
- `fix_labels.py` 只去重跨章 `\label`，**不处理** `\bibitem` 键；不要把 bibitem 键冲突误归因于脚本（详见 § 16.E）。

### 降级 patch（preamble 层，作者无需改源文件）

模板已预置 etoolbox 补丁，把 `thebibliography` 默认的 `\chapter*{\bibname}`（最大级标题 + 跳页 + 改页眉）重定义为 `\section*{\bibname}`（不跳页、降为 section 级），并去掉 `\@mkboth`（保留原 chapter 页眉）。作者**不需要**在章节源文件里改任何东西——这是 preamble 层的修复。

---

## 15. 页眉页脚

问题：ctexrep 默认 `headings` 把页码放在页眉外侧（奇数页右、偶数页左），章节首页 `plain` 页码在底部正中——混合观察就是「页码有时在上方、有时在下方」。

处理：模板用 `fancyhdr` 接管，页码统一在页脚居中，页眉保留 chapter/section 标题。要点：

- `\setlength{\headheight}{15pt}`（默认 12pt 装不下中文页眉，会警告/裁切）；
- 显式 `\fancyhead[LE,RO]{...}` + `\fancyhead[LO,RE]{...}`（清空后必须重设，否则页眉变空）；
- 重定义 `\fancypagestyle{plain}`（章节首页保持无页眉 + 页码底部居中）。

---

## 16. 踩坑分类速查

> 按主题归类的关键坑。**处理**列指向对应的约定/脚本；细节见各 §。

### A. 编译 / 语法类

- `! Undefined control sequence \chapter`：用了 `article` 类，没有 chapter → 改用 `ctexrep`。
- `! File ended while scanning use of \@xdblarg`：`\subsection{...}` 缺 `}` → `fix.py` 阶段检查闭合。
- `! Argument of \select@language has extra }`：用了 `\zihao{...}` → 改用 `\fontsize{12pt}{18pt}\selectfont`。
- `Runaway argument?`：`\texttt{}` 嵌套 `{}` → `fix.py` 剥离。
- `! Too deeply nested`：tikz 层级过深 → 简化。
- `! LaTeX Error` / `Emergency stop` / `Fatal`：编译致命错误 → 必须修源码，不允许 silent fallback。

### B. 中文与编码类

- 中文文件名乱码（`No file 绗?绔?tex`）：xelatex 读取路径编码问题 → `fix.py` 生成英文名 `chN.tex`。
- `Missing character ... (U+FFFD)`：字体缺失 / GBK 写入 → 全程 UTF-8。
- 圆圈数字 / 五角星 / `≈≤≥` / 希腊字母 报 `Unicode character`：这些符号必须在 math mode（`$\approx$` / `$\alpha$` 等），或在正文可用处改用阿拉伯数字 / 文字。

### C. 表格类

- `! Extra alignment tab changed to \cr`：表格列数 / 表头 / 数据不匹配，或合并单元格缺宏包 → 按 § 10 调齐列数（首列 `l` + N×`X`）。
- 列宽窄、字溢出表边界：用了 `tabular{p{...}}` → 改 `tabularx{\textwidth}{lXXX}`（§ 10）。
- `LaTeX Warning Float specifier changed`：`[ht]` 无效 → 写全 `[htbp]`。
- `! Misplaced \noalign`：混用了 `\hline` 与 booktabs → 删 `\hline`，统一三线。

### D. 图（TikZ）类

- 节点文字超出节点边界：节点未设 `text width` + `align=center` → 按 § 11 补全节点必备属性。
- 同层节点文字重叠：y 坐标全相同 → 上下错半个 `node distance`。
- `\draw[->]` 与其它箭头粗细不一致：未用统一 `arrow/.style` → 全部改 `\draw[arrow]`。
- 图整体宽于版心：`fix.py` 的 wrap_tikz 自动缩放超宽图（§ 11 规则 8）。
- tikz 节点不可断词（`ReLU+BN+MaxPool` 之类）导致溢出：节点内加 `\\` 断行——`emergencystretch` 救不了。

### E. 引用与参考文献类

- `LaTeX Warning undefined references`：`\cite{key}` 在本章内缺对应 `\bibitem` → 补（单章 SOP § 6 step 6 已卡）。
- `multiply-defined` 之 `\label` 跨章重名：`\ref` 指向错误编号 → 整书合并前跑 `fix_labels.py` 按章重命名。
- `multiply-defined` 之 `\bibitem` 键跨章重名：这是**作者命名约定问题**（键必须全书唯一，多章写作时加章号前缀如 `c4r1`），**不是脚本缺陷**；`fix_labels.py` 只处理 `\label`，不处理 bibitem 键。键重名由写章节时引入，须作者保证唯一（或合并构建脚本统一加前缀）。
- 参考文献独占一页 + 标题为 chapter 级：book 类默认 → 模板已用 etoolbox patch 降级（§ 14）。
- 杜绝使用 `\bibitem[5]{r5}` 这类可选标签，让 LaTeX 自动从 [1] 顺序编号（§ 14）。

### F. URL 与超链接类

- 中文 URL 显示空白 / 点击后末尾多出 `%25`：用了 `\url{}` 触发 percent-decode 或双编码 → 用 `\href{raw}{display}`，不要预编码（§ 12）。
- `\href` 显示文本中 `_` 触发 `Missing $ inserted`：raw URL 里的下划线进了 math mode → 显示文本必须转义（§ 12）。
- 所有链接点击无反应：误用 `\let\url\nolinkurl` 杀掉了超链接 → 不要用。
- 中文 URL 显示豆腐 U+FFFD：`url.sty` 在 math mode 渲染，xeCJK 不接管 → 模板已重写 `\Url@FormatString` 去掉 math mode（§ 12）。
- DOI/IEEE/ACM 链接直连 202 或 SSL EOF：多为站点反爬/证书瞬断，非 URL 错误 → `verify_urls.py` 已自动改查 `archive.org` 快照作为稳定镜像；若仍失败再换源（出版社镜像、arXiv、作者主页等）。

### G. 排版溢出类

- `Overfull \hbox`：段落 / 显示公式 / 节点文字超宽 → 缩短内容、显示公式改用 `aligned` 拆行、节点内 `\\` 断行。
- `Underfull \hbox`：仅松散度警告，不阻断。其数量与正文内容量正相关，排版过松时可顺手用 `\sloppy` 或微调 `\XeTeXlinebreakskip` 优化，非强制。
- 段落偶发微小超宽：个别长英文词 / URL 顶到右边距 → preamble 已加 `\emergencystretch{3.5em}` 吸收；仍超则手改源码。

### H. 编译环境 / 进程类

- `xdvipdfmx:fatal: Unable to open "main.pdf"`：PDF 被阅读器锁 → 关闭阅读器或 `-jobname book` 绕开（§ 13）。
- 单行章节文件 `\input` 失败：无换行导致 silent parse 损坏 → `fix.py` 在 `\section` 前后补换行；章节源文件务必正常换行。
- 第二次跑 SOP 找不到 `verify_urls.py` / `find_urls.py`：误删常驻脚本 → `cleanup.py` 只删 `chN.tex` 与 `_tmp.*`，**不删任何 `.py` 脚本**（两者均为常驻脚本，见 § 8）。不要把脚本当一次性文件清理。

### I. 工作流 / 阅读类

- `第N章.pdf` 是 0 字节 / 不存在：`cleanup.py` 先删了 `_tmp.pdf` → 已修正为先复制再清理（顺序敏感）。
- 凭「标题记忆 + 领域知识」扩写章节：只读 chunk 0 就下笔，事实不准 → 必须逐 chunk 读正文（§ 1.C、§ 5）。
- `chunks_read=N CONTINUOUS` 被当成「读过 N 个 chunk」的凭证：`reader.py verify` 只校验覆盖完整性，不等于人类读过 → 必须真读 + 写笔记（§ 5）。

---

## 17. 反例清单

❌ 多章同时写，一次性 `xelatex main.tex`
❌ 用 `-interaction=nonstopmode` 代替 `-halt-on-error`（前者让 LaTeX silent fallback）
❌ 「Output written」就当成功
❌ 用 PowerShell `Set-Content -Encoding UTF8` 写中文 .tex（加 BOM）
❌ 对 .tex 做 `Get-Content | Set-Content` 的 round-trip 改写（编码不一致 silent 损坏）
❌ 章节文件没有换行（单行 inline）
❌ 整书合并时 hack `\chapter` 去掉 clearpage / 冗余 `\renewcommand{\thechapter}`
❌ `_tmp.*` / `chN.tex` 留在章节目录（污染判断）
❌ 单章模式用 `\section` 而不是 `\chapter`
❌ 只读素材前 N 行 / grep 部分就开始写
❌ 凭记忆 / 推断写素材之外的内容
❌ fancyhdr 用 `\fancyhf{}` 清空再只设 `\fancyfoot`（页眉被清空）
❌ fancyhdr 忘加 `\setlength{\headheight}{15pt}`（中文页眉被裁切）
❌ 用 `\urlstyle{rm/same}` / `\renewcommand{\UrlFont}` 修中文 URL 豆腐（三件套全失效）
❌ 预先 percent-encode 中文 URL 再喂 `\href`（双编码）
❌ 把 `\url` 全局重定义为 `\nolinkurl`（杀掉所有超链接）
❌ 只读 chunk 0 标题就跳到 verify（verify ≠ 阅读凭证）
❌ 凭「标题记忆 / 领域知识」扩写章节（必须逐 chunk 读正文）
❌ 跳过 `chapter_init_notes/` 写读后摘要（失去抽查回答凭证）

---

## 18. 章节内容体量基线

| 章节类型 | 中文字符 | 典型页数 | bibitem |
|---------|---------|---------|---------|
| 概念/原理 | 6,000–12,000 | 8–11 | ~20 |
| 数据/规模 | 8,000–15,000 | 10–15 | ~20 |
| 政策/规范 | 5,000–10,000 | 6–9 | 15–20 |
| 技术/机制 | 7,000–13,000 | 9–12 | ~20 |
| 对比/差异 | 6,000–11,000 | 8–10 | ~20 |
| 案例/落地 | 5,000–9,000 | 6–8 | ~15 |

---

## 19. 与其他 skill 的边界

- **不重复**：SVG/HTML 图表类 skill、编辑既有 PDF 的 skill、创建 skill 自身的 skill。
- **协同**：素材采集类 skill 提供素材 → 本 skill 整章节 → 后处理 PDF 的 skill（如需）。
- **不接管**：纯 HTML 报告、Markdown→PDF（pandoc 即可）。

---

## 20. 触发关键词

当对话出现这些词，按本工作流执行：

- 「写报告」「做 PDF」「调报告」「修 .tex」「编译 main.tex」
- 「章节内容」「单章编译」「整书合并」
- 「url 替换」「bibitem」「参考文献」

---

> 本 skill 以「约定前置 + 脚本卡口」为核心：能在写作阶段用规则避免的坑（表格/图/URL 样式），
> 就在 § 10–§ 12 规定清楚；只能在编译后发现的硬错误（日志溢出/断链/缺失字符），
> 用 `check_overflow.py` 等卡口拦截。两者结合，保证中文 LaTeX 报告稳定合规产出。
