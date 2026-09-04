# -*- coding: utf-8 -*-
r"""core.lint —— 编译前静态扫描：把「编译才报错」的坑挡在 xelatex 之前。

扫描器总览（按用途分组）
------------------------
字符与 URL：
- ``scan_glyphs``               CJK 字体缺字风险字符（≥ ≤ ≈ ≠ ①-⑩ 希腊字母等）
- ``scan_truncated_urls``       疑似被截断 / 含空白的残破 URL
- ``scan_codeblock_nonascii``   verbatim/codeblock/lstlisting 内的非 ASCII 字符
- ``scan_unbreakable_runs``     等宽 ``\\texttt`` 不可断行长串（Overfull \\hbox 风险预警）
- ``scan_squeezed_tables``      tabularx 非 X 列超长不可断长串（「单列挤压」预警）

TikZ：
- ``scan_tikz_badbreak``        节点内 ``\\`` 换行但未声明 align=（编译期 missing \item Fatal）
- ``scan_tikz_amp``             节点文本内未转义 ``&``（编译期 Missing $ inserted）

排版样式门禁（阻断级）：
- ``scan_table_style``          三线表禁用裸 ``\hline`` 与列格式竖线 ``|``
- ``scan_table_rules``          三线表须含 ``\toprule`` / ``\bottomrule`` 顶底线
- ``scan_caption_position``     表题在上 / 图题在下
- ``scan_raw_verbatim``         伪代码禁用裸 ``verbatim`` / ``lstlisting``

引用与结构：
- ``scan_crossref``             跨章 ``\ref`` 预检（warning 级）
- ``scan_cite_undef``           悬空 ``\cite``（无对应 ``\bibitem``，阻断级）
- ``scan_redundant_heading_number`` 标题手写前导编号（与 ctexrep 自动编号叠加重复）

整书合并（main.tex）：
- ``scan_frontmatter_tables`` / ``inject_frontmatter_noindent``
                                前置整宽表格缺 ``\noindent`` 的扫描与自动修复
- ``scan_missing_frontmatter``  前置部分（摘要/序言/术语表）存在性预检
- ``scan_empty_frontmatter``    前置部分「存在但正文为空」空壳预检
- ``scan_preamble_drift``       main.tex 与 _preamble_shared.tex 补丁漂移预检
"""

import re

from pdfmaker.core.text import strip_latex_comments

# ---- 缺字风险字符集 ----
# CJK 字体（ctexrep 默认的系统中文字体）常缺的数学符号 / 带圈数字 / 希腊字母。
# 在正文（非 math mode）直接使用会触发 xelatex 的 "Missing character"，
# 表现为豆腐块 / 空白。预检后提醒作者改用 \ge / \le 等数学写法或纯文本编号。
# 注：右箭头（ → ，U+2192）在中文 CJK 字体中存在（中文文档编译零 Missing character），
# 纳入会大量误报，故不加入本集。
GLYPH_HAZARDS: dict[str, str] = {
    # 数学关系符号
    "≥": r"$\ge$",      # ≥
    "≤": r"$\le$",      # ≤
    "≈": r"$\approx$",  # ≈
    "≠": r"$\ne$",      # ≠
    "∼": r"$\sim$",     # ∼
    # 带圈数字 ①-⑩
    "①": "(1)", "②": "(2)", "③": "(3)", "④": "(4)",
    "⑤": "(5)", "⑥": "(6)", "⑦": "(7)", "⑧": "(8)",
    "⑨": "(9)", "⑩": "(10)",
    # 运算符 / 单位与希腊字母：正文裸用同样缺字（数学模式内的正确写法由 _mask_math 排除）
    "±": r"$\pm$",              # ±
    "℃": r"$^\circ\mathrm{C}$",  # ℃
    "α": r"$\alpha$",        # α
    "β": r"$\beta$",         # β
    "γ": r"$\gamma$",        # γ
    "δ": r"$\delta$",        # δ
    "ε": r"$\varepsilon$",   # ε
    "ζ": r"$\zeta$",         # ζ
    "η": r"$\eta$",          # η
    "θ": r"$\theta$",        # θ
    "λ": r"$\lambda$",       # λ
    "μ": r"$\mu$",           # μ
    "ν": r"$\nu$",           # ν
    "ξ": r"$\xi$",           # ξ
    "π": r"$\pi$",           # π
    "ρ": r"$\rho$",          # ρ
    "σ": r"$\sigma$",        # σ
    "τ": r"$\tau$",          # τ
    "υ": r"$\upsilon$",      # υ
    "φ": r"$\phi$",          # φ
    "χ": r"$\chi$",          # χ
    "ψ": r"$\psi$",          # ψ
    "ω": r"$\omega$",        # ω
}

# ---- 数学模式区域（scan_glyphs 掩码用） ----
_MATH_ENV_NAMES = (
    "equation|equation*|align|align*|gather|gather*|multline|multline*|"
    "flalign|flalign*|alignat|alignat*|displaymath|math|"
    "array|matrix|matrix*|pmatrix|pmatrix*|bmatrix|bmatrix*|vmatrix|vmatrix*|"
    "Vmatrix|Vmatrix*|Bmatrix|Bmatrix*|cases|split|smallmatrix|"
    "aligned|aligned*|gathered|gathered*"
)
_MATH_ENV_RE = re.compile(
    r"\\begin\{(" + _MATH_ENV_NAMES + r")\}.*?\\end\{\1\}", re.DOTALL
)
# 注意：$...$ 分支的字符组必须写成 [^\\$] 而非 [^$]——否则在「裸 $ 后跟随大量
# 反斜杠命令」的正文（如代码块里出现 #$ARGUMENTS 且后文全是 \href）上，\\. 与 [^$]
# 在每个反斜杠位置产生两条解析路径，懒惰量词回溯空间呈 2^N 爆炸，scan_glyphs 直接
# 挂死（曾导致 chapter SOP 在 check 阶段 99% CPU 空转）。排除反斜杠后每个位置只有
# 唯一解析路径，语义不变（\$ 仍由 \\. 消费）。
_INLINE_MATH_RE = re.compile(
    r"(?<!\\)\$\$.*?\$\$"                                # $$ ... $$
    r"|(?<!\\)\$(?!\$)(?:\\.|[^\\$])*?(?<!\\)\$(?!\$)"   # $ ... $（非 $$）
    r"|\\\(.*?\\\)"                                       # \( ... \)
    r"|\\\[.*?\\\]",                                      # \[ ... \]
    re.DOTALL,
)


