# -*- coding: utf-8 -*-
"""fix.py - 单章 TeX 预处理。

用途
----
把作者手写的章节源文件（默认 `第N章.tex` 或 `附录X/附录X.tex`）转换为可直接交给
xelatex 编译的成品，并生成单章独立编译所需的 `_tmp.tex`（含完整 preamble）。

它会批量修复几类常见、且“编译期才暴露”的中文 LaTeX 坑，避免临时手工改源码。

检查/处理项
-----------
1. URL 规范化：把 ``\\url{...}`` 改写为 ``\\href{raw-url}{display-text}``，
   并对显示文本里的 LaTeX 特殊字符做转义（见 § URL 约定）。
2. 图片宽度上限：给每个 ``tikzpicture`` 套 ``adjustbox{max width=\\textwidth}``，
   只缩放超宽图，正常图保持原样。
3. 写入英文名中间文件 ``chN.tex``（避免中文文件名在部分工具链下乱码）。
4. 生成 ``_tmp.tex``：注入与整书模板同源的 preamble 补丁（参考文献降级、
   中文 URL 支持、代码块环境、防溢出等）。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「写正文之后、xelatex 之前」调用，每章必跑（不可替代）。
用法：
    python fix.py [CH_NUM]          # 默认处理 ./第1章.tex
    python fix.py 3                 # 处理 ./第3章.tex
    python fix.py 附录A             # 处理 ./附录A/附录A.tex

退出码：0 成功；源文件缺失时非零退出。
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# 强制 UTF-8 输出（Windows 控制台 GBK 回退 bug 修复）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

HERE = Path(__file__).parent
ARG = sys.argv[1] if len(sys.argv) > 1 else "1"

if ARG.startswith("附录"):
    CH_NUM = ARG
    SRC = HERE / ARG / f"{ARG}.tex"
    DST = HERE / ARG / f"{ARG}_ch.tex"
    TMP = HERE / ARG / "_tmp.tex"
else:
    CH_NUM = ARG
    SRC = HERE / f"第{CH_NUM}章.tex"
    DST = HERE / f"ch{CH_NUM}.tex"
    TMP = HERE / "_tmp.tex"

if not SRC.exists():
    raise SystemExit(f"[fix.py] 找不到源文件: {SRC}")


def url_to_href(text: str) -> str:
    """将 \\url{...} 改写为 \\href{raw}{display-escaped}。

    - URL 保持原始（不预 percent-encode，交由 hyperref 处理）。
    - 显示文本里的 LaTeX 特殊字符必须转义，否则会进入 math mode 报错。
    """
    def repl(m):
        url = m.group(1)
        try:
            decoded = unquote(url)
        except Exception:
            decoded = url
        display = (
            decoded.replace("\\", r"\textbackslash{}")
            .replace("_", r"\_")
            .replace("&", r"\&")
            .replace("$", r"\$")
            .replace("#", r"\#")
            .replace("%", r"\%")
        )
        return r"\href{" + url + "}{" + display + "}"

    return re.sub(r"\\url\{([^{}]+)\}", repl, text)


def wrap_tikz(text: str) -> str:
    """给每个 tikzpicture 套 adjustbox 宽度上限。

    只对超宽图缩放，正常图不动；这是“图片不超出版心”的结构性保证。
    """
    out = []
    i = 0
    BT = r"\begin{tikzpicture}"
    ET = r"\end{tikzpicture}"
    while True:
        b = text.find(BT, i)
        if b == -1:
            out.append(text[i:])
            break
        e = text.find(ET, b)
        if e == -1:
            out.append(text[i:])
            break
        e_end = e + len(ET)
        out.append(text[i:b])
        out.append(r"\begin{adjustbox}{max width=\textwidth}" + "\n")
        out.append(text[b:e_end])
        out.append(r"\end{adjustbox}" + "\n")
        i = e_end
    return "".join(out)


# ---- 1. URL 规范化 ----
text = url_to_href(SRC.read_text(encoding="utf-8"))

# ---- 2. 图片宽度上限 ----
text = wrap_tikz(text)

# ---- 3. 写出英文名中间文件 ----
DST.write_text(text, encoding="utf-8")

# ---- 4. 生成单章编译 preamble (_tmp.tex) ----
# 与 assets/templates/main.tex 同源；集中放置所有编译期补丁，避免分散到章节源文件。
PREAMBLE = r"""\documentclass[a4paper, 11pt]{ctexrep}
\usepackage{amsmath,amssymb}
\usepackage{graphicx}
\usepackage{booktabs}
\usepackage{multirow}
\usepackage{array}
\usepackage{longtable}
\usepackage{tabularx}
\usepackage[unicode]{hyperref}
\usepackage{indentfirst}
\usepackage{xcolor}
\usepackage{xeCJK}
\usepackage{tikz}
\usetikzlibrary{shapes.geometric, arrows.meta, positioning, fit, backgrounds, calc}
\usepackage{adjustbox}
\usepackage{tcolorbox}
\tcbuselibrary{listings, skins, breakable}
\usepackage{enumitem}
\usepackage{url}
\usepackage{etoolbox}

