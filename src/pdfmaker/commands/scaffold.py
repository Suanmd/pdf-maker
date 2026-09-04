# -*- coding: utf-8 -*-
r"""scaffold —— 书稿骨架生成器（整书初始化 + 单章从素材生成）。

本命令有两档能力：

1. **整书初始化**
   ``python -m pdfmaker scaffold <dir> [--chapters N] [--flat]``
   在 ``<dir>`` 落地 ``main.tex`` / ``_tmp.tex`` 与章节占位。两种布局：
   标准布局 ``第N章/第N章.tex``（多章书籍）；扁平布局 ``--flat`` 时
   ``第N章.tex`` 直接在项目根（单章写作推荐，成品 PDF 落一级目录）。

2. **单章从素材生成**
   ``python -m pdfmaker scaffold chapter N [--material <素材.md>] [--root <项目根>] [--flat] [--force]``
   根据素材（可选）解析出**章标题 / 二级节结构 / 全部 URL**，生成一份「合规富骨架」：

   - 头部注释写死本工具强制约定（引用键前缀 ``cN``、标签前缀 ``cN``、禁止跨章
     ``\ref``、字形风险字符须置于数学模式、三线表 + ``codeblock`` 强制规范）；
   - 内嵌**可直接编译**的合规示例：booktabs 三线表（表题在上）、TikZ 矢量图
     （图题在下）、``codeblock`` 伪代码（全 ASCII 注释）——作者复制即用，从根上
     消灭「凭记忆写、退化成 ``\hline`` 网格表 + 裸 ``verbatim``」的样式漂移；
   - 按素材二级标题预生成 ``\section``，作者不必重新规划结构；
   - 若素材含 URL，预填 ``\bibitem{cNrK}\href{URL}{...}`` 供按需取用（引用是论证
     需要而非配额，无需全部引用，删净未用条目即可过孤儿门禁）；素材无 URL 则
     不生成 thebibliography（零引用章是合法形态，不产生任何凑数压力）。

   该骨架经 `chapter` 标准 SOP 在章文件缺失且提供 `--material` 时**自动调用**
   （无需 `--scaffold` 显式开关），使整条写作流水线自我引导、不再依赖「从空白文件手写」。

设计原则：生成的文件一律**不覆盖**已有成果（``_write_if_absent``）；单章模式仅在
目标章文件缺失时落地（除非 ``--force``）。

退出码
------
0 成功（或跳过已存在）；2 参数错误 / 目标目录非空冲突；1 模板缺失等异常。
"""

import argparse
import re
import sys
from datetime import date
from pathlib import Path

from pdfmaker.core.paths import (
    find_main_template,
    find_tmp_template,
    looks_like_project_root,
    resolve_material,
    resolve_shared_preamble,
    setup_utf8,
)

setup_utf8()

# 素材 URL 提取正则（与 reader 保持一致，避免双源漂移）。
_URL_RE = re.compile(r"https?://[^\s)\]\"<>]+")
# Markdown 标题：任意层级（MULTILINE 使 ^/$ 逐行锚定）。
_MD_HEADING_RE = re.compile(r"^\s{0,3}(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)
# 二级标题（映射为 \section）。
_MD_H2_RE = re.compile(r"^\s{0,3}##\s+(.+?)\s*#*\s*$", re.MULTILINE)

# 章节编号前缀：ctexrep 的 \chapter / \section 会自动生成「第 X 章」/「X.Y」编号；
# 素材标题里手写的「第N章」前缀必须剥离，否则渲染成重复编号。
_CHAPTER_PREFIX_RE = re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千]+\s*章\s*")
# 手写小节编号前缀：素材里常见的「1. 」「2.3 」「3.1.2、」等手写编号会与 \section
# 的自动编号叠加成「2.3 2.3 ……」重复编号（check 的 scan_redundant_heading_number
# 会拦），生成骨架时直接剥离，从源头避免重复返工。
# 要求编号后必须跟空白（防误伤「2024 年度报告」「v9.9 说明」这类无点号标题）。
_SECTION_NUM_PREFIX_RE = re.compile(r"^\s*\d{1,2}(?:\.\d{1,2}){0,3}\s*[.、．]?\s+")


