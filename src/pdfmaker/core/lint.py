# -*- coding: utf-8 -*-
"""编译前静态扫描：把「编译才报错」的坑挡在 xelatex 之前。

包含四类预检：
1. ``scan_glyphs``     —— CJK 字体缺字风险字符（≥ ≤ ≈ ≠ ①-⑩ 等）。
2. ``scan_truncated_urls`` —— 疑似被截断 / 含空白的残破 URL。
3. ``scan_tikz_badbreak``   —— TikZ 节点内 ``\\`` 换行但未声明 align= 的危险写法
                             （编译期会触发 missing \\item Fatal）。
4. ``scan_frontmatter_tables`` / ``inject_frontmatter_noindent`` —— 前置整宽表格
     缺 \\noindent 会触发恰好 21.9pt（=\\parindent）的 Overfull；扫描用于提醒，
     注入用于在合并副本中自动修复（源文件不变）。
"""

import re

from pdfmaker.core.text import strip_latex_comments

# CJK 字体（ctexrep 默认的系统中文字体）常缺的数学符号 / 带圈数字 / 希腊字母。
# 在正文（非 math mode）直接使用会触发 xelatex 的 "Missing character"，
# 表现为豆腐块 / 空白。预检后提醒作者改用 \\ge / \\le 等数学写法或纯文本编号。
# 注：→（右箭头，U+2192）在中文 CJK 字体中存在（中文文档编译零 Missing character），
# 纳入会大量误报，故不加入本集。
GLYPH_HAZARDS: dict[str, str] = {
    # 数学关系符号（旧集）
    "\u2265": r"$\ge$",   # ≥
    "\u2264": r"$\le$",   # ≤
    "\u2248": r"$\approx$",  # ≈
    "\u2260": r"$\ne$",   # ≠
    "\u223c": r"$\sim$",  # ∼
    # 带圈数字 ①-⑩
    "\u2460": "(1)", "\u2461": "(2)", "\u2462": "(3)", "\u2463": "(4)",
    "\u2464": "(5)", "\u2465": "(6)", "\u2466": "(7)", "\u2467": "(8)",
    "\u2468": "(9)", "\u2469": "(10)",  # ①-⑩
    # 新增：正文裸用同样缺字——数学模式内（正确写法）由 _mask_math 排除
    "\u00b1": r"$\pm$",            # ±
    "\u2103": r"$^\circ\mathrm{C}$",  # ℃
    "\u03b1": r"$\alpha$",        # α
    "\u03b2": r"$\beta$",         # β
    "\u03b3": r"$\gamma$",        # γ
    "\u03b4": r"$\delta$",        # δ
    "\u03b5": r"$\varepsilon$",   # ε
    "\u03b6": r"$\zeta$",         # ζ
    "\u03b7": r"$\eta$",          # η
    "\u03b8": r"$\theta$",        # θ
    "\u03bb": r"$\lambda$",       # λ
    "\u03bc": r"$\mu$",           # μ
    "\u03bd": r"$\nu$",           # ν
    "\u03be": r"$\xi$",           # ξ
    "\u03c0": r"$\pi$",           # π
    "\u03c1": r"$\rho$",          # ρ
    "\u03c3": r"$\sigma$",        # σ
    "\u03c4": r"$\tau$",          # τ
    "\u03c5": r"$\upsilon$",      # υ
    "\u03c6": r"$\phi$",          # φ
    "\u03c7": r"$\chi$",          # χ
    "\u03c8": r"$\psi$",          # ψ
    "\u03c9": r"$\omega$",        # ω
}