def _mask_math(text: str) -> str:
    """把数学模式区域替换成等长的空格（保留行号），使 scan_glyphs 只扫正文区域。"""
    masked = text
    for pat in (_MATH_ENV_RE, _INLINE_MATH_RE):
        masked = pat.sub(lambda m: " " * len(m.group(0)), masked)
    return masked


def scan_glyphs(text: str) -> list[dict]:
    """预检「CJK 字体缺字」风险字符，返回每处 {char, codepoint, line, suggestion}。

    - 仅扫描正文（非数学模式）区域：``$\\ge$`` 等数学写法是正确写法，不再误报；
    - 仅扫描正文行（跳过 % 注释整行），命中即提示改用数学写法 / 纯文本编号。
    """
    masked = _mask_math(text)
    hits: list[dict] = []
    for ln, line in enumerate(masked.splitlines(), 1):
        if line.lstrip().startswith("%"):
            continue
        for ch, sug in GLYPH_HAZARDS.items():
            if ch in line:
                hits.append({
                    "char": ch,
                    "codepoint": f"U+{ord(ch):04X}",
                    "line": ln,
                    "suggestion": sug,
                })
    return hits


# 疑似被截断/污染的 URL：包含 Unicode 省略号、3+ 连续点、或空白字符。
_TRUNC_URL_RE = re.compile(
    r"\\url\{([^{}]*)\}|\\href\{([^{}]*)\}\{",
    flags=re.DOTALL,
)


def scan_truncated_urls(text: str) -> list[str]:
    """预检疑似被截断 / 含空白的残破 URL，返回其原文片段列表。

    素材采集工具常把长 URL 截断成 ``https://.../foo...``，这种链接无法验活、
    成书即死链。命中规则：含 Unicode 省略号「…」、含 3 个及以上连续点
    （非 ``://`` 协议部分）、或含空白字符。提醒作者替换为素材里完整的 LIVE 链接。
    """
    bad: list[str] = []
    for m in _TRUNC_URL_RE.finditer(text):
        u = (m.group(1) or m.group(2) or "").strip()
        if not u:
            continue
        if "…" in u:
            bad.append(u)
            continue
        # 3+ 连续点即视为截断（:// 协议分隔只有 2 个点，不会误伤）
        if re.search(r"\.{3,}", u):
            bad.append(u)
            continue
        if any(c.isspace() for c in u):
            bad.append(u)
            continue
    return bad