% === 中文 URL 支持 ===
% url.sty 默认在 math mode 渲染 URL，xeCJK 不接管 math mode，中文会变成豆腐块。
% 重写 \Url@FormatString 去掉 math mode，中文走正常字体分类即可正常显示。
\makeatletter
\def\Url@FormatString{%
 \UrlFont
 \expandafter\UrlLeft\Url@String\UrlRight
}
\makeatother

% === 参考文献降级 + 不跳页 + 不改页眉 ===
% book/ctexrep 的 thebibliography 默认 \chapter*（最大级标题 + 跳页 + 改页眉）。
% 重定义为 \section*，并去掉 \@mkboth，使其与正文页眉保持一致。
\makeatletter
\patchcmd{\thebibliography}{\chapter*{\bibname}}{\section*{\bibname}}{}{}
\patchcmd{\thebibliography}{\@mkboth{\MakeUppercase\bibname}{\MakeUppercase\bibname}}{}{}{}
\makeatother

% === 代码块环境：浅灰打底 + 自动换行 ===
% 用 tcolorbox + listings 引擎（\newtcblisting），才能 breaklines 自动折行长代码行。
% 禁用裸 \verbatim（不折行会溢出页面）。
\newtcblisting{codeblock}{
  colback=gray!10!white, colframe=gray!45!white, boxrule=0.4pt,
  arc=3pt, left=6pt, right=6pt, top=5pt, bottom=5pt,
  listing only, breakable,
  listing options={
    breaklines=true, breakatwhitespace=true,
    basicstyle=\small\ttfamily, showstringspaces=false,
    frame=none, numbers=none, aboveskip=0pt, belowskip=0pt
  }
}

% === 防溢出：吸收段落级微小超宽 ===
% 不能解决 TikZ 节点不可断词 / 显示公式超宽——那些须改源码。
\setlength{\emergencystretch}{3.5em}

\XeTeXlinebreaklocale "zh"
\XeTeXlinebreakskip=0pt
\graphicspath{{figures/}}
\DeclareGraphicsExtensions{.pdf,.png,.jpg}
\hypersetup{colorlinks=true, linkcolor=blue, urlcolor=blue, citecolor=blue}

\begin{document}
\input{""" + DST.name + r"""}
\end{document}
"""

TMP.write_text(PREAMBLE, encoding="utf-8")

print(f"[fix.py] 源: {SRC} -> 中间文件: {DST.name} ({DST.stat().st_size} bytes)")
print(f"[fix.py] 单章编译入口: {TMP.name} ({TMP.stat().st_size} bytes)")
print("[fix.py] 下一步: xelatex -halt-on-error -interaction=nonstopmode _tmp.tex")
