# pdf-maker

> 中文 LaTeX 报告工程化 skill。基于 `xelatex + ctexrep + xeCJK`，把零散章节稳定产出为排版合规的中文 PDF。

[![LaTeX](https://img.shields.io/badge/xelatex-TeXLive-blue)]()
[![Python](https://img.shields.io/badge/python-3.8%2B-yellow)]()

## 这是什么

`pdf-maker` 是一个用于中文 LaTeX 报告工程化的 skill，聚焦于解决最常见的几类痛点：

- **单章独立编译 → 整书合并** 双模式工作流
- **源码预处理**（`fix.py`）把多类常见 LaTeX 坑批量修在编译之前
- **素材强制阅读校验**（`reader.py` 三阶段）杜绝「读一半就写」
- **编译日志体检**（`check_overflow.py`）拦截溢出 / 断链 / 缺失字符等硬错误
- **排版约定前置**：表格（全宽三线表）、图（TikZ 节点规范）、URL（中文超链接）在写作阶段即规定清楚
- **分类踩坑速查** + **完整反例清单** + **参考文献 / 页眉页脚样式补丁**

适用：中文技术报告、调研报告、白皮书、论文（每章 5–15 页，≤ 30 章规模）。

## 目录结构

```
pdf-maker/
├── SKILL.md                # 完整 SOP（强制规范 / 双模式 / 阅读 / 编译 / 脚本 / 约定 / 踩坑）
├── README.md               # 本文件
├── LICENSE                 # MIT
├── CONTRIBUTING.md         # 贡献指南
├── CHANGELOG.md            # 版本里程碑
├── assets/
│   ├── templates/          # LaTeX 模板
│   │   ├── main.tex        #   整书主控
│   │   ├── _tmp.tex        #   单章 preamble（由 fix.py 复用）
│   │   └── url-href.tex    #   中文 URL 写法参考
│   └── examples/           # 工作流辅助模板
│       └── chapter_init_notes_template.md
└── scripts/                # 一组小而专的 Python 工具
    ├── fix.py              # 单章预处理（URL / 图片宽度 / 生成编译入口）
    ├── verify_urls.py      # 章节 URL 真实可达校验
    ├── find_urls.py        # 候选权威源兜底探测
    ├── check.py            # 内容结构统计
    ├── check_balance.py    # 结构 / 引用均衡
    ├── check_overflow.py   # 编译日志体检（硬卡口）
    ├── cleanup.py          # 成品落盘 + 临时清理
    ├── fix_labels.py       # 跨章重复 label 去重
    ├── reader.py           # 素材强制阅读三阶段校验
    └── track_materials.py  # 章节↔素材阅读状态追踪
```

## 快速开始

### 1. 环境

需要：

- **TeX Live 2022 及以上版本**（含 `xelatex` + `ctexrep` + `xeCJK`）
- **Python 3.8+**
- （可选）`pip install pypdf` 用于 PDF 页数校验

### 2. 安装 skill

将本目录放到 skill 加载路径下即可（具体位置取决于你使用的宿主环境）。

### 3. 新建项目

```bash
mkdir my-report
cd my-report
mkdir figures 第1章 第2章 第3章
# 复制 pdf-maker/assets/templates/main.tex 到 ./main.tex
# 复制 pdf-maker/assets/examples/chapter_init_notes_template.md 作为笔记模板
```

### 4. 写一章

按 [SKILL.md § 6](SKILL.md#6-单章编译-sop) 走完整 SOP：

```bash
cd 第1章
# 从 pdf-maker/scripts/ 复制 fix.py / verify_urls.py / check.py / check_balance.py / cleanup.py
python fix.py 1
python verify_urls.py 1
python check.py 1 && python check_balance.py 1
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
xelatex -halt-on-error -interaction=nonstopmode _tmp.tex
python cleanup.py 1
```

### 5. 整书合并

所有章节 OK 后，按 [SKILL.md § 7](SKILL.md#7-整书合并-sop)：

```bash
cd ..
xelatex -halt-on-error -interaction=nonstopmode main.tex
xelatex -halt-on-error -interaction=nonstopmode main.tex
```

## 脚本职责一览

| 脚本 | 一句话 |
|------|--------|
| `fix.py` | 把 `第N章.tex` 处理成 xelatex 真能编译的 `chN.tex` + `_tmp.tex` |
| `verify_urls.py` | 批量测章节内所有 URL 的 HTTP 200 |
| `find_urls.py` | 候选权威源兜底（verify 失败时用） |
| `check.py` | 输出字数 / 层级 / 元素计数 |
| `check_balance.py` | 结构 / 引用均衡自查 |
| `check_overflow.py` | 解析编译日志，拦截溢出 / 断链 / 缺失字符 |
| `cleanup.py` | 复制 `_tmp.pdf → 第N章.pdf` + 删中间产物（顺序敏感） |
| `fix_labels.py` | 跨章重复 `\label` 按章重命名 |
| `reader.py` | 素材强制阅读三阶段校验（index / chunk / verify / toc） |
| `track_materials.py` | 章节↔素材阅读状态追踪 + 引用质量审计 |

详见 [SKILL.md § 8](SKILL.md#8-脚本清单)。

## 关键概念

### 双模式

- **单章独立编译**：每章用 `\chapter`，走完整闭环 → 验证 → 下一章
- **整书合并**：所有章节用 `\chapter`，主控 `\input` 装入 → 出 `main.pdf`

混用 = bug。详见 [SKILL.md § 3](SKILL.md#3-双模式工作流)。

### 三阶段阅读

每章动笔前用 `reader.py` 跑 `index → chunk → verify`，确保素材被完整通读，而非只读片段。详见 [SKILL.md § 5](SKILL.md#5-素材阅读-sop)。

### 日志体检

编译后必须跑 `check_overflow.py <log>`，把 `Overfull`、`Missing character`、`multiply-defined`、`undefined references`、`Fatal` 等阻断级信号拦在交付前。详见 [SKILL.md § 8](SKILL.md#8-脚本清单)。

## 与其他组件的边界

- **协同**：素材采集类工具提供素材 → 本 skill 整章节 → 后处理 PDF 的工具（如需）。
- **不重复**：SVG/HTML 图表、编辑既有 PDF、创建 skill 自身。

## 贡献

欢迎提交 Issue 与 Pull Request。新增踩坑请同步更新 [SKILL.md § 16](SKILL.md#16-踩坑分类速查)；脚本改动保持单一职责。详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可

MIT —— 见 [LICENSE](LICENSE)。