def _strip_chapter_prefix(title: str) -> str:
    """剥离标题前导的「第N章 / 第 N 章」，避免与 ctexrep 自动编号重复。"""
    return _CHAPTER_PREFIX_RE.sub("", title, count=1).strip()


def _strip_section_number(title: str) -> str:
    """剥离标题前导的手写小节编号（「1. 」「2.3 」「3.1.2、」），避免与自动编号重复。"""
    return _SECTION_NUM_PREFIX_RE.sub("", title, count=1).strip()


# ---- 素材解析 ----

def parse_material(material_path: str) -> tuple[str, list[str], list[str]]:
    """从素材 .md 解析 (标题, 二级节列表, URL 列表)。

    标题取首个 Markdown 标题；二级节取所有 ``## `` 标题（若与标题文本相同则跳过，
    避免把「第N章」既当标题又当节）；URL 用 ``_URL_RE`` 去重保序。无素材时返回
    ("", [], []) 由调用方回退默认。
    """
    p = Path(material_path)
    if not p.exists():
        print(f"[scaffold] 素材不存在，按空白骨架处理：{material_path}")
        return "", [], []
    text = p.read_text(encoding="utf-8")
    title = ""
    for m in _MD_HEADING_RE.finditer(text):
        title = _strip_section_number(m.group(2).strip())
        break
    sections: list[str] = []
    for m in _MD_H2_RE.finditer(text):
        s = _strip_section_number(m.group(1).strip())
        if s and s != title and s not in sections:
            sections.append(s)
    urls = []
    for u in _URL_RE.findall(text):
        if u not in urls:
            urls.append(u)
    return title, sections, urls


# ---- 合规富骨架构建 ----

def _compliance_examples(n: int) -> str:
    """内嵌可直接编译的合规示例：三线表（表题在上）+ TikZ 图（图题在下）+ codeblock。

    这些示例与规范验证过的写法逐字一致，作者复制到正文任意位置即用，从根上
    消灭样式退化。整节标题醒目提示「撰写后删除」。
    """
    return f"""\\section{{排版合规示例（撰写正文后务必删除本节）}}
\\label{{sec:c{n}:examples}}

以下示例与全书强制规范逐字一致，可整段复制到正文章节。**规范要求：表格必须用
三线表（booktabs 规则线，禁用裸横线命令 hline 与列格式竖线 |）；伪代码/代码块必须用共享
preamble 的 codeblock 环境（禁用裸 verbatim/lstlisting）；表题在上、图题在下。**

% ---- 三线表示例（表题在上）----
\\begin{{table}}[htbp]
\\centering
\\caption{{示例三线表：方案 A 与方案 B 的对比（表题在上）。}}
\\label{{tab:c{n}:example}}
\\begin{{tabularx}}{{\\textwidth}}{{l X X}}
\\toprule
维度 & 方案 A & 方案 B \\\\
\\midrule
特征甲 & 表现甲 & 表现乙 \\\\
特征乙 & 表现丙 & 表现丁 \\\\
\\bottomrule
\\end{{tabularx}}
\\end{{table}}

% ---- TikZ 矢量图示例（图题在下）----
\\begin{{figure}}[htbp]
\\centering
\\begin{{tikzpicture}}[
  box/.style={{draw, rounded corners, minimum width=2.6cm, minimum height=1.0cm, align=center}},
  arr/.style={{->, >=stealth, thick}}
]
  \\node[box, align=center] (a) {{输入\\\\X}};
  \\node[box, right=0.9cm of a, align=center] (b) {{处理\\\\Y}};
  \\node[box, right=0.9cm of b, align=center] (c) {{输出\\\\Z}};
  \\draw[arr] (a) -- (b);
  \\draw[arr] (b) -- (c);
\\end{{tikzpicture}}
\\caption{{示例流程图：输入经处理得到输出（图题在下）。节点内换行须声明 align=center。}}
\\label{{fig:c{n}:example}}
\\end{{figure}}

% ---- codeblock 伪代码示例（注释须纯 ASCII，等宽字体不含中文/希腊字母）----
\\begin{{codeblock}}
def example_pipeline(x, params):
    # normalize input, then apply physics-informed constraint
    y = normalize(x)
    y = apply_constraint(y, params)   # e.g. a physics-informed constraint
    return y                          # physically consistent output
\\end{{codeblock}}
"""


