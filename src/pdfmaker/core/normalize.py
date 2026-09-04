# -*- coding: utf-8 -*-
"""core.normalize —— 单一规范化真源：URL → href + TikZ 图宽上限 + 缺字字形修复
+ 长 \\texttt 自动拆词。

单章编译（commands.fix）与整书合并（commands.build）都调用本模块的
``normalize_text()``，保证 URL 规范化、TikZ 包裹、字形修复与拆词在两条流水线
完全一致。所有函数均幂等，可重复调用而不产生副作用。
"""

import re
from urllib.parse import unquote

# 可调阈值统一从 config 收口；用模块别名访问（而非 from ... import X），
# 确保运行时 toml / 环境变量覆盖真正生效。
import pdfmaker.core.config as cfg


def url_to_href(text: str) -> str:
    r"""将 \url{...} 改写为 \href{raw}{display-escaped}。

    - URL 保持原始（不预 percent-encode，交由 hyperref 处理）；
    - 显示文本里的 LaTeX 特殊字符必须转义，否则会进入 math mode 报错。

    幂等：已是 \href 的不重复改写。
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
    r"""给每个 tikzpicture 套 adjustbox 宽度上限（幂等：已包裹的不重复套）。

    只对「尚未被 adjustbox / resizebox 包裹」的 tikzpicture 套一层
    \begin{adjustbox}{max width=\textwidth}；已手工预缩放（如过宽 pipeline 图
    用 \resizebox{\textwidth}{!}{...}）或前次生成的 chN.tex 再次跑 fix，
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