def _iter_tikz_nodes(text: str):
    """遍历全文每个 tikzpicture 环境内的 \\node 节点，产出 (块起点, 节点起点, 选项段, 节点文本)。

    供 scan_tikz_badbreak / scan_tikz_amp 共用：越过 (...) 坐标组与 [...] 选项组
    （含嵌套），定位节点文本大括号内容；括号匹配找到文本结束。
    """
    for tm in re.finditer(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", text, flags=re.DOTALL):
        block = tm.group(0)
        bstart = tm.start()
        for nm in re.finditer(r"\\(?:node|Node)\b", block):
            i = nm.end()
            # 越过坐标组 (...) 与选项组 [...]（含嵌套），定位节点文本开括号 {
            j = i
            text_start = -1
            while j < len(block):
                c = block[j]
                if c == "\\":
                    j += 2
                    continue
                if c in "([":
                    depth2 = 1
                    j += 1
                    while j < len(block) and depth2 > 0:
                        cc = block[j]
                        if cc == "\\":
                            j += 2
                            continue
                        if cc in "([":
                            depth2 += 1
                        elif cc in ")]":
                            depth2 -= 1
                        j += 1
                    continue
                if c == "{":
                    text_start = j
                    break
                j += 1
            if text_start == -1:
                continue
            # 括号匹配找到文本结束 }
            depth = 0
            k = text_start
            text_end = -1
            while k < len(block):
                c = block[k]
                if c == "\\":
                    k += 2
                    continue
                if c == "{":
                    depth += 1
                elif c == "}":
                    depth -= 1
                    if depth == 0:
                        text_end = k
                        break
                k += 1
            if text_end == -1:
                continue
            node_text = block[text_start + 1:text_end]
            opts = block[i:text_start]
            yield bstart, nm.start(), block, opts, node_text


def scan_tikz_badbreak(text: str) -> list[dict]:
    r"""预检 TikZ 节点内 ``\\`` 换行但未声明 align= 的危险写法（编译期 missing \item Fatal）。

    写法示例：``\node[...]{中心聚合\\服务器}`` 在 ``\\`` 处触发 LaTeX "missing \item" Fatal。
    返回每处 {line, snippet}，供 balance 作为阻断级提示，把编译错误挡在 xelatex 之前。

    仅扫描 tikzpicture 环境内的 \node 文本大括号内容；会跳过 (...) 坐标组与
    [...] 选项组（含嵌套），只对「节点文本内的真实换行 \\」报警，且选项已含 align 的不报警。
    """
    hits: list[dict] = []
    for bstart, nstart, block, opts, node_text in _iter_tikz_nodes(text):
        # `\\` 换行但非命令/非 ( / [ / ] 跟随；选项缺 align → 危险
        bad_break = bool(re.search(r"\\\\(?![A-Za-z(\[\]])", node_text))
        # align 可能继承自 name/.style={...,align=...}（如 box/.style={...,align=center}）。
        # 同一 tikzpicture 内任意节点/styledef 含 align 即视为已声明，避免
        # 「共享 style + 节点用 \\ 换行」被误报阻断。
        if bad_break and "align" not in opts and "align" not in block:
            line = text[:bstart].count("\n") + block[:nstart].count("\n") + 1
            hits.append({"line": line, "snippet": node_text[:60]})
    return hits


# 等宽字体（Latin Modern Mono）缺字风险环境：verbatim/codeblock/lstlisting。
# 这些环境内若含非 ASCII（希腊字母 σ/π、中文、全角符号），等宽字体无对应字形，
# 编译期触发 Missing character。fix_glyphs 为保代码原样会跳过 verbatim/codeblock，
# 故只能靠本预检在 check/lint 阶段提前 warning。
_CODE_NONASCII_ENV_RE = re.compile(
    r"\\begin\{(verbatim|codeblock|lstlisting)\}(.*?)\\end\{\1\}",
    flags=re.DOTALL,
)


def scan_codeblock_nonascii(text: str) -> list[dict]:
    """预检 verbatim/codeblock/lstlisting 内的非 ASCII 字符（等宽字体缺字风险）。

    等宽字体（Latin Modern Mono）不含希腊字母 / 中文 / 全角符号；代码块注释里写
    ``±3σ`` 之类会落入该字体触发 xelatex 的 Missing character（编译期才暴露，白跑两遍
    编译）。``fix_glyphs`` 出于保护代码原样会跳过 verbatim/codeblock，无法在规范化阶段修复，
    故本扫描在 check / lint 阶段提前 warning，让作者改用纯 ASCII 或把说明移出代码块。

    返回 [{line, char, codepoint, snippet}]，每个环境**每行至多上报一个字符**以免刷屏。
    """
    hits: list[dict] = []
    for m in _CODE_NONASCII_ENV_RE.finditer(text):
        body = m.group(2)
        start = text[:m.start()].count("\n") + 1
        for i, line in enumerate(body.split("\n"), start):
            for ch in line:
                if ord(ch) > 127:
                    hits.append({
                        "line": i,
                        "char": ch,
                        "codepoint": f"U+{ord(ch):04X}",
                        "snippet": line.strip()[:60],
                    })
                    break  # 每行只报首个非 ASCII，避免噪声
    return hits


# ---- 不可断行长串（Overfull \hbox 风险）预检 ----
# \texttt 在 Latin Modern Mono 下禁用断词（hyphenchar=-1），且 / . _ : 等符号在文本模式
# 不构成断点；相邻 \texttt 用 / 连排在 TeX 眼中同样是一个不可断的整体。这类长串一旦
# 落在行尾附近即触发 Overfull \hbox（真实成书写作期的 12 处 Overfull 全部源于此，
# 单处最大溢出 191pt）。本扫描在 check / lint 阶段（编译前）预警，把「编译后读 log
# 才发现」提前为「写作期即知」。warning 级，不阻断。
_TEXTTT_OPEN_RE = re.compile(r"\\texttt\{")
# 「不可断字符」之外的边界：空白、连字符 -（TeX 允许在显式连字符后断行）、
# CJK/全角字符（xeCJK 在其前后天然提供断点）、零宽语法花括号 {}、以及命令词
# （\section、\quad 等——其产物可断/为零宽，先以等长空格替换再扫，坐标不漂移）。
# 转义对 ``\X``（``\_``、``\%`` 等，渲染为 1 个不可断字形）允许并入串内。
_LONGRUN_CMD_RE = re.compile(r"\\[A-Za-z]+\*?")
_LONGRUN_RE = re.compile(r"(?:\\[^A-Za-z\s]|[^\s\-\\{}⺀-\U0010ffff])+")
# 逐字符置空但保留换行（保持行号坐标）：用于屏蔽 codeblock/verbatim/lstlisting
_CODE_MASK_RE = re.compile(r"[^\n]")


def _texttt_spans(t: str) -> tuple[str, list[tuple[int, int]]]:
    """把 ``\\texttt{...}`` 标记剥离为纯内容，返回（变换后文本, 内容区间列表）。

    变换后文本中每个 ``\\texttt{X}`` 被替换为 ``X``（内容原样保留），区间列表记录
    各内容段在变换后文本中的 [start, end) 坐标。删除的只有命令标记与定界花括号，
    不换行、不新增字符，因此变换后文本的行号与源文本严格一致。
    未闭合的 ``\\texttt{`` 直接放弃解析（结构错误由其它门禁报告，本扫描不背锅）。
    """
    pieces: list[str] = []
    spans: list[tuple[int, int]] = []
    out_len = 0
    cursor = 0
    for m in _TEXTTT_OPEN_RE.finditer(t):
        j = m.end()
        depth = 1
        while j < len(t) and depth > 0:
            c = t[j]
            if c == "\\":
                j += 2
                continue
            if c == "{":
                depth += 1
            elif c == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break  # 未闭合：放弃本扫描，交给结构类门禁
        pieces.append(t[cursor:m.start()])
        out_len += m.start() - cursor
        content = t[m.end():j - 1]
        pieces.append(content)
        spans.append((out_len, out_len + len(content)))
        out_len += len(content)
        cursor = j
    pieces.append(t[cursor:])
    return "".join(pieces), spans


def scan_unbreakable_runs(text: str, threshold: int = 25) -> list[dict]:
    r"""预检 ``\texttt`` 等宽不可断行长串（落在行尾附近时触发 Overfull \hbox）。

    判定规则：
    - 剥掉 LaTeX 注释；屏蔽 codeblock/verbatim/lstlisting（其中 ``\texttt`` 是字面文本
      而非命令；屏蔽保留换行，行号坐标不变）；
    - 将 ``\texttt{X}`` 展开为 ``X``，再按「非空白、非 ``-``、非 CJK/全角」取极大连续段
      ——相邻 ``\texttt{a}/\texttt{b}`` 经 ``/`` 连排在 TeX 眼中也是不可断整体，会被
      自然并入同一段；
    - 仅当某段与至少一个 ``\texttt`` 内容区间相交才上报（正文英文单词可走断词，
      不在预警范围；长 URL 走 ``\url``/``\href`` 的可断行实现，也不误报）；
    - 段长按字形数计（``\_`` 等转义序列算 1 个字符），≥ threshold 即预警。

    返回 [{line, run, length}]（warning 级，不阻断；``threshold <= 0`` 时直接返回空）。
    这是启发式预警：长串只有落在行尾附近才会真实溢出，命中不等于必然 Overfull。
    """
    if threshold <= 0:
        return []
    t = strip_latex_comments(text)
    t = _CODE_NONASCII_ENV_RE.sub(lambda m: _CODE_MASK_RE.sub(" ", m.group(0)), t)
    transformed, spans = _texttt_spans(t)
    if not spans:
        return []
    # 命令词（\section、\quad 等）以等长空格替换后再扫：它们要么是断点、要么零宽，
    # 不应与相邻 \texttt 内容粘成假长串；等长替换保证区间坐标与行号不漂移。
    scan_text = _LONGRUN_CMD_RE.sub(lambda m: " " * len(m.group(0)), transformed)
    hits: list[dict] = []
    for m in _LONGRUN_RE.finditer(scan_text):
        run = m.group(0)
        if not any(s < m.end() and m.start() < e for s, e in spans):
            continue  # 不与任何 \texttt 内容相交：可断词的正文/命令，不预警
        length = len(run) - run.count("\\")  # 转义对（\_ 等）按 1 个字形计
        if length < threshold:
            continue
        line = scan_text.count("\n", 0, m.start()) + 1
        display = re.sub(r"\\(.)", r"\1", run)
        hits.append({"line": line, "run": display[:80], "length": length})
    return hits


def scan_tikz_amp(text: str) -> list[dict]:
    r"""预检 TikZ 节点文本内的未转义 ``&``（编译期会触发 Missing $ inserted / 对齐符错误）。

    在 align=... 的节点里，``&`` 被当作 tabular 列分隔符，直接编译报错（如残差块缩写
    ``Add & Norm``）。扫描 tikzpicture 内 \node 的文本大括号内容，找出未转义
    （非 ``\&`` 前置）的 &，返回 {line, snippet}。
    仅查 \node 文本，不查 \matrix（其 & 是合法的单元格分隔符）。
    """
    hits: list[dict] = []
    for bstart, nstart, block, opts, node_text in _iter_tikz_nodes(text):
        for idx in range(len(node_text)):
            if node_text[idx] == "&" and (idx == 0 or node_text[idx - 1] != "\\"):
                line = (
                    text[:bstart].count("\n")
                    + block[:nstart].count("\n")
                    + node_text[:idx].count("\n")
                    + 1
                )
                snippet = node_text[max(0, idx - 15):idx + 15]
                hits.append({"line": line, "snippet": snippet})
    return hits


# ---- 前置部分整宽表格 \noindent 预检与自动修复 ----
# 章节入口标记：main.tex 中首个 \input{第...} 之前即「前置部分」（序言/摘要/术语表）。
_FRONTMATTER_INPUT_RE = re.compile(r"\\input\{第")


def scan_frontmatter_tables(text: str) -> list[int]:
    r"""预检 main.tex 前置部分的整宽表格（tabularx/tabular/longtable）是否缺 ``\noindent``。

    前置表格若紧跟空行（新段落带 \parindent，11pt 下 2em≈21.9pt），会与整宽表格叠加，
    触发恰好 21.9pt 的 Overfull。返回缺 \noindent 的表格所在行号列表，供 build 合并前
    提醒并给出精准修复提示。

    判定：取每个前置表格所在「段落」（距其上最近空行之后的片段），若该片段不含
    \noindent，则视为会在段落缩进下溢出。章节内部的表格不在此列（在章节 .tex 中，且
    单章编译由 overflow 兜底）。
    """
    m = _FRONTMATTER_INPUT_RE.search(text)
    fm = text[:m.start()] if m else text
    bad: list[int] = []
    # table 浮动体范围：其内部的 tabularx/tabular 不参与首行缩进，须跳过以免误报。
    float_ranges = [
        (mm.start(), mm.end())
        for mm in re.finditer(r"\\begin\{table\}.*?\\end\{table\}", fm, flags=re.DOTALL)
    ]
    table_open = re.compile(r"\\begin\{(tabularx|tabular|longtable)\}")
    for tm in table_open.finditer(fm):
        # 仅「行首顶格」的表格才算流内表格（与 inject 行为一致）；
        # 若同行前面还有 \begin{table} 等内容，则不是顶格流内表格。
        line_start = fm.rfind("\n", 0, tm.start()) + 1
        if fm[line_start:tm.start()].strip():
            continue
        if any(s <= tm.start() < e for s, e in float_ranges):
            continue  # 位于 table 浮动体内，跳过
        pre = fm[:tm.start()]
        seg = pre[pre.rfind("\n\n") + 2:] if "\n\n" in pre else pre
        if "\\noindent" not in seg:
            lineno = text[:tm.start()].count("\n") + 1
            bad.append(lineno)
    return bad


def inject_frontmatter_noindent(text: str) -> str:
    r"""在前置部分给「顶格的流内整宽表格」自动补 ``\noindent``，返回注入后的全文。

    消除「段落缩进 + 整宽表格」叠加导致的恰好 \parindent 的 Overfull（合并时才暴露、
    白跑整书编译）。

    设计要点
    --------
    - **仅作用于 _build 副本**：由 build 在生成合并副本时调用，源 main.tex 不变；
    - **幂等**：表格上一非空行已是 \noindent 则跳过（源已手写 \noindent 时不会重复加）；
    - **仅前置部分**：章节内部表格不在此列（章节 .tex 内的表格由单章 overflow 兜底）。
    """
    m = _FRONTMATTER_INPUT_RE.search(text)
    cut = m.start() if m else len(text)
    head = text[:cut]
    tail = text[cut:]
    # table 浮动体范围：其内部的 tabularx/tabular 不参与首行缩进，跳过（与 scan 一致）。
    float_ranges = [
        (mm.start(), mm.end())
        for mm in re.finditer(r"\\begin\{table\}.*?\\end\{table\}", head, flags=re.DOTALL)
    ]
    lines = head.split("\n")
    out: list[str] = []
    table_open = re.compile(r"\\begin\{(?:tabularx|tabular|longtable)\}")
    for i, line in enumerate(lines):
        stripped = line.strip()
        if table_open.match(stripped):
            # 计算该行表格在 head 中的绝对偏移，判断是否落在 table 浮动体内
            offset = len("\n".join(lines[:i])) + (1 if i > 0 else 0)
            if any(s <= offset < e for s, e in float_ranges):
                out.append(line)
                continue
            prev = ""
            for j in range(i - 1, -1, -1):
                if lines[j].strip():
                    prev = lines[j].strip()
                    break
            if prev != r"\noindent":
                out.append(r"\noindent")
        out.append(line)
    return "\n".join(out) + tail


# ---- 排版样式门禁：三线表 ----
# 学术中文书稿要求表格用 booktabs 的 \toprule/\midrule/\bottomrule，严禁 \hline
# 与列格式里的竖线 |（vertical rule）。裸 \hline / 竖线会退化成「网格表」，
# 与规范确立的三线表范式冲突。
def scan_table_style(text: str) -> list[dict]:
    r"""预检非三线表的退化写法，返回每处 {line, kind, snippet}。

    - ``kind == "hline"``：出现裸 ``\hline``（三线表应改用 ``\toprule/\midrule/\bottomrule``）；
    - ``kind == "vrule"``：tabular/tabularx/longtable 的列格式含竖线 ``|``。

    仅查表格环境（tabular/tabularx/longtable），不查数学 array（其 ``|`` 是合法列分隔符）。
    """
    hits: list[dict] = []
    # 1) 裸 \hline（三线表禁用；booktabs 用 \toprule/\midrule/\bottomrule 替代）
    for m in re.finditer(r"\\hline", text):
        line = text[:m.start()].count("\n") + 1
        hits.append({
            "line": line,
            "kind": "hline",
            "snippet": text.splitlines()[line - 1].strip()[:60],
        })
    # 2) 列格式里的竖线 |（tabular/tabularx/longtable 的 vertical rule）
    for m in re.finditer(r"\\begin\{(tabularx|tabular|longtable)\}", text):
        rest = text[m.end():]
        sm = re.match(r"(?:\{[^}]*\})?\{([^}]*)\}", rest)
        if sm and "|" in sm.group(1):
            line = text[:m.start()].count("\n") + 1
            hits.append({
                "line": line,
                "kind": "vrule",
                "snippet": m.group(0)[:60],
            })
    return hits


def scan_table_rules(text: str) -> list[dict]:
    r"""预检表格是否含 booktabs 顶/底线，返回每处 {line, kind, snippet}。

    - ``kind == "missing_rule"``：``tabular/tabularx/longtable`` 环境内缺
      ``\toprule`` 或 ``\bottomrule``（裸表格无规则线，非三线表，渲染成无框裸表）。

    scan_table_style 禁「坏的」（裸 \hline / 列格式竖线 |），本函数补「好的」——
    若表格环境内连顶/底线都没有，虽无 \hline 也不算三线表，须阻断，
    使门禁从「只禁坏的」升级为「要求好的」。与 scan_table_style 同属阻断级。
    """
    hits: list[dict] = []
    for m in re.finditer(
        r"\\begin\{(tabular|tabularx|longtable)\}(.*?)\\end\{\1\}", text, flags=re.DOTALL
    ):
        block = m.group(2)
        missing = []
        if "\\toprule" not in block:
            missing.append("\\toprule")
        if "\\bottomrule" not in block:
            missing.append("\\bottomrule")
        if missing:
            line = text[:m.start()].count("\n") + 1
            first = m.group(0).splitlines()[0] if m.group(0).splitlines() else ""
            hits.append({
                "line": line,
                "kind": "missing_rule",
                "snippet": first[:60],
            })
    return hits


def scan_caption_position(text: str) -> list[dict]:
    r"""预检表题/图题位置，返回每处 {line, kind, snippet}。

    - ``kind == "caption_table_below"``：``table`` 浮动体内 \caption 出现在
      tabular* 之后（应为表题在上）；
    - ``kind == "caption_figure_above"``：``figure`` 浮动体内 \caption 出现在
      图形（tikzpicture/includegraphics）之前（应为图题在下）。

    scan_table_style 只管表内规则线，不校验 \caption 相对位置；本函数补此缺口。
    覆盖 table* / figure* 星号变体。与 scan_table_style 同属阻断级。
    """
    hits: list[dict] = []
    # 同时覆盖 table/figure 的星号变体（table*/figure*）。
    float_re = re.compile(r"\\begin\{(table|figure)(\*?)\}(.*?)\\end\{\1\2\}", re.DOTALL)
    for fm in float_re.finditer(text):
        kind_env = fm.group(1)
        block = fm.group(3)
        base = text[:fm.start()].count("\n")
        cap_lines = [
            base + block[:mm.start()].count("\n") + 1
            for mm in re.finditer(r"\\caption\{", block)
        ]
        if kind_env == "table":
            tab_lines = [
                base + block[:mm.start()].count("\n") + 1
                for mm in re.finditer(
                    r"\\begin\{(tabular|tabularx|longtable)\}", block
                )
            ]
            # 表题在上：任意 \caption 出现在 tabular* 之后即违规（取最早 caption 判定）。
            if cap_lines and tab_lines and min(cap_lines) > min(tab_lines):
                hits.append({
                    "line": min(cap_lines),
                    "kind": "caption_table_below",
                    "snippet": _first_caption_snippet(block),
                })
        else:  # figure
            graphic_lines = [
                base + block[:mm.start()].count("\n") + 1
                for mm in re.finditer(r"\\begin\{tikzpicture\}|\\includegraphics", block)
            ]
            # 图题在下：任意 \caption 出现在图形之前即违规（取最早 caption 判定）。
            if cap_lines and graphic_lines and min(cap_lines) < max(graphic_lines):
                hits.append({
                    "line": min(cap_lines),
                    "kind": "caption_figure_above",
                    "snippet": _first_caption_snippet(block),
                })
    return hits


def _first_caption_snippet(block: str) -> str:
    """取 block 内首个 \\caption{...} 行作为 snippet（用于违规提示）。"""
    idx = block.find("\\caption{")
    if idx < 0:
        return ""
    return block[idx:].splitlines()[0][:60]


# ---- 排版样式门禁：伪代码 / 代码块 ----
# 代码/伪代码应使用共享 preamble 提供的 codeblock 环境（浅灰底 + 自动折行，
# 与正文明显区分）；裸 verbatim/lstlisting 不折行易溢出且无视觉样式。
_RAW_ENV_RE = re.compile(r"\\begin\{(verbatim|lstlisting)\}", flags=re.DOTALL)


def scan_raw_verbatim(text: str) -> list[dict]:
    r"""预检裸 verbatim / lstlisting（无样式），返回每处 {line, env, snippet}。

    伪代码/代码块应使用 codeblock 环境（共享 preamble 定义，浅灰底 + 自动折行）；
    裸 verbatim / lstlisting 不折行、无视觉区分，且等宽字体缺字风险更高。
    """
    hits: list[dict] = []
    for m in _RAW_ENV_RE.finditer(text):
        line = text[:m.start()].count("\n") + 1
        env = m.group(1)
        hits.append({
            "line": line,
            "env": env,
            "snippet": text.splitlines()[line - 1].strip()[:60],
        })
    return hits


# ---- 引用预检 ----
# 跨章 \ref 预检（warning 级，不阻断）：pdf-maker 红线规定跨章引用必须写成硬编码
# 纯文本「第~N 章」，禁用 \ref{...} 跨章引用（编译后指向错误编号）。但作者常常在单章
# 写作时顺手写 \ref{cha:c3} 指向前/后章，合并前 xref 才会抓到；本函数在单章 lint
# 阶段提前（边写边查）把「指向本文件未定义 \label 的 \ref」标出——这类 \ref 几乎
# 一定是跨章引用（同章前向/后向引用指向本文件内已定义的 \label，不会命中），提示作者
# 改为「第~N 章」硬编码文本。悬空 \ref（指向全书都不存在的 \label）也会被一并捕获。
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_REF_RE = re.compile(r"\\(?:ref|cref|autoref|eqref|pageref)\{([^}]+)\}")


def scan_crossref(text: str) -> list[dict]:
    r"""预检「引用指向本文件未定义的 \label」（极可能是跨章 \ref / 悬空引用）。

    返回每处 {line, kind, target, snippet}，warning 级（不阻断）。本文件内已定义的
    \label（含同章前向/后向引用）视为合法，不报警；仅当 \ref 目标不在本文件时报警。
    """
    local = set(_LABEL_RE.findall(text))
    hits: list[dict] = []
    for m in _REF_RE.finditer(text):
        target = m.group(1)
        if target in local:
            continue  # 同文件内引用（含前向/后向）合法
        line = text[:m.start()].count("\n") + 1
        hits.append({
            "line": line,
            "kind": "cross_ref",
            "target": target,
            "snippet": text.splitlines()[line - 1].strip()[:60],
        })
    return hits


# 悬空引用（正文 \cite 指向本文件未定义的 \bibitem）：编译期只报 "Citation undefined"
# （不会 Fatal，但正文出现「?」），且旧实现只在 balance 阶段（SOP 偏后）才拦截。
# 本函数在 check 阶段（xelatex 之前）即拦截，与样式门禁同级（阻断级），双保险。
_BIBITEM_RE = re.compile(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}")
# 匹配 \cite / \citep / \citet / \citeauthor / \nocite 等任意含 "cite" 的命令，
# 含可选 * 与 [..] 参数组，提取其强制大括号里的键（可逗号分隔多个）。
_CITE_RE = re.compile(r"\\(?:[A-Za-z]*cite[A-Za-z]*)\*?\s*(?:\[[^\]]*\])*\s*\{([^}]*)\}")
_VERBATIM_ENV_RE = re.compile(
    r"\\begin\{(verbatim|codeblock|lstlisting)\}.*?\\end\{\1\}", flags=re.DOTALL
)


def scan_cite_undef(text: str) -> list[dict]:
    r"""预检「正文 \cite 引用了本文件未定义的 \bibitem」（悬空引用）。

    返回每处 {line, kind, key, snippet}，阻断级（与样式门禁同级，check 阶段即拦截）。
    处理要点：
    - 剥离 LaTeX 注释，避免注释掉的 \cite 误报；
    - 剔除 verbatim / codeblock / lstlisting，代码块里的 \cite 是示例非真实引用；
    - 单文件内校验：用户每章自带 thebibliography，\cite 键必须存在本文件 \bibitem 中。
    """
    t = strip_latex_comments(text)
    t = _VERBATIM_ENV_RE.sub("", t)
    defined = set(_BIBITEM_RE.findall(t))
    hits: list[dict] = []
    for m in _CITE_RE.finditer(t):
        for k in (s.strip() for s in m.group(1).split(",") if s.strip()):
            if k in defined:
                continue
            line = t[:m.start()].count("\n") + 1
            hits.append({
                "line": line,
                "kind": "cite_undef",
                "key": k,
                "snippet": t.splitlines()[line - 1].strip()[:60],
            })
    return hits


# ---- 章节编号重复预检（warning 级，不阻断） ----
# ctexrep 的 \chapter / \section / \subsection 会自动生成「第 X 章」/「X.Y」/「X.Y.Z」
# 编号；若标题里再手写前导编号，会与自动编号叠加成「第 X 章 第 X 章」「X.Y X.Y …」的
# 重复编号。本函数在 check / lint 阶段（xelatex 之前）提前 warning，把渲染缺陷挡在编译之前。
# 仅查标题前导编号；* 变体（\chapter* 等）不带自动编号，手写前缀不重复，跳过。
_HEADING_RE = re.compile(r"\\(chapter|section|subsection)(\*?)\{([^{}]*)\}")
_CHAPTER_TITLE_PREFIX_RE = re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千]+\s*章\s*")
_SECTION_TITLE_PREFIX_RE = re.compile(r"^\s*[0-9]+\.[0-9]+(?:\.[0-9]+)?\s+")


