# pdf-maker

> 中文 LaTeX 报告/书籍工程化工具。基于 `xelatex + ctexrep + xeCJK`，把零散章节稳定产出为排版合规的中文 PDF。

`pdf-maker` 把「写一份像样的中文 PDF 报告/书」这件容易翻车的事，固化成一条受控流水线：
**单章独立编译 → 整书合并**，并在每个关键节点设置质量关卡（素材强制阅读、URL 联网验活、编译日志体检、跨章标签去重）。

## 特性

- **双模式工作流**：单章独立编译 ↔ 整书合并，章节源文件保持干净。
- **源码预处理**（`fix`）：`\url{} → \href{raw}{display}` 规范化、TikZ 图宽上限、生成 `chN.tex` + `_tmp.tex`。
- **素材强制阅读校验**（`reader` 三阶段）：杜绝「读一半就写」。
- **联网验活**（`verify`）：逐 URL 检测可达性，死链必须修（exit 0/1/2）。
- **编译日志体检**（`overflow`）：拦截 Overfull / Missing character / 断链 / 缺字符 / Fatal。
- **跨章 `\label` 去重**（`labels`）。
- **零第三方依赖**：仅用 Python 标准库，无需 `pip install` 任何包；模板随包分发。

适用：中文技术报告、调研报告、白皮书、论文（每章 5–15 页，≤ 30 章规模）。

## 环境要求

| 依赖 | 版本 / 说明 |
|------|------------|
| TeX Live | 2022+（含 `xelatex`、`ctexrep`、`xeCJK`） |
| Python | **3.10+** |
| `pdfinfo` | poppler，通常随 TeX Live 附带（可选，用于元数据校验） |

> 工具本身零第三方依赖，不需要安装任何 PyPI 包。

## 安装

### 作为 Python 包（推荐，开源用法）

```bash
# 从源码可编辑安装（开发用）
cd pdf-maker
pip install -e .

# 或直接构建安装
pip install .
```

安装后即可使用 `pdfmaker` 命令或 `python -m pdfmaker`：

```bash
pdfmaker --help
python -m pdfmaker build .
```

### 作为 WorkBuddy 技能

把本仓库放到任意技能加载路径即可（脚本通过当前工作目录 CWD 定位书稿项目）：

```bash
# 用户级（跨项目可用）
cp -r pdf-maker ~/.workbuddy/skills/pdf-maker/

# 或项目级（仅当前仓库协作者可用）
cp -r pdf-maker <your-project>/.workbuddy/skills/pdf-maker/
```

## 快速开始

### 1. 生成书稿骨架

`scaffold` 会把内置的 `main.tex` / `_tmp.tex` 模板落地为可编译起点，并按需生成章节占位：

```bash
python -m pdfmaker scaffold my-report                 # 生成 my-report/（默认 1 章）
python -m pdfmaker scaffold . --chapters N            # 在当前目录生成 N 章骨架
python -m pdfmaker scaffold book --title "我的书" --author 张三
```

生成的目录：

```
my-report/
  main.tex        # 整书主控（占位符已填默认 / 由参数指定）
  _tmp.tex        # 单章编译 preamble 模板（fix 用）
  第1章/
    第1章.tex     # 章节占位源
```

> 你也可以手动从包内模板复制（无需安装包）：
> `python -m pdfmaker` 会自动从包数据 `pdfmaker.templates` 定位 `main.tex` / `_tmp.tex`；
> `fix` 与 `build` 命令都从包内读取，不必把模板复制到项目里。

### 2. 写一章（完整 SOP）

在**书稿项目根目录 `<PROJECT>`** 下执行，**无需把工具/模板复制进项目**：