def build_chapter_skeleton(n: int, *, title: str = "", sections: list[str] | None = None,
                           urls: list[str] | None = None) -> str:
    """构建单章合规富骨架的 .tex 文本（不直接写盘）。

    参数
    ----
    n : 章号（数字）。
    title : 章标题；为空回退 ``未命名章标题``（不自带「第N章」，避免与 ctexrep 自动前缀重复）。
    sections : 二级节名列表；为空/None 回退默认两节。
    urls : 素材中提取的 URL 列表；用于预填 \\bibitem + \\href。
    """
    title = title or "未命名章标题"
    title = _strip_chapter_prefix(title) or "未命名章标题"
    secs = [s for s in (sections or []) if s]
    if not secs:
        secs = ["背景与动机", "方法或结论"]
    secs = secs[:8]  # 防止素材结构过长撑爆骨架
    urls = urls or []

    # 文献预填：cNrK + \href；并在引言处给引用示例，保证 bibitem==cite 开箱一致。
    bib_items = []
    cite_line = ""
    if urls:
        for i, u in enumerate(urls, start=1):
            key = f"c{n}r{i}"
            bib_items.append(
                f"\\bibitem{{{key}}} 待补文献条目（作者. 标题. \\emph{{来源}}, 年份）. "
                f"\\href{{{u}}}{{{u}}}"
            )
        keys = ", ".join(f"\\cite{{c{n}r{i}}}" for i in range(1, len(urls) + 1))
        cite_line = (
            f"\n下方已按素材 URL 预填文献条目（{keys}）——按需引用即可，无需全部引用；"
            f"删除正文中未使用的文献条目，否则会触发孤儿文献门禁。\n"
        )
        bib_tex = "\n".join(bib_items)
        bib_block = (
            "\\begin{thebibliography}{99}\n"
            f"{bib_tex}\n"
            "\\end{thebibliography}"
        )
    else:
        # 素材无 URL → 零引用章：不生成 thebibliography（避免编译出空的「参考文献」
        # 标题节），头部注释说明；后续若要加文献，作者自行补环境即可。
        bib_block = (
            "% 本章素材未提供 URL，无外部参考文献（零引用章是合法形态）。\n"
            "% 如需添加文献，可在此补 thebibliography 环境。"
        )

    sections_tex = _build_sections(n, secs, intro_lead=cite_line)

    return f"""% 第 {n} 章 / 第{n}章.tex
% 本文件由 pdfmaker scaffold 生成（合规富骨架）。
% 强制约定：引用键前缀 c{n}rN；标签前缀 c{n}；禁止跨章 \\ref（交叉章引用用硬编码纯文本「第~N 章」）。
% 字形风险（≥≤≈≠∼①-⑩ 及希腊字母/±/℃）一律置于数学模式 $\\ge$ 等，正文不得裸用；codeblock 内注释须纯 ASCII。
% 表格须三线表（booktabs，表题在上）；伪代码须 codeblock 环境（图题在下）。

\\chapter{{{title}}}
\\label{{cha:c{n}}}

{sections_tex}

{_compliance_examples(n)}
\\section{{本章小结}}
\\label{{sec:c{n}:summary}}

归纳本章要点，并点明与后续章节的衔接（跨章互指用纯文本「第~N 章」，章号勿越界）。

{bib_block}
"""


def _build_sections(n: int, secs: list[str], *, intro_lead: str = "") -> str:
    """构建各 \\section 正文（含首节引言合并，避免引言段与首节重复）。

    - 首节标签固定 ``sec:c{n}:intro``，引言引导语并入首节正文（不再单独浮空成段，
      避免与素材首个 ## 同名为「引言」时形成「双重引言」）；
    - 其余节标签 ``sec:c{n}:2..N``，互不相同、无重复。
    """
    # 引言引导语不写死任何具体章号（如「第~6--12 章」）：盲写章号会在小书稿上
    # 触发 xref 的「文字引用越界」阻断，让开箱骨架反而过不了自己的门禁。
    lead = (
        f"这里是第 {n} 章引言：说明本章要解决的问题、与前后章"
        f"的关系、以及核心结论。{intro_lead}"
    )
    parts: list[str] = []
    for i, s in enumerate(secs):
        label = "intro" if i == 0 else str(i + 1)
        body = (
            f"在此展开「{s}」的分析（建议 4000–6000 字/章，本节不少于 300 可见字符）。"
        )
        if i == 0:
            body = lead + "\n\n" + body
        parts.append(f"\\section{{{s}}}\n\\label{{sec:c{n}:{label}}}\n\n{body}")
    return "\n\n".join(parts)


