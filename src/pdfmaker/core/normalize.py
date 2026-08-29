# -*- coding: utf-8 -*-
"""单一规范化真源：URL → href + TikZ 图宽上限。

单章编译（commands.fix）与整书合并（commands.build）都调用本模块的
``normalize_text()``，保证 URL 规范化与 TikZ 包裹在两条流水线完全一致。
所有函数均幂等。
"""

import re
from urllib.parse import unquote


def url_to_href(text: str) -> str:
    """将 \\url{...} 改写为 \\href{raw}{display-escaped}。

    - URL 保持原始（不预 percent-encode，交由 hyperref 处理）。
    - 显示文本里的 LaTeX 特殊字符必须转义，否则会进入 math mode 报错。
    幂等：已是 \\href 的不重复改写。
    """

    def repl(m: re.Match) -> str:
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
            # 学术 URL 高频含 ~（如 ~user 主页）与 ^（如检索式）；二者在 LaTeX 正文里
            # 是活动字符：~ 是非断空格、^ 触发「Missing $ inserted」编译错误，必须以
            # \textasciitilde{} / \textasciicircum{} 转义（与 _ & $ # % 同属显示文本转义）。
            .replace("~", r"\textasciitilde{}")
            .replace("^", r"\textasciicircum{}")
        )
        return r"\href{" + url + "}{" + display + "}"

    return re.sub(r"\\url\{([^{}]+)\}", repl, text)


def wrap_tikz(text: str) -> str:
    """给每个 tikzpicture 套 adjustbox 宽度上限（幂等：已包裹的不重复套）。

    只对「尚未被 adjustbox / resizebox 包裹」的 tikzpicture 套一层
    \\begin{adjustbox}{max width=\\textwidth}；已手工预缩放（如过宽 pipeline 图
    用 \\resizebox{\\textwidth}{!}{...}）或前次生成的 chN.tex 再次跑 fix，
    都不会产生双层嵌套包裹。max width 仅对超宽图缩放，正常图保持原样。
    """
    out = []
    i = 0
    bt = r"\begin{tikzpicture}"
    et = r"\end{tikzpicture}"
    while True:
        b = text.find(bt, i)
        if b == -1:
            out.append(text[i:])
            break
        e = text.find(et, b)
        if e == -1:
            out.append(text[i:])
            break
        e_end = e + len(et)
        seg = text[i:b]  # 本 tikz 之前、上一处理边界之后的片段
        # 若此前已存在未闭合的 adjustbox / resizebox（即本 tikz 已被包裹），跳过
        already_wrapped = (r"\begin{adjustbox}" in seg) or (r"\resizebox{" in seg)
        out.append(seg)
        if already_wrapped:
            out.append(text[b:e_end])  # 已包裹：原样保留，不重复套
        else:
            out.append(r"\begin{adjustbox}{max width=\textwidth}" + "\n")
            out.append(text[b:e_end])
            out.append(r"\end{adjustbox}" + "\n")
        i = e_end
    return "".join(out)


# 常见「CJK 字体缺字」字符 → LaTeX 等价写法。拆成两类：
# - _MATH_GLYPH_MAP：数学命令（\ge \le \approx \neq \sim \pm \times \div 及希腊字母等），
#   仅在数学模式合法；fix_glyphs 在正文（非 math mode）会包裹 $...$（如 $\ge$），在已有
#   数学环境内用裸命令（如 \ge），避免裸命令触发「Missing $ inserted」致命错误。
#   本自动修集与预检集 GLYPH_HAZARDS（lint.py）保持一致：正文裸用 σ/π/±/℃/希腊字母等
#   既会被 scan_glyphs 预警，也能被 fix_glyphs 自动修复。
#   注：→（U+2192）在中文 CJK 字体中存在，刻意不纳入，避免大量误报/误修。
# - _TEXT_GLYPH_MAP：纯文本替换（①-⑩ → (1)-(10)），不受数学模式影响。
_MATH_GLYPH_MAP = {
    # 数学关系符号
    "\u2265": r"\ge",        # ≥
    "\u2264": r"\le",        # ≤
    "\u2248": r"\approx",    # ≈
    "\u2260": r"\neq",       # ≠
    "\u223c": r"\sim",       # ∼
    # 运算符 / 单位
    "\u00b1": r"\pm",        # ±
    "\u00d7": r"\times",     # ×
    "\u00f7": r"\div",       # ÷
    "\u2103": r"^\circ\mathrm{C}",  # ℃
    "\u00b0": r"\circ",      # °
    # 希腊字母（正文裸用缺字；数学模式内为正确写法，由 _replace_glyphs 处理）
    "\u03b1": r"\alpha",     # α
    "\u03b2": r"\beta",      # β
    "\u03b3": r"\gamma",     # γ
    "\u03b4": r"\delta",     # δ
    "\u03b5": r"\varepsilon",  # ε
    "\u03b6": r"\zeta",      # ζ
    "\u03b7": r"\eta",       # η
    "\u03b8": r"\theta",     # θ
    "\u03bb": r"\lambda",    # λ
    "\u03bc": r"\mu",        # μ
    "\u03bd": r"\nu",        # ν
    "\u03be": r"\xi",        # ξ
    "\u03c0": r"\pi",        # π
    "\u03c1": r"\rho",       # ρ
    "\u03c3": r"\sigma",     # σ
    "\u03c4": r"\tau",       # τ
    "\u03c5": r"\upsilon",   # υ
    "\u03c6": r"\phi",       # φ
    "\u03c7": r"\chi",       # χ
    "\u03c8": r"\psi",       # ψ
    "\u03c9": r"\omega",     # ω
}
_TEXT_GLYPH_MAP = {chr(0x2460 + _i): f"({_i + 1})" for _i in range(10)}  # ①-⑩ → (1)-(10)

