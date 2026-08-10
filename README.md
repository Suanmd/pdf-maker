# pdf-maker

> 中文 LaTeX 报告工程化 skill。基于 `xelatex + ctexrep + xeCJK`，把零散章节稳定产出为排版合规的中文 PDF。

`pdf-maker` 把「写一份像样的中文 PDF 报告/书」这件容易翻车的事，固化成一条受控流水线：
**单章独立编译 → 整书合并**，并在每个关键节点设置质量关卡（素材强制阅读、URL 联网验活、编译日志体检、跨章标签去重）。

## 特性

- **双模式工作流**：单章独立编译 ↔ 整书合并，章节源文件保持干净。
- **源码预处理**（`fix.py`）：`\url{} → \href{raw}{display}` 规范化、TikZ 图宽上限、生成 `chN.tex` + `_tmp.tex`。
- **素材强制阅读校验**（`reader.py` 三阶段）：杜绝「读一半就写」。
- **联网验活**（`verify_urls.py`）：逐 URL 检测可达性，死链必须修（exit 0/1/2）。
- **编译日志体检**（`check_overflow.py`）：拦截 Overfull / Missing character / 断链 / 缺字符 / Fatal。
- **跨章 `\label` 去重**（`fix_labels.py`）。
- **零第三方依赖**：脚本只用 Python 标准库，无需 `pip install`。

适用：中文技术报告、调研报告、白皮书、论文（每章 5–15 页，≤ 30 章规模）。

## 环境要求

| 依赖 | 版本 / 说明 |
|------|------------|
| TeX Live | 2022+（含 `xelatex`、`ctexrep`、`xeCJK`） |
| Python | **3.10+**（脚本用到 `Path \| None` 类型标注） |
| `pdfinfo` | poppler，通常随 TeX Live 附带（可选，用于元数据校验） |

> 脚本仅用标准库，不需要安装任何 PyPI 包。

## 安装

把本目录（含 `SKILL.md` / `scripts/` / `assets/` / `references/`）放到任意 skill 加载路径。装在哪都不影响使用——脚本通过当前工作目录（CWD）定位书稿项目：

```bash
# 用户级（跨项目可用）
cp -r pdf-maker ~/.workbuddy/skills/pdf-maker/

# 或项目级（仅当前仓库协作者可用）
cp -r pdf-maker <your-project>/.workbuddy/skills/pdf-maker/
```

下文的 `<PDF_MAKER>` 即本 skill 的安装根目录（如 `~/.workbuddy/skills/pdf-maker`）。

## 快速开始

### 1. 新建书稿项目

```bash
mkdir my-report && cd my-report
mkdir figures 第1章 第2章 第3章
# 复制整书模板：<PDF_MAKER>/assets/templates/main.tex → ./main.tex
# 复制阅读笔记模板：<PDF_MAKER>/assets/examples/chapter_init_notes_template.md
```

### 2. 写一章（完整 SOP）

在**书稿项目根目录 `<PROJECT>`** 下执行脚本即可，无需把脚本/模板复制进项目——`fix.py` 会从自身安装目录向上定位 `assets/templates/_tmp.tex` 作为单章 preamble 唯一真源。

```bash
cd <PROJECT>
# 1) 强制阅读素材（三阶段）
python <PDF_MAKER>/scripts/reader.py index  "<素材 report.md>"
python <PDF_MAKER>/scripts/reader.py chunk  "<素材 report.md>" 0
python <PDF_MAKER>/scripts/reader.py verify "<素材 report.md>"

# 2) 撰写 第1章/第1章.tex

# 3) 预处理
python <PDF_MAKER>/scripts/fix.py 1
# 4) 结构校验
python <PDF_MAKER>/scripts/check.py 1 && python <PDF_MAKER>/scripts/check_balance.py 1
# 5) 联网验活（强制；exit 0 继续 / 1 修链接 / 2 离线重跑）
python <PDF_MAKER>/scripts/verify_urls.py 1
# 6) 编译（必须 cd 进章目录）
cd 第1章 && xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex && cd ..
# 7) 日志体检
python <PDF_MAKER>/scripts/check_overflow.py 第1章/_tmp.log
# 8) 清理落盘
python <PDF_MAKER>/scripts/cleanup.py 1
# 9) 更新素材追踪
python <PDF_MAKER>/scripts/track_materials.py update <PROJECT> 第1章 <size> <lines> <chunks>
```