def scan_redundant_heading_number(text: str) -> list[dict]:
    r"""预检章节标题里手写的前导编号（会与 ctexrep 自动编号叠加成重复编号）。

    - ``\chapter{第N章 ...}`` → 渲染「第 X 章 第 X 章 ...」（重复章号）；
    - ``\section{X.Y ...}`` / ``\subsection{...}`` → 渲染「X.Y X.Y ...」（重复节号）。

    返回每处 {line, level, kind, snippet}，warning 级（提醒作者删去手写前缀，
    自动编号由 ctexrep 负责）。``*`` 变体（\chapter* 等）不带编号，不检查。
    仅查标题前导编号，标题其余正文不报。
    """
    hits: list[dict] = []
    for m in _HEADING_RE.finditer(text):
        level, star, title = m.group(1), m.group(2), m.group(3)
        if star:
            continue  # 不带编号的 * 变体，手写前缀不重复
        line = text[:m.start()].count("\n") + 1
        if level == "chapter" and _CHAPTER_TITLE_PREFIX_RE.match(title):
            hits.append({
                "line": line, "level": level, "kind": "chapter_prefix",
                "snippet": title.strip()[:60],
            })
        elif level in ("section", "subsection") and _SECTION_TITLE_PREFIX_RE.match(title):
            hits.append({
                "line": line, "level": level, "kind": "section_prefix",
                "snippet": title.strip()[:60],
            })
    return hits


