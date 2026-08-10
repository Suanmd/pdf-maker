# pdf-maker 详细 SOP（完整版）

本文件是 `SKILL.md` 的详细版：完整命令、参数、模板说明、URL 写法与踩坑速查。
凡 `SKILL.md` 中以「见 references/SOP.md」指代的内容，均在此处展开。

---

## 1. 前置要求（细节）

| 依赖 | 版本 / 说明 | 用途 |
|------|------------|------|
| TeX Live | 2022+，含 `xelatex`、`ctexrep`、`xeCJK` | 编译 LaTeX |
| Python | **3.10+**（脚本用了 `Path \| None` 类型标注） | 运行 `scripts/*.py` |
| `pdfinfo` | poppler，通常随 TeX Live 附带 | PDF 元数据/页数校验（可选） |

**脚本零第三方依赖**：仅用标准库（`argparse`/`re`/`pathlib`/`urllib`/`concurrent.futures` 等），无需 `pip install`。`common.py` 为共享模块，不被单独运行。

---

## 2. 书稿目录布局

```
<PROJECT>/                         # 书稿项目根目录
├── main.tex                       # 整书主控（复制自 assets/templates/main.tex）
├── materials.json                 # 章节 ↔ 素材索引（track_materials.py 维护）
├── figures/                       # 图片资源（\graphicspath{{figures/}}）
├── 第1章/
│   └── 第1章.tex                   # 章节源文件（\chapter 作顶层命令）
├── 第2章/
│   └── 第2章.tex
└── ...（每章一个目录 + 一个 .tex）
```

附录目录命名为 `附录X/附录X.tex`（如 `附录A/附录A.tex`），所有脚本的 `N` 参数可传 `附录X`。

> 脚本通过 CWD 定位源文件：在 `<PROJECT>` 根执行时匹配 `第N章/第N章.tex`；`cd 第N章/` 执行时匹配扁平 `第N章.tex`。两种姿势都支持。

---

## 3. 单章流水线（Phase A）

### 步骤 1 — 强制阅读素材

```bash
cd <PROJECT>
python <PDF_MAKER>/scripts/reader.py index  "<素材 report.md 路径>"
python <PDF_MAKER>/scripts/reader.py chunk  "<素材 report.md 路径>" 0
python <PDF_MAKER>/scripts/reader.py chunk  "<素材 report.md 路径>" 1   # 逐块读完所有 chunk
python <PDF_MAKER>/scripts/reader.py verify "<素材 report.md 路径>"     # 5 字段全过才算读完
```

- `<素材 report.md 路径>` 必须是真实素材报告（如 `.../deep-search/xxx/report.md`）。
- `verify` 前必须先 `index` + 逐 `chunk` 读完；缺任一步 `verify` 直接 FAIL。
- 阅读证明行示例：`📖 完整读完 <path> (<size> / <lines> 行 / <chunks> chunks) verify ✅`。
- 也可用 `reader.py toc <file>` 仅打印标题树，快速浏览结构。

### 步骤 2 — 撰写章节

写 `第N章/第N章.tex`：以 `\chapter{标题}` 作顶层，正文用 `tabularx` 三线表、`\href{URL}{显示文本}` 写链接，章末放 `thebibliography`。详见 §5（URL）、§6（参考文献/标签约定）。

### 步骤 3 — 预处理（fix.py）

```bash
cd <PROJECT>
python <PDF_MAKER>/scripts/fix.py 4          # 处理第 4 章
python <PDF_MAKER>/scripts/fix.py 附录A       # 处理附录 A
# 也可：cd 第4章 && python <PDF_MAKER>/scripts/fix.py 4
```

作用：读取 `assets/templates/_tmp.tex`，把占位符 `CHAPTER_TEX` 替换为实际章节中间文件名（`chN.tex` / `附录X_ch.tex`），写出 `第N章/_tmp.tex`；同时生成 `第N章/chN.tex`（URL 规范化后的干净章节副本）。`fix.py` **必须**在 `<PROJECT>` 根或 `第N章/` 内执行（脚本目录兜底定位）。