```bash
cd <PROJECT>

# 1) 强制阅读素材（推荐一键通读；也可 index+chunk+verify 三阶段）
python -m pdfmaker reader ingest "<素材 .md 路径>"

# 2) 撰写 第1章/第1章.tex

# 3) 预处理（生成 ch1.tex + _tmp.tex）
python -m pdfmaker fix 1

# 4) 结构校验
python -m pdfmaker check 1
python -m pdfmaker balance 1

# 5) 联网验活（强制；exit 0 继续 / 1 修链接 / 2 离线重跑）
python -m pdfmaker verify 1

# 6) 编译（必须 cd 进章目录）
cd 第1章 && xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex && cd ..

# 7) 日志体检
python -m pdfmaker overflow 第1章/_tmp.log

# 8) 清理落盘
python -m pdfmaker cleanup 1

# 9) 更新素材追踪（三整数反映「章节」自身：.tex 字节数 / 行数 / 已读素材 chunk 数）
python -m pdfmaker track update <PROJECT> 第1章 <size> <lines> <chunks>
#   --material <素材.md>：把该素材写入 source_files，便于追溯关联素材
python -m pdfmaker track update <PROJECT> 第1章 <size> <lines> <chunks> --material 素材-第1章.md
#   --no-verify / verify 离线退出 2 时加 --unverified，明确标记本章未验活
python -m pdfmaker track update <PROJECT> 第1章 <size> <lines> <chunks> --unverified
```

`overflow` 若不传日志路径，会在当前目录自动寻找 `_tmp.log` / `main.log`。

### 3. 整书合并

所有章节 OK 后，**统一用 `build` 一键合并**（自动跑 `labels` → `xref`
预检 → 规范化 → `xelatex` 两遍 → `overflow` → 落盘 `main.pdf`；规范化与单章同一套
`normalize_text`，确保 TikZ/URL 处理完全一致）：

```bash
cd <PROJECT>
python -m pdfmaker build .              # 合并，exit 0 即成功
python -m pdfmaker build . --verify     # 合并前额外联网验活全书 URL
pdfinfo main.pdf                        # 校验 Title / Author 元数据
```

> 不要手敲 `xelatex main.tex`——那会直接 `\input` 原始章节、漏掉规范化，导致「单章不溢出、
> 合并却 Overfull」。

## 项目结构

```
pdf-maker/
├── README.md                      # 本文件
├── LICENSE                        # MIT
├── CHANGELOG.md                   # 版本里程碑
├── CONTRIBUTING.md                # 贡献指南
├── pyproject.toml                 # 打包（setuptools，零第三方依赖）
├── .gitignore
└── src/
    └── pdfmaker/                  # 标准 Python 包（可 pip install -e .）
        ├── __init__.py            #   版本号
        ├── __main__.py            #   python -m pdfmaker 入口
        ├── cli.py                 #   子命令分发
        ├── py.typed               #   类型标记
        ├── core/                  #   共享纯函数（路径/文本/规范化/章节/lint）
        │   ├── paths.py           #     路径定位 / UTF-8 / 模板定位
        │   ├── text.py            #     字数统计（剔除表格/图/code）
        │   ├── normalize.py       #     单一规范化真源（URL→href + TikZ 上限）
        │   ├── chapters.py        #     章节枚举
        │   └── lint.py            #     编译前风险预检（缺字/截断URL/TikZ/Frontmatter/三线表/伪代码样式）
        ├── commands/              #   每个子命令一个模块，暴露 main(argv)->int
        │   ├── fix.py             #     单章预处理
        │   ├── check.py           #     结构统计 + 风险预检 + 排版样式门禁（三线表/伪代码，阻断级）
        │   ├── balance.py         #     结构/引用均衡（阻断/建议分明）
        │   ├── overflow.py        #     编译日志体检（硬卡口）
        │   ├── xref.py            #     合并前引用预检
        │   ├── verify.py          #     联网验活（exit 0/1/2）
        │   ├── build.py           #     整书合并唯一入口
        │   ├── chapter.py         #     单章九步 SOP 一键编排
        │   ├── cleanup.py         #     成品落盘 + 归档
        │   ├── labels.py          #     跨章 label 去重
        │   ├── reader.py          #     素材阅读校验
        │   ├── track.py           #     章节↔素材阅读状态追踪
        │   └── scaffold.py        #     初始化书稿骨架
        └── templates/             #   包内 LaTeX 模板 + 章节阅读笔记模板（main.tex / _tmp.tex / chapter_init_notes_template.md）
```