# ---- 整书合并（main.tex）预检 ----
def scan_missing_frontmatter(text: str) -> list[str]:
    r"""预检 main.tex 是否缺前置部分，返回缺失项的中文标签列表（空表示齐全）。

    判定：匹配 ``\chapter*{摘\quad 要}`` / ``\chapter*{序\quad 言}`` /
    ``\chapter*{术语表}``。其中**摘要为必选项**，序言/术语表为可选（模板注释明示
    「若不需要则整段删除」），build 侧据此区分 WARN 与 INFO。

    背景：整书合并 SOP 曾遗漏前置部分，导致成书无摘要/序言/术语表，而 build 全程
    不报错。本函数在 build 合并前非阻断提醒，避免静默出货一本没有前置部分的书。
    """
    expected = [
        ("摘要", r"\\chapter\*\{摘\\quad 要\}"),
        ("序言", r"\\chapter\*\{序\\quad 言\}"),
        ("术语表", r"\\chapter\*\{术语表\}"),
    ]
    missing = []
    for label, pat in expected:
        if not re.search(pat, text):
            missing.append(label)
    return missing


# 前置部分「正文结束」的边界标记：下一章节标题 / 目录 / \input / 文档结束。
_FRONTMATTER_BOUNDARY = re.compile(
    r"\\chapter\*?\{|\\tableofcontents|\\input\{|\\end\{document\}")