`check_overflow.py` 若不传日志路径，会在当前目录自动寻找 `_tmp.log` / `main.log`。

### 3. 整书合并

所有章节 OK 后，在 `<PROJECT>` 根目录执行：

```bash
python <PDF_MAKER>/scripts/fix_labels.py .
xelatex -halt-on-error -interaction=nonstopmode main.tex
xelatex -halt-on-error -interaction=nonstopmode main.tex
python <PDF_MAKER>/scripts/check_overflow.py main.log
pdfinfo main.pdf          # 校验 Title / Author 元数据
```

## 项目结构

```
pdf-maker/
├── SKILL.md                       # 精简 SOP（触发 + 红线 + 脚本表），详细见 references/
├── README.md                      # 本文件
├── LICENSE                        # MIT
├── CHANGELOG.md                   # 版本里程碑
├── CONTRIBUTING.md                # 贡献指南
├── .gitignore
├── assets/
│   ├── templates/
│   │   ├── main.tex               #   整书主控模板
│   │   └── _tmp.tex               #   单章编译 preamble 唯一真源
│   └── examples/
│       └── chapter_init_notes_template.md
├── references/
│   └── SOP.md                     # 完整 SOP / 命令参考 / 模板说明 / URL 写法 / 踩坑速查
└── scripts/                       # 一组小而专的 Python 工具（stdlib-only）
    ├── common.py                  #   共享工具（路径定位 / 编码 / 文本统计）
    ├── fix.py                     #   单章预处理
    ├── verify_urls.py             #   【强制】联网验活
    ├── check.py                   #   内容结构统计
    ├── check_balance.py           #   结构 / 引用均衡
    ├── check_overflow.py          #   编译日志体检（硬卡口）
    ├── cleanup.py                 #   成品落盘 + 临时清理
    ├── fix_labels.py              #   跨章重复 label 去重
    ├── reader.py                  #   素材强制阅读三阶段校验
    └── track_materials.py         #   章节 ↔ 素材阅读状态追踪
```

## 脚本职责一览

| 脚本 | 一句话 |
|------|--------|
| `fix.py` | 把 `第N章.tex` 处理成 xelatex 真能编译的 `chN.tex` + `_tmp.tex` |
| `verify_urls.py` | **【强制】** 联网验活：逐 URL 检测可达性，exit 0/1/2 |
| `check.py` | 输出字数 / 层级 / 元素计数 |
| `check_balance.py` | 结构 / 引用均衡自查（软告警） |
| `check_overflow.py` | 解析编译日志，拦截溢出 / 断链 / 缺失字符 |
| `cleanup.py` | 复制 `_tmp.pdf → 第N章.pdf` + 归档中间产物（移动而非删除） |
| `fix_labels.py` | 跨章重复 `\label` 按章重命名 |
| `reader.py` | 素材强制阅读三阶段校验（index / chunk / verify / toc） |
| `track_materials.py` | 章节 ↔ 素材阅读状态追踪 |
| `common.py` | 共享工具模块（不被单独运行） |

完整命令、参数与踩坑见 [`references/SOP.md`](references/SOP.md)。

## 关键概念

- **双模式**：单章独立编译（每章 `\chapter` → 验证 → 下一章）与整书合并（`main.tex` `\input` 各章 → `main.pdf`）二选一，混用即 bug。
- **三阶段阅读**：动笔前 `reader.py` 跑 `index → chunk → verify`，确保素材被完整通读。
- **日志体检**：编译后必须跑 `check_overflow.py`，把阻断级信号拦在交付前。

## 贡献

欢迎提交 Issue 与 Pull Request。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。新增踩坑请同步更新 `references/SOP.md` 的踩坑速查；脚本改动保持单一职责、显式 `import`。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