# ---- 占位骨架判定 ----

def is_untouched_placeholder(text: str) -> bool:
    """判断章节文件是否仍是「未被编辑过的 scaffold 占位骨架」。

    判定依据两个骨架独有标记：头部生成注释 + ``\\chapter{未命名章标题}``
    （整书初始化 scaffold 在无素材时生成的占位标题）。作者一旦动笔
    （改标题/删注释），即视为已有成果，回到「绝不覆盖」原则。

    用途：``chapter N --material`` 在整书初始化后常遇到「占位骨架挡路」——
    素材驱动的富骨架（按素材预生成节结构与文献）被「文件已存在」挡住，
    作者只能全手写。占位骨架不含任何作者劳动，允许被素材骨架再生。
    """
    return ("本文件由 pdfmaker scaffold 生成" in text
            and "\\chapter{未命名章标题}" in text)


# ---- 写盘（幂等，不覆盖） ----

def _write_if_absent(path: Path, content: str) -> bool:
    """写出文件；若已存在则跳过（不覆盖用户已有成果）。返回是否实际写入。"""
    if path.exists():
        print(f"[scaffold] 跳过已存在（不覆盖）: {path}")
        return False
    path.write_text(content, encoding="utf-8")
    return True


def write_chapter(n: int, *, material: str | None = None,
                  root: str | None = None, force: bool = False,
                  flat: bool = False) -> bool:
    """生成单章骨架并写盘。返回是否实际写入。

    - 目标：标准布局 ``<root>/第N章/第N章.tex``；扁平布局（``flat=True``，推荐
      单章写作使用）``<root>/第N章.tex``，成品 PDF 随 cleanup 落在一级目录；
    - root 默认当前目录；
    - 解析素材（标题/二级节/URL）预填骨架；不传素材则空白默认骨架；
    - 已存在且非 ``--force`` 时跳过（不覆盖）。
    """
    root_path = Path(root) if root else Path.cwd()
    chdir = root_path if flat else root_path / f"第{n}章"
    target = chdir / f"第{n}章.tex"
    if target.exists() and not force:
        print(f"[scaffold] 跳过已存在（不覆盖）: {target}（加 --force 可覆盖）")
        return False
    title, sections, urls = ("", [], [])
    if material:
        title, sections, urls = parse_material(material)
    content = build_chapter_skeleton(n, title=title, sections=sections, urls=urls)
    chdir.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    print(f"[scaffold] 已生成单章骨架: {target}")
    print(f"          章标题: {_strip_chapter_prefix(title) or '未命名章标题'}（「第N章」前缀由 ctexrep 自动生成，已剥离），"
          f"预生成节: {len(sections) or 2} 个，预填文献: {len(urls)} 条")
    return True


# ---- 整书初始化 ----

def _fill_main_template(text: str, *, title: str, subtitle: str, epigraph: str,
                        epigraph_closing: str, author: str, date_str: str,
                        chapters_list: str) -> str:
    """把 main.tex 模板里的全部 {{XXX}} 占位符替换为实际值。"""
    pdf_title = title.replace("\\\\", " ").replace("\\", " ").strip()
    mapping = {
        "{{TITLE}}": title,
        "{{PDF_TITLE}}": pdf_title,
        "{{SUBTITLE}}": subtitle,
        "{{EPIGRAPH}}": epigraph,
        "{{EPIGRAPH_CLOSING}}": epigraph_closing,
        "{{AUTHOR}}": author,
        "{{DATE}}": date_str,
        "{{CHAPTERS_LIST}}": chapters_list,
    }
    for key, val in mapping.items():
        text = text.replace(key, val)
    return text