# 前置部分里不算「正文」的纯结构命令（模板默认就有，不代表作者写了内容）：
# \addcontentsline / \markboth / \thispagestyle / \newpage / \clearpage / \vspace 等。
_FRONTMATTER_STRUCTURE = re.compile(
    r"\\addcontentsline\{[^{}]*\}\{[^{}]*\}\{[^{}]*\}"
    r"|\\markboth\{[^{}]*\}\{[^{}]*\}"
    r"|\\thispagestyle\{[^{}]*\}"
    r"|\\pagenumbering\{[^{}]*\}"
    r"|\\vspace\*?\{[^{}]*\}"
    r"|\\(?:newpage|clearpage|cleardoublepage)\b")


def scan_empty_frontmatter(text: str) -> list[str]:
    r"""预检 main.tex 中「存在但正文为空」的前置部分，返回其中文标签列表（空表示无空壳）。

    判定：对每个已存在的前置部分标题（``\chapter*{摘\quad 要}`` 等），取其标题行之后
    到下一个章节标题 / ``\tableofcontents`` / ``\input`` / ``\end{document}`` 之间的
    文本，依次剥掉 LaTeX 注释、纯结构命令（``\\addcontentsline`` / ``\\newpage`` 等，
    模板默认就有、不代表作者写了内容）与空白后若一无所有，即视为「空壳前置页」。

    背景：模板在摘要/序言处只留 ``% 在此输入……`` 注释，作者忘记填写时，存在性预检
    （``scan_missing_frontmatter``）会绿灯放行，成书却带着两页空白（真实事故）。
    与存在性预检互补：那个管「有没有」，这个管「写了没」。
    """
    expected = [
        ("摘要", r"\\chapter\*\{摘\\quad 要\}"),
        ("序言", r"\\chapter\*\{序\\quad 言\}"),
        ("术语表", r"\\chapter\*\{术语表\}"),
    ]
    empty = []
    for label, pat in expected:
        m = re.search(pat, text)
        if not m:
            continue  # 整节缺失归 scan_missing_frontmatter 管，这里不重复报告
        body = text[m.end():]
        boundary = _FRONTMATTER_BOUNDARY.search(body)
        if boundary:
            body = body[:boundary.start()]
        body = strip_latex_comments(body)
        body = _FRONTMATTER_STRUCTURE.sub("", body)
        if not body.strip():
            empty.append(label)
    return empty