# 受保护片段：其中的字符不做字形替换（URL / 逐字块等）。
_PROTECTED_RE = re.compile(
    r"\\url\{[^{}]*\}"
    r"|\\href\{[^{}]*\}\{[^{}]*\}"
    r"|\\verb([^a-zA-Z]).*?\1"
    r"|\\begin\{verbatim\}.*?\\end\{verbatim\}"
    r"|\\begin\{codeblock\}.*?\\end\{codeblock\}",
    flags=re.DOTALL,
)


def _replace_glyphs(seg: str) -> str:
    r"""把 seg 内的缺字字符替换为 LaTeX 等价写法，数学模式感知。

    - 数学符号（≥ ≤ ≈ ≠）：正文（非 math mode）包裹 $...$（如 $\ge$），已有数学
      环境（$...$ / \\(..\\) / \\[..\\]）内用裸命令（如 \\ge），二者都合法，
      杜绝裸 \\ge 触发 Missing $ inserted。
    - 带圈数字（①-⑩）：纯文本替换为 (1)-(10)，两类模式皆可。
    幂等：替换后不再含这些字符，二次调用无副作用。
    """
    out: list[str] = []
    i = 0
    n = len(seg)
    math = False
    while i < n:
        c = seg[i]
        if c == "\\":
            if i + 1 < n:
                nxt = seg[i + 1]
                if nxt == "\\":
                    # 双反斜杠 \\ ：TikZ/表格里的换行命令（\\ 或 \\* 或 \\[...]），
                    # 是一个「不透明」控制符，绝不把它后面的 $ 误当成转义美元（\\$）。
                    # 否则会吞掉本应开启数学模式的 $，导致后续数学状态整体错位。
                    out.append("\\\\")
                    i += 2
                    continue
                if nxt == "$":
                    # 转义美元符，不切换数学模式
                    out.append(r"\$")
                    i += 2
                    continue
                if nxt in "([":
                    math = True
                    out.append(seg[i:i + 2])
                    i += 2
                    continue
                if nxt in ")]":
                    math = False
                    out.append(seg[i:i + 2])
                    i += 2
                    continue
                # 其它命令（\ge / \alpha 等）原样保留，继续
                out.append(c)
                i += 1
                continue
            out.append(c)
            i += 1
            continue
        if c == "$":
            # 单 $ 切换数学模式（$$ 两次切换回到原状态，正确反映显示公式）
            math = not math
            out.append(c)
            i += 1
            continue
        if c in _MATH_GLYPH_MAP:
            rep = _MATH_GLYPH_MAP[c]
            out.append(rep if math else "$" + rep + "$")
            i += 1
            continue
        if c in _TEXT_GLYPH_MAP:
            out.append(_TEXT_GLYPH_MAP[c])
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)


def fix_glyphs(text: str) -> str:
    """把 CJK 字体缺字字符（≥ ≤ ≈ ≠ ∼ ± × ÷ ℃ ° 及希腊字母 α–ω，与 scan_glyphs 预警集一致）
    替换为 LaTeX 等价写法（数学模式感知）。

    跳过 \\url / \\href / \\verb / verbatim / codeblock 等受保护片段，避免在 URL 或
    逐字块里误改。幂等：替换后不再含这些字符，二次调用无副作用。
    """
    if not any(g in text for m in (_MATH_GLYPH_MAP, _TEXT_GLYPH_MAP) for g in m):
        return text
    out = []
    last = 0
    for m in _PROTECTED_RE.finditer(text):
        out.append(_replace_glyphs(text[last:m.start()]))
        out.append(m.group(0))
        last = m.end()
    out.append(_replace_glyphs(text[last:]))
    return "".join(out)


def normalize_text(text: str) -> str:
    """单章与整书合并共用的「单一规范化真源」。

    顺序：url_to_href（URL 规范化）→ wrap_tikz（图宽上限）→ fix_glyphs（缺字字形替换）。
    三者皆幂等，可重复调用而不产生副作用。commands.fix（单章）与 commands.build（合并）
    都调用本函数，保证 URL / TikZ / 字形 在两条流水线完全一致。
    """
    return fix_glyphs(wrap_tikz(url_to_href(text)))