def _starter_chapter(n: int) -> str:
    """整书初始化用的单章占位（合规富骨架，从根上消除样式漂移）。"""
    return build_chapter_skeleton(n)


def _starter_appendix(label: str) -> str:
    """整书初始化用的附录占位。"""
    return (
        f"% 附录{label}/附录{label}.tex\n"
        f"% 本文件由 pdfmaker scaffold 生成。\n"
        f"\\chapter{{附录{label} 标题}}\n\n"
        f"这里是附录{label}的正文。\n"
    )


def _cmd_init(argv: list[str]) -> int:
    """整书初始化：``scaffold <dir> [--chapters N] [--title ...] ...``。"""
    parser = argparse.ArgumentParser(
        prog="pdfmaker scaffold",
        description="初始化一本书稿项目骨架（main.tex + _tmp.tex + 章节占位）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker scaffold my-book                # 生成 my-book/（默认 1 章）\n"
            "  python -m pdfmaker scaffold . --chapters 19       # 在当前目录生成 19 章骨架\n"
            "  python -m pdfmaker scaffold book --title \"我的书\" --author 张三\n"
        ),
    )
    parser.add_argument("directory", nargs="?", default=".",
                        help="目标目录，默认当前目录")
    parser.add_argument("--title", default=None, help="书名（扉页 + PDF 元数据），默认用目录名")
    parser.add_argument("--subtitle", default="", help="副标题，默认空")
    parser.add_argument("--author", default="佚名", help="作者，默认「佚名」")
    parser.add_argument("--date", default=None, help="成稿日期，默认今天")
    parser.add_argument("--chapters", type=int, default=1,
                        help="生成的正文章节数（第1章…第N章），默认 1")
    parser.add_argument("--appendices", type=int, default=0,
                        help="生成的附录数（附录A…），默认 0")
    parser.add_argument("--flat", action="store_true",
                        help="扁平布局：章节写为 第N章.tex 直接落在项目根（不建 第N章/ 目录），"
                             "成品 PDF 随 cleanup 落在一级目录。推荐单章写作使用")
    parser.add_argument("--force", action="store_true",
                        help="允许在「非空目标目录」中落地骨架；已存在的文件不会被覆盖（跳过）")
    args = parser.parse_args(argv)

    target = Path(args.directory)
    if target.exists() and any(target.iterdir()) and not args.force:
        print(f"[scaffold] 目标目录非空，拒绝覆盖：{target}")
        print("          如需在现有目录中补齐缺失骨架（不覆盖已有文件），加 --force。")
        return 2

    title = args.title or (target.resolve().name if args.directory != "." else "未命名书稿")
    date_str = args.date or date.today().strftime("%Y年%m月%d日")

    chapters_list_lines = []
    for n in range(1, max(args.chapters, 0) + 1):
        # 扁平布局：\input{第N章}；标准布局：\input{第N章/第N章}
        chapters_list_lines.append(
            f"\\input{{第{n}章}}" if args.flat else f"\\input{{第{n}章/第{n}章}}"
        )
    for i in range(max(args.appendices, 0)):
        label = chr(ord("A") + i)
        chapters_list_lines.append(
            f"\\input{{附录{label}}}" if args.flat else f"\\input{{附录{label}/附录{label}}}"
        )
    chapters_list = "\n".join(chapters_list_lines)

    try:
        main_tpl = find_main_template().read_text(encoding="utf-8")
        tmp_tpl = find_tmp_template().read_text(encoding="utf-8")
    except SystemExit as e:
        print(f"[scaffold] {e}")
        return 1

    main_tpl = resolve_shared_preamble(main_tpl)
    tmp_tpl = resolve_shared_preamble(tmp_tpl)

    target.mkdir(parents=True, exist_ok=True)
    _write_if_absent(
        target / "main.tex",
        _fill_main_template(
            main_tpl, title=title, subtitle=args.subtitle, epigraph="",
            epigraph_closing="", author=args.author, date_str=date_str,
            chapters_list=chapters_list,
        ),
    )
    _write_if_absent(target / "_tmp.tex", tmp_tpl)

    for n in range(1, max(args.chapters, 0) + 1):
        if args.flat:
            _write_if_absent(target / f"第{n}章.tex", _starter_chapter(n))
        else:
            d = target / f"第{n}章"
            d.mkdir(parents=True, exist_ok=True)
            _write_if_absent(d / f"第{n}章.tex", _starter_chapter(n))
    for i in range(max(args.appendices, 0)):
        label = chr(ord("A") + i)
        if args.flat:
            _write_if_absent(target / f"附录{label}.tex", _starter_appendix(label))
        else:
            d = target / f"附录{label}"
            d.mkdir(parents=True, exist_ok=True)
            _write_if_absent(d / f"附录{label}.tex", _starter_appendix(label))

    print(f"[scaffold] 已在 {target} 生成书稿骨架：")
    print(f"  main.tex（书名：{title} / 作者：{args.author}）")
    print("  _tmp.tex")
    layout = "扁平布局（第N章.tex 在项目根）" if args.flat else "标准布局（第N章/第N章.tex）"
    print(f"  正文 {max(args.chapters, 0)} 章（合规富骨架，{layout}）、附录 {max(args.appendices, 0)} 个")
    if args.force:
        print("  （--force：已存在文件已跳过，未覆盖）")
    print(f"\n下一步：编辑各章 .tex 后，在 {target} 内运行 `python -m pdfmaker build .`")
    if args.title is None:
        print(f"提示：书名默认取自目录名「{title}」、作者默认「{args.author}」；"
              f"如需修改请编辑 main.tex 扉页与 \\hypersetup 元数据，"
              f"或重新生成时加 --title / --author。")
    return 0