def scan_preamble_drift(main_text: str, shared_text: str) -> list[str]:
    r"""比较 main.tex 与 _preamble_shared.tex 的五段补丁标记，返回漂移项列表（空表示一致）。

    五段补丁各有不可混淆的特征标记，比较其在 main / shared 中是否同时存在：
    若某标记在两者间不一致（main 缺 / shared 缺），即视为漂移。

    背景：_preamble_shared.tex 是「中文 URL 支持 / 参考文献降级 / codeblock 环境 /
    表格字号 / 防溢出」五段补丁的唯一真源，单章模板 _tmp.tex 经 {{SHARED_PREAMBLE}}
    由 fix 内联；但整书模板 main.tex 可能是手写内联副本，若只改 _preamble_shared.tex
    而忘了同步 main.tex，两者会漂移（单章正常、整书却缺某补丁）。本函数在 build 合并前非阻断提醒。
    """
    markers = [
        ("中文 URL 支持", r"\\def\\Url@FormatString"),
        ("参考文献降级", r"\\patchcmd\{\\thebibliography\}\{\\chapter\*\{\\bibname\}\}"),
        ("codeblock 环境", r"\\newtcblisting\{codeblock\}"),
        ("表格字号", r"\\AtBeginEnvironment\{tabularx\}\{\\small\}"),
        ("防溢出", r"\\setlength\{\\emergencystretch\}"),
    ]
    drift = []
    for label, pat in markers:
        in_main = bool(re.search(pat, main_text))
        in_shared = bool(re.search(pat, shared_text))
        if in_main != in_shared:
            drift.append(label)
    return drift