## 命令参考

所有命令均支持 `-h` 查看准确参数与示例。核心子命令：

| 命令 | 用法 | 说明 |
|------|------|------|
| `scaffold` | `scaffold <dir> [--title T] [--author A] [--chapters N] [--appendices M] [--force]` | 初始化书稿骨架（`--force` 允许非空目录，已存在文件跳过不覆盖） |
| `reader` | `reader {ingest,index,chunk,verify,toc,clean} <file>` | 素材校验；`ingest` 一键通读；`clean` 清阅读状态 |
| `track` | `track {init,show,check,update,auto-init,bib-audit} <PROJECT> [chapter] [size lines chunks]` | 阅读状态追踪 |
| `fix` | `fix [chapter]`（默认 1） | 单章预处理（生成 `chN.tex` + `_tmp.tex`） |
| `check` | `check [chapter] [--min-chars N] [--no-gate]` | 内容结构统计 + 编译前风险预检 + **排版样式门禁（三线表禁用 `\hline`/`|`、伪代码禁用裸 `verbatim`/`lstlisting`，阻断级）** + 字数硬门禁（低于下限 exit 1） |
| `balance` | `balance [chapter]` | 结构/引用均衡（阻断项 exit 1，建议项不阻断） |
| `xref` | `xref [target]`（`.` 或 `N` 或 `.tex`） | 合并前预检：越界「第N章」引用 / 跨章 `\ref` |
| `verify` | `verify <target>`（`N` / `.tex` / `.` 整书）`[--retries N] [--timeout S] [--cache P] [--refresh]` | 联网验活（exit 0/1/2；401/403/429 算 LIVE；结果可缓存） |
| `build` | `build [root]`（默认 `.`）`[--verify] [--no-preflight]` | **整书合并唯一入口** |
| `chapter` | `chapter <N> [--material F] [--project P] [--xelatex X] [--no-verify] [--no-track]` | **单章九步 SOP 一键编排**：reader→fix→check→balance→verify→xelatex×2→overflow→cleanup→track，任一步阻断即中止 |
| `overflow` | `overflow [log]` | 日志体检，省略则自动找 `_tmp.log`/`main.log` |
| `cleanup` | `cleanup [chapter]` | 落盘 + 归档中间文件 |
| `labels` | `labels [root]`（默认 CWD） | 跨章 `\label` 去重 |

## 配置与环境变量

所有可调项集中在 `src/pdfmaker/core/config.py`，**统一通过 `PDFMAKER_` 前缀的环境变量覆盖**，
无需改代码即可按项目调参（CI / 受限网络环境尤其有用）：

| 环境变量 | 默认 | 作用 |
|----------|------|------|
| `PDFMAKER_CHAPTER_MIN_CHARS` | `2000` | `check` 整章字数硬门禁下限；项目要求如 4000 字/章则设 `4000` |
| `PDFMAKER_URL_TIMEOUT` | `30.0` | `verify` 单 URL 超时（秒） |
| `PDFMAKER_URL_RETRIES` | `3` | `verify` 单 URL 重试次数 |
| `PDFMAKER_URL_WORKERS` | `8` | `verify` 并发线程数 |
| `PDFMAKER_BACKOFF` | `2.0` | `verify` 重试退避基数（秒） |
| `PDFMAKER_USER_AGENT` | `Mozilla/5.0 (pdf-maker verify) compatible` | `verify` 请求 UA |
| `PDFMAKER_PROBE_HOSTS` | `example.com,archive.org,w3.org` | `verify` 离线连通性探针主机 |
| `PDFMAKER_VERIFY_CACHE_TTL_DAYS` | `7` | `verify` 结果缓存新鲜度（天） |
| `PDFMAKER_VERIFY_CACHE_DIR` | `~/.cache/pdfmaker` | `verify` 结果缓存目录 |
| `PDFMAKER_READER_STATE_DIR` | `~/.cache/pdfmaker/reader` | `reader` 阅读状态存放目录（全局缓存，不污染内容目录） |
| `PDFMAKER_CHUNK_SIZE_CN` / `_EN` | `200` / `320` | `reader` 中/英文素材单 chunk 行数 |