### 步骤 4 — 结构校验（check + check_balance）

```bash
python <PDF_MAKER>/scripts/check.py 4
python <PDF_MAKER>/scripts/check_balance.py 4
```

- `check.py`：输出字数 / 层级 / 元素计数（只统计不阻断）。
- `check_balance.py`：小节字数、表格数、配图数（建议每章 ≥ 1 张）、引用闭合（孤儿 bibitem / 悬空 cite）检查。**质量软告警，不硬阻断**（如个别小节偏短、建议表数 ≥ 4、建议配图 ≥ 1）。

### 步骤 5 — 联网验活（verify_urls，强制）

```bash
python <PDF_MAKER>/scripts/verify_urls.py 4                 # 验活第 4 章全部 URL
python <PDF_MAKER>/scripts/verify_urls.py 第4章/第4章.tex    # 或直接传 .tex 路径
```

- 抽取章节全部 `\href{}`/URL → 本地格式校验（ASCII / 无空格 / 合法 scheme）→ 联网逐 URL 检测。
- 直连 2xx/3xx 记 **LIVE**；直连失败再查 `web.archive.org` 快照记 **ARCHIVE**（不阻断）；既失败又无快照记 **DEAD**。
- **退出码即 SOP 决策**：`0` 全过可继续 / `1` 失效或虚构链接必须修 / `2` 离线未验活须联网重跑（禁止静默放过）。
- 出现 DEAD（exit 1）：**替换**为素材正文中另一条同主题真实 LIVE 链接，并重跑直到 exit 0。本 skill 不做自动替换，由作者人工选源以保证准确性。

### 步骤 6 — 编译（xelatex ×2）

```bash
cd <PROJECT>/第4章
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
```

> **强约束**：单章必须 `cd` 进 `第N章/` 内编译。否则 `\input{chN.tex}` 报 `File not found`——本机 xelatex 不把主文件目录加入搜索路径。

### 步骤 7 — 日志体检（check_overflow）

```bash
cd <PROJECT>/第4章
python <PDF_MAKER>/scripts/check_overflow.py _tmp.log
# 或省略路径：python <PDF_MAKER>/scripts/check_overflow.py  （自动找 _tmp.log / main.log）
```

拦截：`Overfull` / `Missing character` / `multiply-defined` / `undefined references` / `Fatal`。**阻断级**（如 Fatal、undefined references）必须修；`Underfull` 等非阻断警告通常可忽略。

### 步骤 8 — 清理落盘（cleanup）

```bash
cd <PROJECT>
python <PDF_MAKER>/scripts/cleanup.py 4
```

复制 `_tmp.pdf → 第N章.pdf`，其余中间文件（`_tmp.tex`/`chN.tex`/`.aux`/`.log`/`.out`）**移动**到 `第N章/_tmp_old/`（移动而非删除，便于追溯）。章节目录保持只有 1 个源 `.tex` + 1 个成品 `.pdf`。

### 步骤 9 — 更新素材追踪

```bash
python <PDF_MAKER>/scripts/track_materials.py update <PROJECT> 第4章 <size_bytes> <total_lines> <chunks_count>
```

三个整数取自 `reader.py verify` 输出（`size_bytes` / `total_lines` / `chunks_count`）。其余子命令：`init` / `show` / `check` / `auto-init` / `bib-audit`。`check` 与 `update` 必须同时传 `<PROJECT>` 和 `<chapter>`。

---

## 4. 整书合并流水线（Phase B）