# ---- tabularx 非 X 列「单列挤压」预警 ----
# 列格式 l/c/r 不换行：单元格内若含超长的不可断长串（典型为长 \texttt 标识符），
# 该列会被内容撑宽、把 X 列挤成窄条（真实事故：首列 30+ 字形标识符使 X 列只剩
# 窄条，整表失衡）。本扫描在 check/lint 阶段（编译前）预警：命中即建议改用
# >{\raggedright\arraybackslash}p{宽} 定宽换行列，或给长串加 \allowbreak。
_TABX_BEGIN_RE = re.compile(r"\\begin\{tabularx\}\{\\textwidth\}\{")


def _parse_colspec(spec: str) -> list[str]:
    """把 tabularx 列格式串解析为逐列类型列表（'X' / 'l' / 'c' / 'r' / 'p' / 其它忽略）。

    支持 ``>{...}`` 前缀修饰（其修饰的下一列照常登记，如 ``>{\\raggedright\\arraybackslash}X``
    仍为 X 列）；``p{...}`` 记为可换行的 p 列；竖线 ``|`` 与空格忽略。
    """
    cols: list[str] = []
    i = 0
    n = len(spec)
    while i < n:
        c = spec[i]
        if c == ">":
            # 跳过 >{...} 前缀（平衡的嵌套花括号）
            j = spec.find("{", i)
            if j == -1:
                break
            depth = 1
            k = j + 1
            while k < n and depth > 0:
                if spec[k] == "\\":
                    k += 2
                    continue
                if spec[k] == "{":
                    depth += 1
                elif spec[k] == "}":
                    depth -= 1
                k += 1
            i = k
            continue
        if c in "lcrX":
            cols.append(c)
            i += 1
            continue
        if c == "p":
            cols.append("p")
            i += 1
            continue
        if c in "{}":
            i += 1
            continue
        i += 1
    return cols


def _split_tabx_cells(row: str) -> list[str]:
    """按未转义的 & 切分表格行为单元格（\\& 不算分隔符）。"""
    cells: list[str] = []
    buf: list[str] = []
    i = 0
    while i < len(row):
        c = row[i]
        if c == "\\" and i + 1 < len(row):
            buf.append(row[i:i + 2])
            i += 2
            continue
        if c == "&":
            cells.append("".join(buf))
            buf = []
            i += 1
            continue
        buf.append(c)
        i += 1
    cells.append("".join(buf))
    return cells


def scan_squeezed_tables(text: str, threshold: int = 20) -> list[dict]:
    r"""预检 tabularx 非 X 列（l/c/r）内的超长不可断长串（单列挤压风险）。

    判定规则：
    - 解析每个 ``\begin{tabularx}{\textwidth}{...}`` 的列格式，定位 l/c/r 列；
    - 逐行（``\\`` 分隔）逐格（未转义 ``&`` 分隔）展开 ``\texttt`` 后取极大不可断段
      （空白、``-``、CJK/全角为断点，``\_`` 等转义对算 1 字形）；
    - 仅当段与 ``\texttt`` 内容相交且字形数 ≥ threshold 才上报（正文英文长词可走断词，
      不误报；p/X 列可换行，不在预警范围）。

    返回 [{line, col, letter, run, length}]（warning 级，不阻断；``threshold <= 0`` 返回空）。
    """
    if threshold <= 0:
        return []
    t = strip_latex_comments(text)
    t = _CODE_NONASCII_ENV_RE.sub(lambda m: _CODE_MASK_RE.sub(" ", m.group(0)), t)
    hits: list[dict] = []
    for bm in _TABX_BEGIN_RE.finditer(t):
        # 平衡解析列格式（内含 >{...} 嵌套花括号）
        j = bm.end()
        depth = 1
        while j < len(t) and depth > 0:
            if t[j] == "\\":
                j += 2
                continue
            if t[j] == "{":
                depth += 1
            elif t[j] == "}":
                depth -= 1
            j += 1
        if depth != 0:
            break
        colspec = t[bm.end():j - 1]
        end_m = re.compile(r"\\end\{tabularx\}").search(t, j)
        if not end_m:
            break
        body = t[j:end_m.start()]
        body_start_line = t.count("\n", 0, j) + 1
        cols = _parse_colspec(colspec)
        if not cols or "X" not in cols:
            continue  # 非 tabularx 标准用法（无 X 列可挤），跳过
        # 逐行扫描：行内命令（\toprule 等）先置空，坐标不漂移
        rows = re.split(r"\\\\", body)
        offset = 0
        for row in rows:
            row_start = offset
            offset += len(row) + 2
            cells = _split_tabx_cells(row)
            cell_pos = 0
            for ci, cell in enumerate(cells):
                cell_start = row_start + cell_pos
                cell_pos += len(cell) + 1
                if ci >= len(cols) or cols[ci] not in ("l", "c", "r"):
                    continue  # p/X 列可换行；仅不换行的 l/c/r 列有挤压风险
                # 先展开 \texttt（拿到内容区间），再把其余命令词等长置空——
                # 顺序不可颠倒（先置空会抹掉 \texttt 标记，spans 永远为空）。
                expanded, spans = _texttt_spans(cell)
                if not spans:
                    continue
                scan_cell = _LONGRUN_CMD_RE.sub(lambda m: " " * len(m.group(0)), expanded)
                for m in _LONGRUN_RE.finditer(scan_cell):
                    run = m.group(0)
                    if not any(s < m.end() and m.start() < e for s, e in spans):
                        continue
                    length = len(run) - run.count("\\")
                    if length < threshold:
                        continue
                    display = re.sub(r"\\(.)", r"\1", run)
                    hits.append({
                        "line": body_start_line + body.count("\n", 0, cell_start + m.start()),
                        "col": ci + 1,
                        "letter": cols[ci],
                        "run": display[:60],
                        "length": length,
                    })
    # 同行同列去重（同一单元格多个长串只报最长者），保持输出紧凑
    best: dict[tuple[int, int], dict] = {}
    for h in hits:
        key = (h["line"], h["col"])
        if key not in best or h["length"] > best[key]["length"]:
            best[key] = h
    return sorted(best.values(), key=lambda h: (h["line"], h["col"]))