# 数学模式区域
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
_INLINE_MATH_RE = re.compile(
    r"(?<!\\)\$\$.*?\$\$"                              # $$ ... $$
    r"|(?<!\\)\$(?!\$)(?:\\.|[^$])*?(?<!\\)\$(?!\$)"   # $ ... $（非 $$）
    r"|\\\(.*?\\\)"                                     # \( ... \)
    r"|\\\[.*?\\\]",                                    # \[ ... \]
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

    - 仅扫描正文（非数学模式）区域：``$\\ge$`` 等数学写法是正确写法，不再误报。
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
    """预检疑似被截断 / 含空白的残破 URL。

    素材采集工具等常把长 URL 截断成 ``https://.../foo...``，这种链接
    无法验活、成书即死链。本函数静态找出：含 Unicode 省略号「…」、含 3 个及以上
    连续点（非 ``://`` 协议部分）、或含空白字符的 URL，返回其原文片段，提醒作者
    替换为素材里完整的 LIVE 链接。
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


def scan_tikz_badbreak(text: str) -> list[dict]:
    """预检 TikZ 节点内 `\\` 换行但未声明 align= 的危险写法（编译期 missing \\item Fatal）。

    写法示例：`\\node[...]{中心聚合\\\\服务器}` 在 `\\\\` 处触发 LaTeX "missing \\item" Fatal。
    返回每处 {line, snippet}，供 check_balance 作为阻断级提示，把编译错误挡在 xelatex 之前。

    仅扫描 tikzpicture 环境内的 \\node / node 文本大括号内容；会跳过 (...) 坐标组与
    [...] 选项组（含嵌套），只对「节点文本内的真实换行 `\\`」报警，且选项已含 align 的不报警。
    """
    hits: list[dict] = []
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
            # `\\` 换行但非命令/非 ( / [ / ] 跟随；选项缺 align → 危险
            bad_break = bool(re.search(r"\\\\(?![A-Za-z(\[\]])", node_text))
            # align 可能继承自 name/.style={...,align=...}（如 box/.style
            # ={...,align=center}）。同一 tikzpicture 内任意节点/styledef 含 align
            # 即视为已声明，避免「共享 style + 节点用 \\ 换行」被误报阻断。
            if bad_break and "align" not in opts and "align" not in block:
                line = text[:bstart].count("\n") + block[:nm.start()].count("\n") + 1
                hits.append({"line": line, "snippet": node_text[:60]})
    return hits


# 等宽字体（Latin Modern Mono）缺字风险环境：verbatim/codeblock/lstlisting。
# 这些环境内若含非 ASCII（希腊字母 σ/π、中文、全角符号），等宽字体无对应字形，
# 编译期触发 Missing character（特殊符号注释踩坑）。fix_glyphs 为保代码原样
# 会跳过 verbatim/codeblock，故只能靠本预检在 check/lint 阶段提前 warning。
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


def scan_tikz_amp(text: str) -> list[dict]:
    """预检 TikZ 节点文本内的未转义 &（编译期会触发 Missing $ inserted / 对齐符错误）。

    在 align=... 的节点里，`&` 被当作 tabular 列分隔符，直接编译报错（如残差块缩写
    ``Add & Norm`` 写成 ``Add & Norm``）。扫描 tikzpicture 内 \\node/\\Node 的文本大括号
    内容，找出未转义（非 \\& 前置）的 &，返回 {line, snippet}。
    仅查 \\node 文本，不查 \\matrix（其 & 是合法的单元格分隔符）。
    """
    hits: list[dict] = []
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
            # 未转义的 &（非 \& 前置）：节点文本里的 & 在 align 环境下是列分隔符，编译报错
            for idx in range(len(node_text)):
                if node_text[idx] == "&" and (idx == 0 or node_text[idx - 1] != "\\"):
                    line = (
                        text[:bstart].count("\n")
                        + block[:nm.start()].count("\n")
                        + node_text[:idx].count("\n")
                        + 1
                    )
                    snippet = node_text[max(0, idx - 15):idx + 15]
                    hits.append({"line": line, "snippet": snippet})
    return hits


# 章节入口标记：main.tex 中首个 \input{第...} 之前即「前置部分」（序言/摘要/术语表）。
_FRONTMATTER_INPUT_RE = re.compile(r"\\input\{第")


def scan_frontmatter_tables(text: str) -> list[int]:
    """预检 main.tex 前置部分的整宽表格（tabularx/tabular/table）是否缺 \\noindent。

    前置表格若紧跟空行（新段落带 \\parindent，11pt 下 2em≈21.9pt），会与整宽表格叠加，
    触发恰好 21.9pt 的 Overfull（这正是合并曾卡住的根因）。返回缺 \\noindent 的表格
    所在行号列表，供 build 合并前提醒并给出精准修复提示。

    判定：取每个前置表格所在「段落」（距其上最近空行之后的片段），若该片段不含
    \\noindent，则视为会在段落缩进下溢出。章节内部的表格不在此列（在章节 .tex 中，且
    单章编译由 check_overflow 兜底）。
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
    """在前置部分（首个 \\input{第...} 之前）给「顶格的流内整宽表格」
    （tabularx / tabular / longtable）自动补 \\noindent，消除「段落缩进 + 整宽表格」
    叠加导致的恰好 \\parindent 的 Overfull（合并时才暴露、白跑整书编译）。

    设计要点
    --------
    - **仅作用于 _build 副本**：由 build 在生成合并副本时调用，源 main.tex 不变。
    - **幂等**：表格上一非空行已是 \\noindent 则跳过（源已手写 \\noindent 时不会重复加）。
    - **仅前置部分**：章节内部表格不在此列（章节 .tex 内的表格由单章 check_overflow 兜底）。

    返回注入后的全文；原表格行不变，仅在缺失 \\noindent 的表格前插入一行 \\noindent。
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


# 三线表规范：学术中文书稿要求表格用 booktabs 的 \toprule/\midrule/\bottomrule，
# 严禁 \hline 与列格式里的竖线 |（vertical rule）。裸 \hline / 竖线会退化成
# 「网格表」，与规范确立的三线表范式冲突（早期章节曾退化，已回填）。
def scan_table_style(text: str) -> list[dict]:
    """预检非三线表的退化写法，返回每处 {line, kind, snippet}。

    - ``kind == "hline"``：出现裸 ``\\hline``（三线表应改用 ``\\toprule/\\midrule/\\bottomrule``）。
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


# 裸 verbatim / lstlisting（无样式）：代码/伪代码应使用共享 preamble 提供的
# codeblock 环境（浅灰底 + 自动折行，与正文明显区分）；裸 verbatim/lstlisting
# 不折行易溢出且无视觉样式。第 10–12 章曾退化为裸 verbatim，已回填为 codeblock。
_RAW_ENV_RE = re.compile(r"\\begin\{(verbatim|lstlisting)\}", flags=re.DOTALL)


def scan_raw_verbatim(text: str) -> list[dict]:
    """预检裸 verbatim / lstlisting（无样式），返回每处 {line, env, snippet}。

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


# 三线表「规则线齐全」预检：booktabs 要求表顶 \toprule、表尾 \bottomrule。
# scan_table_style 已禁「坏的」（裸 \hline / 列格式竖线 |），本函数补「好的」——
# 若表格环境内连顶/底线都没有（裸 tabular 无规则线），虽无 \hline 也不算三线表，
# 须阻断，使门禁从「只禁坏的」升级为「要求好的」。与 scan_table_style 同属阻断级。
def scan_table_rules(text: str) -> list[dict]:
    """预检表格是否含 booktabs 顶/底线，返回每处 {line, kind, snippet}。

    - ``kind == "missing_rule"``：``tabular/tabularx/longtable`` 环境内缺
      ``\\toprule`` 或 ``\\bottomrule``（裸表格无规则线，非三线表，渲染成无框裸表）。
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


# 表题在上 / 图题在下 预检：本工具强制规范（SKILL.md「强制排版规范」）。
# scan_table_style 只管表内规则线，不校验 \caption 相对位置；本函数补此缺口：
# table 内 \caption 须在 tabular* 之前（表题在上），figure 内 \caption 须在
# 图形（tikzpicture/includegraphics）之后（图题在下）。与 scan_table_style 同属阻断级。
def scan_caption_position(text: str) -> list[dict]:
    """预检表题/图题位置，返回每处 {line, kind, snippet}。

    - ``kind == "caption_table_below"``：``table`` 浮动体内 \\caption 出现在
      tabular* 之后（应为表题在上）。
    - ``kind == "caption_figure_above"``：``figure`` 浮动体内 \\caption 出现在
      图形（tikzpicture/includegraphics）之前（应为图题在下）。
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


# 跨章 \\ref 预检（warning 级，不阻断）：pdf-maker 红线规定跨章引用必须写成硬编码
# 纯文本「第~N 章」，禁用 \\ref{...} 跨章引用（编译后指向错误编号）。但作者常常在单章
# 写作时顺手写 \\ref{cha:c3} 指向前/后章，合并前 xref.py 才会抓到；本函数在单章 lint
# 阶段提前（边写边查）把「指向本文件未定义 \\label 的 \\ref」标出——这类 \\ref 几乎
# 一定是跨章引用（同章前向/后向引用指向本文件内已定义的 \\label，不会命中），提示作者
# 改为「第~N 章」硬编码文本。悬空 \\ref（指向全书都不存在的 \\label）也会被一并捕获。
_LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
_REF_RE = re.compile(r"\\(?:ref|cref|autoref|eqref|pageref)\{([^}]+)\}")


def scan_crossref(text: str) -> list[dict]:
    """预检「引用指向本文件未定义的 \\label」（极可能是跨章 \\ref / 悬空引用）。

    返回每处 {line, kind, target, snippet}，warning 级（不阻断）。本文件内已定义的
    \\label（含同章前向/后向引用）视为合法，不报警；仅当 \\ref 目标不在本文件时报警。
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
    """预检「正文 \\cite 引用了本文件未定义的 \\bibitem」（悬空引用）。

    返回每处 {line, kind, key, snippet}，阻断级（与样式门禁同级，check 阶段即拦截）。
    处理要点：
    - 剥离 LaTeX 注释，避免注释掉的 \\cite 误报；
    - 剔除 verbatim / codeblock / lstlisting，代码块里的 \\cite 是示例非真实引用；
    - 单文件内校验：用户每章自带 thebibliography，\\cite 键必须存在本文件 \\bibitem 中。
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


# 章节编号重复预检（warning 级，不阻断）：ctexrep 的 \chapter / \section / \subsection
# 会自动生成「第 X 章」/「X.Y」/「X.Y.Z」编号；若标题里再手写前导编号，会与自动编号
# 叠加成「第 X 章 第 X 章」「X.Y X.Y …」的重复编号（曾踩此坑）。本函数在
# check / lint 阶段（xelatex 之前）提前 warning，把渲染缺陷挡在编译之前。
# 仅查标题前导编号；* 变体（\chapter* 等）不带自动编号，手写前缀不重复，跳过。
_HEADING_RE = re.compile(r"\\(chapter|section|subsection)(\*?)\{([^{}]*)\}")
_CHAPTER_TITLE_PREFIX_RE = re.compile(r"^\s*第\s*[0-9零一二三四五六七八九十百千]+\s*章\s*")
_SECTION_TITLE_PREFIX_RE = re.compile(r"^\s*[0-9]+\.[0-9]+(?:\.[0-9]+)?\s+")


def scan_redundant_heading_number(text: str) -> list[dict]:
    """预检章节标题里手写的前导编号（会与 ctexrep 自动编号叠加成重复编号）。

    - ``\\chapter{第N章 ...}`` → 渲染「第 X 章 第 X 章 ...」（重复章号）。
    - ``\\section{X.Y ...}`` / ``\\subsection{...}`` → 渲染「X.Y X.Y ...」（重复节号）。

    返回每处 {line, level, kind, snippet}，warning 级（提醒作者删去手写前缀，
    自动编号由 ctexrep 负责）。``*`` 变体（\\chapter* 等）不带编号，不检查。
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


# 前置部分（摘要/序言/术语表）存在性预检：用户反馈整书合并 SOP
# 曾遗漏前置部分，导致成书无摘要/序言/术语表，而 build 全程不报错。本函数在 build
# 合并前非阻断提醒：若 main.tex 未声明这些 \\chapter* 块，提示作者补全，避免开源用户
# 静默出货一本没有前置部分的书。摘要为必选项；序言/术语表按模板注释为可选，仅作软提示。
def scan_missing_frontmatter(text: str) -> list[str]:
    """预检 main.tex 是否缺前置部分，返回缺失项的中文标签列表（空表示齐全）。

    判定：匹配 ``\\chapter*{摘\\quad 要}`` / ``\\chapter*{序\\quad 言}`` /
    ``\\chapter*{术语表}``。其中**摘要为必选项**，序言/术语表为可选（模板注释明示
    「若不需要则整段删除」），build 侧据此区分 WARN 与 INFO。
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


# 整书模板 main.tex 与共享补丁源 _preamble_shared.tex 漂移预检：
# _preamble_shared.tex 是「中文 URL 支持 / 参考文献降级 / codeblock 环境 / 防溢出」四段
# 补丁的唯一真源，单章模板 _tmp.tex 经 {{SHARED_PREAMBLE}} 由 fix.py 内联；但整书模板
# main.tex 目前是手写内联副本，若只改 _preamble_shared.tex 而忘了同步 main.tex，两者会
# 漂移（单章正常、整书却缺某补丁）。本函数在 build 合并前非阻断提醒。
def scan_preamble_drift(main_text: str, shared_text: str) -> list[str]:
    """比较 main.tex 与 _preamble_shared.tex 的四段补丁标记，返回漂移项列表（空表示一致）。

    四段补丁各有不可混淆的特征标记，比较其在 main / shared 中是否同时存在：
    若某标记在两者间不一致（main 缺 / shared 缺），即视为漂移。
    """
    markers = [
        ("中文 URL 支持", r"\\def\\Url@FormatString"),
        ("参考文献降级", r"\\patchcmd\{\\thebibliography\}\{\\chapter\*\{\\bibname\}\}"),
        ("codeblock 环境", r"\\newtcblisting\{codeblock\}"),
        ("防溢出", r"\\setlength\{\\emergencystretch\}"),
    ]
    drift = []
    for label, pat in markers:
        in_main = bool(re.search(pat, main_text))
        in_shared = bool(re.search(pat, shared_text))
        if in_main != in_shared:
            drift.append(label)
    return drift