1. **跨章去重**：`python <PDF_MAKER>/scripts/fix_labels.py <PROJECT>`（扫描所有 `第*章`/`附录*` 目录，重复 `\label` 按章重命名；0 冲突时静默通过）。
2. **编译**：在 `<PROJECT>` 根执行 `xelatex main.tex` **两次**（第二遍解析交叉引用）。
3. **体检**：`python <PDF_MAKER>/scripts/check_overflow.py main.log`。
4. **元数据校验**：`pdfinfo main.pdf` 确认 `Title` / `Author` 与 `main.tex` 中 `{{PDF_TITLE}}` / `{{AUTHOR}}` 一致。
5. **收尾**：保留 `main.tex` 与 `main.pdf`；删 `main.aux`/`main.log`/`main.out`/`main.toc`。

---

## 5. URL 写法（中文 / 特殊字符）

- **必须用** `\href{raw-url}{display-text}`；**不要用** `\url{}`（会触发 hyperref 的 percent-decode bug，中文易出错）、`\nolinkurl`（杀掉超链接）。
- `fix.py` 已自动把章节里的 `\url{...}` 转成 `\href{raw}{display}`，但**手写新链接**时直接写 `\href` 最稳妥。
- `hyperref` 自动把 raw-url percent-encode 写入 PDF 注解（不会双编码）；**不要**预先 percent-encode 再进 `\href`。
- 显示文本走 verbatim 解析，其中的 LaTeX 特殊字符需转义：`_` → `\_`、`&` → `\&`、`$` → `\$`、`#` → `\#`、`%` → `\%`、`\` → `\textbackslash{}`。
- 配套 hyperref 设置（`main.tex` / `_tmp.tex` 已预置，无需重复）：
  ```latex
  \usepackage[unicode]{hyperref}
  \hypersetup{colorlinks=true, linkcolor=blue, urlcolor=blue, citecolor=blue}
  ```

---

## 6. 参考文献与标签约定

- **bibitem 键加章号前缀**：`c1r1`、`c2r3`…（第 N 章第 M 条）。保证跨章不冲突。
- **`\cite` 必有对应 `\bibitem`**：`check_balance.py` 会检测孤儿 bibitem 与悬空 cite。
- **`\label` 加章号前缀**：如 `\label{sec:c3-food}`；`fix_labels.py` 作为兜底再扫一遍跨章重复。
- 章末 `thebibliography` 用 `\bibitem{cNrM} 作者. 标题[EB/OL]. \href{url}{display}` 形式。

---

## 7. 模板说明

### assets/templates/_tmp.tex（单章 preamble 唯一真源）

- `fix.py` 读取本文件，把 `\input{CHAPTER_TEX}` 替换为实际章节中间文件（`chN.tex` / `附录X_ch.tex`），写出 `第N章/_tmp.tex` 交 xelatex 编译。
- 已预置关键补丁，章节源文件无需关心：`中文 URL 支持`、`参考文献降级 + 不跳页 + 不改页眉`、`代码块环境 codeblock`、`图片宽度上限 adjustbox`、`emergencystretch 防溢出`。
- **禁止**在 `fix.py` 内再内联一份 preamble 副本（双源漂移）。

### assets/templates/main.tex（整书主控）

- 合并时所有章节的唯一入口，把各章 `\input` 进来，统一页面/页眉页脚/参考文献样式。
- 使用步骤：
  1. 替换 `{{TITLE}}` / `{{SUBTITLE}}` / `{{EPIGRAPH}}` / `{{EPIGRAPH_CLOSING}}` / `{{AUTHOR}}` / `{{DATE}}` / `{{PROJECT}}` / `{{PDF_TITLE}}` 占位符。
     - `{{TITLE}}` 用于扉页显示，可含 `\\`；`{{PDF_TITLE}}` 用于 PDF 元数据，**必须单行、不含 `\\`**。
  2. 在「正文各章」处把章节列表占位符 `{{CHAPTERS_LIST}}` 替换为每章一行 `\input{第N章/第N章}`。
  3. 不需要扉页/序言/附录/结尾段，删除对应整块。
  4. `xelatex` 跑两遍。
  5. 收尾删 `main.aux/log/out/toc`。
- `_tmp.tex` 与 `main.tex` 同步关键补丁；差异（twoside / geometry / fancyhdr）是「预览 vs 成书」的有意区分，非双源漂移。

---

## 8. 命令参考（权威接口）

所有脚本均支持 `-h` 查看示例。以下为准确参数：

| 脚本 | 用法 | 说明 |
|------|------|------|
| `reader.py` | `reader.py {index,chunk,verify,toc} <file> [chunk_no]` | 素材三阶段校验；`verify` 前须 `index`+逐 `chunk` |
| `track_materials.py` | `track_materials.py {init,show,check,update,auto-init,bib-audit} <PROJECT> [chapter] [size lines chunks]` | 阅读状态追踪；`check`/`update` 须传 `<PROJECT>`+`<chapter>` |
| `fix.py` | `fix.py [chapter]`（默认 1） | 单章预处理，生成 `chN.tex` + `_tmp.tex` |
| `check.py` | `check.py [chapter]` | 内容结构统计 |
| `check_balance.py` | `check_balance.py [chapter]` | 结构/引用均衡（小节字数 / 表格 / 配图建议 / 引用闭合，软告警） |
| `verify_urls.py` | `verify_urls.py <target>`（`N` 或 `.tex` 路径） | 联网验活，exit 0/1/2 |
| `check_overflow.py` | `check_overflow.py [log]` | 日志体检，省略则自动找 `_tmp.log`/`main.log` |
| `cleanup.py` | `cleanup.py [chapter]` | 落盘 + 归档中间文件 |
| `fix_labels.py` | `fix_labels.py [root]`（默认 CWD） | 跨章 `\label` 去重 |

---

## 9. 踩坑速查

| 主题 | 现象 | 解决 |
|------|------|------|
| 编译路径 | `\input{chN.tex}` File not found | 单章必须 `cd 第N章/` 内编译；整书必须在根 |
| 死链 | `verify_urls.py` exit 1（DEAD） | 替换为素材正文中另一条同主题 LIVE 链接，重跑 |
| 中文 URL 豆腐块 | `\url{}` 中文显示异常 | 改用 `\href{raw}{display}` |
| 溢出 | Overfull `\hbox` | 改源码超宽处；`emergencystretch` 仅吸收微小超宽 |
| 双源漂移 | 模板改了但编译没变 | 只改 `assets/templates/` 下模板，禁止脚本内联副本 |
| 重复标签 | `multiply-defined` 警告 | 运行 `fix_labels.py` |
| 脚本找不到章 | resolve_source 报错 | 在 `<PROJECT>` 根或 `第N章/` 内执行；不要只在 `scripts/` 目录跑 |
| 附录 | glob 只匹配 `第*章` | 所有命令的 `N` 支持 `附录X`，无需特殊姿势 |

---

## 10. 共享模块 common.py

`scripts/common.py` 集中存放被多脚本复用的纯函数，消除历史上「每个脚本各写一份 `resolve_source` / `strip_blocks`」导致的多份漂移补丁：

- `setup_utf8()` — Windows 控制台中文输出修复（幂等，try/except 包裹）。
- `resolve_source(arg, tool)` — 把 `N` / `附录X` / `.tex` 路径解析为章节源文件绝对路径（CWD 优先、脚本目录兜底）；找不到时 `raise SystemExit` 并列出尝试路径。
- `mid_name_for(arg)` — 返回中间文件名（`chN.tex` / `附录X_ch.tex`），与 `fix.py` 一致。
- `workdir_for(arg)` — 定位章节工作目录（`_tmp.pdf` 所在目录），`cleanup.py` 用。
- `strip_blocks(text)` / `chinese_count(text)` — 去表格/图/verbatim 逐字块后统计中文字数。

被 `fix.py` / `check.py` / `check_balance.py` / `verify_urls.py` / `cleanup.py` 显式 import；`reader.py` / `track_materials.py` / `check_overflow.py` / `fix_labels.py` 仅复用 `setup_utf8()`。