### 质量门禁说明

- **`check` 字数硬门禁**：正文（去表格/图/代码块后）中文字数低于 `--min-chars`（默认
  `PDFMAKER_CHAPTER_MIN_CHARS`）时 **exit 1 阻断**，SOP 流程应停在此处补写正文。附录 / 短章
  等合法短章节用 `--no-gate` 放行。
- **`verify` 状态码语义**：`2xx/3xx` → LIVE；`404/410` → DEAD（必须修）；`401/403/429` → LIVE
  （地址有效，仅访问受限 / 限流，**不再误杀**）；`400/405/406/407` → LIVE（服务端拒绝该请求方式但
  主机在线，地址有效，**不误杀**）；`408/425` 与 `5xx` / 网络抖动 → 指数退避重试，耗尽仍不通且无
  存档 → TRANSIENT（exit 2）；`451` → 转 archive.org 兜底（有则 ARCHIVE，否则 DEAD）。
- **`verify` 结果缓存**：默认写 `~/.cache/pdfmaker/verify_cache.json`，新鲜期内（默认 7 天）且非
  TRANSIENT 的结果直接复用、不再联网；`--refresh` 强制重验；离线时**能复用多少复用多少**——
  缓存中新鲜的确定性结论（LIVE/ARCHIVE/DEAD）直接并入结果，未缓存/过期项单独标 TRANSIENT 并在
  明细中可见（不再像旧版那样「非全命中即整段丢弃、直接 exit 2 且不打印任何明细」）。
- **`verify` 离线探针兜底**：默认连通性探针主机（`PDFMAKER_PROBE_HOSTS` / `probe_hosts`）全部
  不可达时，会进一步**直接探测待验 URL 中的真实目标**（前 3 个、短超时）；只要任一目标可响应即视为
  在线，避免受限于代理白名单把「其实能访问的站点」误判为离线而 exit 2。
- **`reader` 状态位置**：阅读状态统一收口到全局缓存目录（默认 `~/.cache/pdfmaker/reader`），
  **不再在素材同目录生成 `.reader-state-*.json` 点文件**。清残留用 `reader clean <dir> --apply`；
  清全局缓存用 `reader clean --global --apply`。

## 项目级配置（`.pdfmaker.toml`）

除环境变量外，还可在**书稿项目根目录**放一个 `.pdfmaker.toml`，让配置随项目走、不再依赖每次手动设环境变量。`cli` 在分发子命令前会自动向上回溯查找并加载，**无需任何额外参数**。

优先级：**环境变量 > `.pdfmaker.toml` > 代码默认**（设了环境变量则该键忽略 toml）。