def _cmd_chapter(argv: list[str]) -> int:
    """单章从素材生成：``scaffold chapter N [--material <md>] [--root <dir>] [--flat] [--force]``。"""
    parser = argparse.ArgumentParser(
        prog="pdfmaker scaffold chapter",
        description="从素材（可选）生成单章合规富骨架（第N章/第N章.tex；--flat 为 第N章.tex）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker scaffold chapter 14 --material 第14章/素材-第14章.md\n"
            "  python -m pdfmaker scaffold chapter 14 --root . --force\n"
            "  python -m pdfmaker scaffold chapter 1 --flat   # 扁平布局（单章写作推荐）\n"
        ),
    )
    parser.add_argument("n", type=int, help="章号（数字 N）")
    parser.add_argument("--material", default=None, help="素材 .md 路径；传入则预填标题/节/文献")
    parser.add_argument("--root", default=None, help="项目根目录（默认当前目录）")
    parser.add_argument("--flat", action="store_true",
                        help="扁平布局：写为 <root>/第N章.tex（不建 第N章/ 目录），推荐单章写作使用")
    parser.add_argument("--force", action="store_true",
                        help="覆盖已存在的章文件（默认跳过已存在）")
    args = parser.parse_args(argv)
    # 素材路径解析：多章约定素材在章节文件夹（第N章/素材-第N章.md），裸文件名自动解析
    material = args.material
    if material:
        base = Path(args.root) if args.root else None
        material = str(resolve_material(material, str(args.n), base))
    # CWD 守卫：在「不像书稿项目根」的目录创建章骨架前拒绝（防止游离目录），
    # --force 显式豁免（如全新扁平项目从零起稿）。
    root_path = Path(args.root) if args.root else Path.cwd()
    if not args.force and not looks_like_project_root(root_path):
        target_exists = (root_path / f"第{args.n}章.tex").exists() or \
            (root_path / f"第{args.n}章" / f"第{args.n}章.tex").exists()
        if not target_exists:
            print(f"[scaffold] 拒绝在 {root_path} 创建章骨架：该目录不像书稿项目根"
                  f"（无 main.tex / materials.json / 既有章节结构）。\n"
                  f"          请 cd 到书稿项目根后重跑；若确要在当前目录新建，加 --force。")
            return 2
    write_chapter(args.n, material=material, root=args.root, force=args.force,
                  flat=args.flat)
    return 0


def main(argv: list[str] | None = None) -> int:
    """手动分发：``scaffold chapter N ...`` 走单章模式；其余走整书初始化（向后兼容）。"""
    argv = argv or []
    if argv and argv[0] == "chapter":
        return _cmd_chapter(argv[1:])
    return _cmd_init(argv)


if __name__ == "__main__":
    sys.exit(main())