# ---- 缺字字形映射表 ----
# 常见「CJK 字体缺字」字符 → LaTeX 等价写法，拆成两类：
# - _MATH_GLYPH_MAP：数学命令（\ge \le \approx \neq \sim \pm \times \div 及希腊字母等），
#   仅在数学模式合法；fix_glyphs 在正文（非 math mode）会包裹 $...$（如 $\ge$），在已有
#   数学环境内用裸命令（如 \ge），避免裸命令触发「Missing $ inserted」致命错误。
#   本自动修集与预检集 GLYPH_HAZARDS（core/lint.py）相互对齐：预检集预警的正文裸用字符
#   （σ/π/±/℃/希腊字母等）都能在这里被自动修复。
#   注：右箭头（ → ，U+2192）在中文 CJK 字体中存在，刻意不纳入，避免大量误报/误修。
# - _TEXT_GLYPH_MAP：纯文本替换（①-⑩ → (1)-(10)），不受数学模式影响。
_MATH_GLYPH_MAP = {
    # 数学关系符号
    "≥": r"\ge",        # ≥
    "≤": r"\le",        # ≤
    "≈": r"\approx",    # ≈
    "≠": r"\neq",       # ≠
    "∼": r"\sim",       # ∼
    # 运算符 / 单位
    "±": r"\pm",        # ±
    "×": r"\times",     # ×
    "÷": r"\div",       # ÷
    "℃": r"^\circ\mathrm{C}",  # ℃
    "°": r"\circ",      # °
    # 希腊字母（正文裸用缺字；数学模式内为正确写法，由 _replace_glyphs 处理）
    "α": r"\alpha",     # α
    "β": r"\beta",      # β
    "γ": r"\gamma",     # γ
    "δ": r"\delta",     # δ
    "ε": r"\varepsilon",  # ε
    "ζ": r"\zeta",      # ζ
    "η": r"\eta",       # η
    "θ": r"\theta",     # θ
    "λ": r"\lambda",    # λ
    "μ": r"\mu",        # μ
    "ν": r"\nu",        # ν
    "ξ": r"\xi",        # ξ
    "π": r"\pi",        # π
    "ρ": r"\rho",       # ρ
    "σ": r"\sigma",     # σ
    "τ": r"\tau",       # τ
    "υ": r"\upsilon",   # υ
    "φ": r"\phi",       # φ
    "χ": r"\chi",       # χ
    "ψ": r"\psi",       # ψ
    "ω": r"\omega",     # ω
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

    - 数学符号（≥ ≤ ≈ ≠ 等）：正文（非 math mode）包裹 $...$（如 $\ge$），已有数学
      环境（$...$ / \(...\) / \[...\]）内用裸命令（如 \ge），二者都合法，
      杜绝裸 \ge 触发 Missing $ inserted。
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
                    # 双反斜杠 \\：TikZ/表格里的换行命令（\\ 或 \\* 或 \\[...]），
                    # 是一个「不透明」控制符，绝不把它后面的 $ 误当成转义美元（\\$）。
                    # 否则会吞掉本应开启数学模式的 $，导致后续数学状态整体错位。
                    out.append("\\\\")
                    i += 2
                    continue
                if nxt == "$":
                    # 转义美元符 \$，不切换数学模式
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
                # 其它命令（\ge / \alpha 等）原样保留
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
    r"""把 CJK 字体缺字字符替换为 LaTeX 等价写法（数学模式感知）。

    覆盖 ≥ ≤ ≈ ≠ ∼ ± × ÷ ℃ ° 及希腊字母 α–ω，与 scan_glyphs 预警集对齐。
    跳过 \url / \href / \verb / verbatim / codeblock 等受保护片段，避免在 URL 或
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


# ---- 长 \texttt 自动拆词（源头治理 Overfull） ----
# 等宽字体（Latin Modern Mono）禁用断词，且 / . _ : 在文本模式不构成断点：
# 长 \texttt 标识符落在行尾附近即触发 Overfull \hbox（成书实践中最常见的阻断源）。
# check/lint 的 scan_unbreakable_runs 只能「预警」，本函数在规范化阶段直接「修复」：
# 对字形数 ≥ 阈值的 \texttt 内容，在分隔符（\_ _ / .）后插入 \allowbreak{}——
# 它只「允许」断行、不改变排版结果与字形，语义零风险；相邻 \texttt 以 / 连排的
# 接缝处同样补断点（这类连排在 TeX 眼中也是一个不可断整体）。
_RELAX_PROTECTED_RE = re.compile(
    r"\\url\{[^{}]*\}"
    r"|\\href\{[^{}]*\}\{[^{}]*\}"
    r"|\\verb([^a-zA-Z]).*?\1"
    r"|\\begin\{verbatim\}.*?\\end\{verbatim\}"
    r"|\\begin\{lstlisting\}.*?\\end\{lstlisting\}"
    r"|\\begin\{codeblock\}.*?\\end\{codeblock\}",
    flags=re.DOTALL,
)
_TEXTTT_OPEN_RE = re.compile(r"\\texttt\{")
# 相邻 \texttt 以 / 连排的接缝（已含 \allowbreak 的不再重复插入，保证幂等）。
_TEXTTT_JOINT_RE = re.compile(r"\}/(\\allowbreak\{\})?\\texttt\{")
# 转义对（\_ \% 等）按 1 个字形计；CJK/全角按 2 个字形计（宽度约为拉丁 2 倍）。
# 区间依次覆盖：CJK 部首补充/基本区（U+2E80–U+9FFF）、CJK 兼容表意（U+F900–U+FAFF）、
# 竖排变体（U+FE30–U+FE4F）、全角/半角（U+FF00–U+FFEF）。
_CJK_RE = re.compile(r"[⺀-鿿豈-﫿︰-﹏＀-￯]")


def _relax_glyph_len(s: str) -> int:
    """计算拆词语义下的字形数：转义对算 1，CJK/全角算 2。"""
    plain = re.sub(r"\\(.)", r"\1", s)
    return len(plain) + len(_CJK_RE.findall(plain))


def _relax_content(content: str) -> str:
    r"""在 \texttt 内容的分隔符（\_ _ / .）后插入 \allowbreak{}。

    只在单个 ``\texttt`` 的内容内部工作；已含 \allowbreak 的内容原样返回（幂等）。
    含未转义花括号的内容跳过（结构复杂，交给结构类门禁，不在此冒险）。
    """
    if "\\allowbreak" in content:
        return content
    if "{" in content or "}" in content:
        return content
    out: list[str] = []
    i = 0
    n = len(content)
    while i < n:
        c = content[i]
        if c == "\\" and i + 1 < n:
            pair = content[i:i + 2]
            out.append(pair)
            i += 2
            # 转义下划线 \_ 是标识符的高频接缝：在其后允许断行
            if pair == r"\_":
                out.append(r"\allowbreak{}")
            continue
        out.append(c)
        i += 1
        if c in "_/.":
            out.append(r"\allowbreak{}")
    return "".join(out)


def _relax_segment(seg: str, threshold: int) -> str:
    """处理一个非保护片段：拆长 \texttt 内容 + 相邻 \texttt 的 / 接缝。"""
    pieces: list[str] = []
    cursor = 0
    for m in _TEXTTT_OPEN_RE.finditer(seg):
        j = m.end()
        depth = 1
        while j < len(seg) and depth > 0:
            c = seg[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break  # 未闭合：放弃本片段（结构错误由其它门禁报告）
        content = seg[m.end():j - 1]
        pieces.append(seg[cursor:m.start()])
        if _relax_glyph_len(content) >= threshold:
            content = _relax_content(content)
        pieces.append(r"\texttt{" + content + "}")
        cursor = j
    pieces.append(seg[cursor:])
    out = "".join(pieces)
    # 相邻 \texttt 的 / 接缝补断点（幂等：已有 \allowbreak 时正则不重插）
    out = _TEXTTT_JOINT_RE.sub(
        lambda m: r"}/\allowbreak{}\texttt{" if not m.group(1) else m.group(0), out
    )
    return out


def relax_long_texttt(text: str, threshold: int | None = None) -> str:
    r"""对字形数 ≥ threshold 的 ``\texttt`` 内容自动插入 ``\allowbreak{}``（幂等）。

    - 仅允许断行、不改变排版结果与字形，语义零风险；
    - 跳过 url/href/verb/verbatim/lstlisting/codeblock 等受保护片段；
    - 已含 ``\allowbreak`` 的内容与接缝不重复插入（幂等，可随 fix 反复跑）；
    - threshold 为 None 时读 ``cfg.TEXTTT_RELAX_CHARS``（默认 20，0 = 关闭）。
    """
    if threshold is None:
        threshold = cfg.TEXTTT_RELAX_CHARS
    if threshold <= 0 or r"\texttt{" not in text:
        return text
    out: list[str] = []
    last = 0
    for m in _RELAX_PROTECTED_RE.finditer(text):
        out.append(_relax_segment(text[last:m.start()], threshold))
        out.append(m.group(0))
        last = m.end()
    out.append(_relax_segment(text[last:], threshold))
    return "".join(out)


def normalize_text(text: str) -> str:
    """单章与整书合并共用的「单一规范化真源」。

    顺序：url_to_href（URL 规范化） → wrap_tikz（TikZ 图宽上限） → fix_glyphs（缺字字形替换）
    → relax_long_texttt（长 \\texttt 自动拆词）。
    四者皆幂等，可重复调用而不产生副作用。commands.fix（单章）与 commands.build（合并）
    都调用本函数，保证 URL / TikZ / 字形 / 拆词在两条流水线完全一致。
    """
    return relax_long_texttt(fix_glyphs(wrap_tikz(url_to_href(text))))