```toml
[pdfmaker]
chapter_min_chars = 4000         # 覆盖 PDFMAKER_CHAPTER_MIN_CHARS
min_chars        = 4000          # balance 全书/整章下限
min_tables       = 2             # balance 每章表格下限
min_images       = 1             # balance 每章配图下限
url_timeout      = 20.0          # 覆盖 PDFMAKER_URL_TIMEOUT
url_workers      = 12            # 覆盖 PDFMAKER_URL_WORKERS
probe_timeout    = 4.0           # 覆盖 PDFMAKER_PROBE_TIMEOUT
url_retries      = 4             # 覆盖 PDFMAKER_URL_RETRIES
backoff          = 2.0           # 覆盖 PDFMAKER_BACKOFF
user_agent       = "Mozilla/5.0 (pdf-maker) compatible"  # 覆盖 PDFMAKER_USER_AGENT
verify_cache_ttl_days = 7        # 覆盖 PDFMAKER_VERIFY_CACHE_TTL_DAYS
chunk_size_cn    = 200           # 覆盖 PDFMAKER_CHUNK_SIZE_CN
chunk_size_en    = 320           # 覆盖 PDFMAKER_CHUNK_SIZE_EN
max_bytes_per_read = 200000      # 覆盖 PDFMAKER_MAX_BYTES_PER_READ
xelatex          = "xelatex"     # 覆盖 PDFMAKER_XELATEX；留空或 "xelatex" 时运行时沿 PATH 自动探测

# 离线探针主机（覆盖 PDFMAKER_PROBE_HOSTS），默认 example.com,archive.org,w3.org
probe_hosts = ["https://arxiv.org", "https://doi.org", "https://link.springer.com"]

# 参考文献权威站点提示（bib-audit / 验活判 LIVE 时加权），覆盖默认清单
authority_hints = ["doi.org", "arxiv.org", "springer.com", "link.springer.com",
                   "springeropen.com", "frontiersin.org", "ieee.org", "mdpi.com",
                   "acm.org", "nature.com", "science.org", "wiley.com", "stanford.edu"]

# 阅读状态 / 验活缓存目录（覆盖默认 ~/.cache/pdfmaker/...）
reader_state_dir = "~/.cache/pdfmaker/reader"
verify_cache_dir = "~/.cache/pdfmaker"
```

> 查找规则：从当前工作目录（或 `--project` 指定目录）向上逐级父目录回溯，命中最近的 `.pdfmaker.toml` 即停止。`chapter` / `build` / `check` / `balance` / `verify` / `track` 全部受益（例如 `chapter` 编排里 `check` 的字数门禁会直接套用 `chapter_min_chars=4000`）。

### 排版符号自动修复（glyph auto-fix）

`fix` 与 `build` 在规范化阶段（同一套 `normalize_text`）会**自动把常见 Unicode 数学/圈号字符转为 LaTeX 安全写法**，避免 `xelatex` 报 Missing character 或 PDF 显示豆腐块：

| 输入字符 | 转写 |
|----------|------|
| `≥` `≤` `≈` `≠` | `\ge` `\le` `\approx` `\neq` |
| ①–⑩ | `(1)`–`(10)` |

受保护片段（URL、`\href{}`、`\verb`、`verbatim`、`codeblock`）内的字符**不转换**，确保链接与代码原样保留。该步骤幂等，纯 ASCII 文本无任何影响。

### 单章九步一键编排（`chapter`）

不想逐步手敲 9 条命令时，用 `chapter` 一条命令跑完整 SOP：

```bash
cd <PROJECT>
python -m pdfmaker chapter 3                 # 第 3 章全链路：reader→fix→check→balance→verify→xelatex×2→overflow→cleanup→track
python -m pdfmaker chapter 3 --material 素材.md   # 顺带先 ingest 指定素材
python -m pdfmaker chapter 3 --no-verify     # 离线时跳过联网验活
python -m pdfmaker chapter 3 --no-track      # 跳过素材追踪更新
python -m pdfmaker chapter 3 --xelatex "/path/to/xelatex"  # 显式指定编译引擎
```

- 编排顺序严格遵循 SOP：`check` 与 `balance` 为**硬卡口**（exit≠0 立即中止，便于就地补正文/补结构）；`verify` 仅 `exit 1`（死链）阻断、`exit 2`（离线/瞬时）仅告警继续；`xelatex` 连跑两遍（cd 进章目录，`--halt-on-error`）；`track update` 若章节尚未登记会自动 `init` 再写，无需先手动登记。
- 编译引擎解析顺序：`--xelatex` > 环境变量 `PDFMAKER_XELATEX` > `.pdfmaker.toml` 的 `xelatex` > 运行时沿 PATH 探测（与 `build` 同一套 `find_xelatex`）。

## URL 写法（中文 / 特殊字符）

- **必须用** `\href{raw-url}{display-text}`；**不要用** `\url{}`（会触发 hyperref 的 percent-decode bug，中文易出错）、`\nolinkurl`（杀掉超链接）。
- `fix` 已自动把章节里的 `\url{...}` 转成 `\href{raw}{display}`（`url_to_href` 实现），但**手写新链接**时直接写 `\href` 最稳妥。
- `hyperref` 自动把 raw-url percent-encode 写入 PDF 注解（不会双编码）；**不要**预先 percent-encode 再进 `\href`。
- 显示文本里的 LaTeX 特殊字符需转义：`_` → `\_`、`&` → `\&`、`$` → `\$`、`#` → `\#`、`%` → `\%`、`\` → `\textbackslash{}`。

## 参考文献与标签约定

- **bibitem 键加章号前缀**：`c1r1`、`c2r3`…（第 N 章第 M 条），保证跨章不冲突。
- **`\cite` 必有对应 `\bibitem`**：`balance` 会检测孤儿 bibitem 与悬空 cite。
- **`\label` 加章号前缀**：如 `\label{sec:c3-food}`；`labels` 作为兜底再扫一遍跨章重复。
- 章末 `thebibliography` 用 `\bibitem{cNrM} 作者. 标题[EB/OL]. \href{url}{display}` 形式。

## 模板说明

### `templates/_tmp.tex`（单章 preamble 唯一真源）

- `fix` 读取本文件，把 `\input{CHAPTER_TEX}` 替换为实际章节中间文件（`chN.tex` / `附录X_ch.tex`），写出 `第N章/_tmp.tex` 交 xelatex 编译。
- 已预置关键补丁，章节源文件无需关心：`中文 URL 支持`、`参考文献降级 + 不跳页 + 不改页眉`、`代码块环境 codeblock`、`图片宽度上限 adjustbox`、`emergencystretch 防溢出`。
- **禁止**在 `fix` 内再内联一份 preamble 副本（双源漂移）。

### `templates/main.tex`（整书主控）

- 合并时所有章节的唯一入口，把各章 `\input` 进来，统一页面/页眉页脚/参考文献样式。
- 使用步骤：
  1. 替换 `{{TITLE}}` / `{{SUBTITLE}}` / `{{EPIGRAPH}}` / `{{EPIGRAPH_CLOSING}}` / `{{AUTHOR}}` / `{{DATE}}` / `{{PDF_TITLE}}` 占位符。
     - `{{TITLE}}` 用于扉页显示，可含 `\\`；`{{PDF_TITLE}}` 用于 PDF 元数据，**必须单行、不含 `\\`**。
  2. 在「正文各章」处把 `{{CHAPTERS_LIST}}` 替换为每章一行 `\input{第N章/第N章}`。
  3. 不需要扉页/序言/附录/结尾段，删除对应整块。
  4. `xelatex` 跑两遍。
  5. 收尾删 `main.aux/log/out/toc`。
- `_tmp.tex` 与 `main.tex` 同步关键补丁；差异（twoside / geometry / fancyhdr）是「预览 vs 成书」的有意区分，非双源漂移。

## 关键概念

- **双模式**：单章独立编译（每章 `\chapter` → 验证 → 下一章）与整书合并（`main.tex` `\input` 各章 → `main.pdf`）二选一，混用即 bug。
- **单一规范化真源**：`normalize_text()` = `url_to_href()` + `wrap_tikz()`，单章与合并共用，幂等，从根上消除双源漂移。
- **三阶段阅读**：动笔前 `reader` 跑 `index → chunk → verify`，确保素材被完整通读；
  阅读状态存放在全局缓存目录（`~/.cache/pdfmaker/reader`），不污染书稿内容目录。
- **日志体检**：编译后必须跑 `overflow`，把阻断级信号拦在交付前。

## 开发

```bash
pip install -e .               # 可编辑安装
python -m pdfmaker --help      # 查看子命令
```

## 贡献

欢迎提交 Issue 与 Pull Request。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。改动保持单一职责、显式 `import`，共享逻辑进 `pdfmaker.core`。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
