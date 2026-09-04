# -*- coding: utf-8 -*-
r"""overflow —— xelatex 编译日志体检（体检之三，阻断级）。

编译完成后，解析 xelatex 生成的 .log，汇总「会让成品出问题的」信号，
作为单章 / 整书交付前的最后一道卡口。

检查项（阻断级：存在即非零退出）
--------------------------------
- Overfull \hbox        ：段落 / 显示公式 / 节点文字溢出页面宽度。
- Missing character     ：字体缺失（豆腐块 / 空白）。
- multiply-defined      ：同一 \label 跨章重名，导致 \ref 指向错误编号。
- undefined references  ：引用断链（??）。
- LaTeX Error / Fatal   ：编译致命错误。

降级与豁免
----------
- 代码/逐字环境（verbatim/codeblock/lstlisting）与显示公式环境内的 Overfull
  不可断词、超宽仅影响美观 → 降级为警告（仍打印，不计入阻断）。
- Overfull \vbox（高度溢出）与 Underfull \hbox/vbox（松散度警告）仅提示，不阻断。

发现 Overfull 时会打印前若干条所在行（含 at lines X--Y），便于直接定位源码；
并按溢出宽度给出常见根因与修复方向，减少排错时间。

源行号映射
----------
日志里的 ``at lines A--B`` 指向的是**归一化副本**（chN.tex / _build/第N章.tex）的行号，
不是作者编辑的源文件（第N章/第N章.tex）。本命令对每条阻断级 Overfull 做三级
best-effort 源定位：
1. **内容锚定**：从日志的 hbox 上下文提取长标识符，回源文件精确匹配（允许 ``\_`` 变体）；
2. **行号对齐**：用 difflib 对齐作者源与归一化副本的行序列，吸收 normalize 增行漂移；
3. **原样回退**：无法映射时保留日志行号并明确标注「归一化副本行号」。
若定位落入表格（tabularx/table）内部，还会列出该表中含超长不可断长串的候选行
（复用 core.lint.scan_squeezed_tables），直接指出「哪一格」而非只指到 \end{tabularx}。

退出码
------
0 阻断级信号全清；1 存在阻断级问题；找不到日志时 SystemExit。
"""

import argparse
import difflib
import re
import sys
from pathlib import Path

from pdfmaker.core.lint import scan_squeezed_tables
from pdfmaker.core.paths import setup_utf8

setup_utf8()

MAX_SHOWN = 8   # Overfull 明细最多打印几条
LOG_NAMES = ("_tmp.log", "main.log", "book.log")  # 自动寻找时的候选日志文件名


def _search_up(name: str) -> Path | None:
    """从 CWD 沿祖先链向上回溯，找名为 name 的日志文件。"""
    for base in [Path.cwd(), *Path.cwd().parents]:
        cand = base / name
        if cand.exists():
            return cand
    return None


def find_log() -> Path | None:
    """在 CWD、脚本目录及其父目录、CWD 祖先链中寻找常见日志文件名。"""
    here = Path(__file__).parent
    bases = [Path.cwd(), here, here.parent, *Path.cwd().parents]
    for cand in LOG_NAMES:
        for base in bases:
            p = base / cand
            if p.exists():
                return p
    return None


# 代码/逐字环境：其长行不可断词，Overfull 硬阻断意义有限 → 降级为警告。
_CODE_ENV_RE = re.compile(
    r"\\begin\{(verbatim|codeblock|lstlisting)\}.*?\\end\{\1\}", re.DOTALL
)


def _codeblock_line_ranges(tex: str) -> list[tuple[int, int]]:
    """返回 tex 中 verbatim/codeblock/lstlisting 环境的 (起, 止) 行号区间（含边界，1-based）。"""
    ranges: list[tuple[int, int]] = []
    for m in _CODE_ENV_RE.finditer(tex):
        start = tex[:m.start()].count("\n") + 1
        end = tex[:m.end()].count("\n") + 1
        ranges.append((start, end))
    return ranges


# 显示公式环境：其长行超宽仅影响美观、不影响编译正确性 → 与代码块同待遇降级为警告。
# 白名单覆盖 AMS 数学环境全家桶（equation/align/gather/multline/flalign/alignat/
# displaymath/math 及 array/matrix/pmatrix/bmatrix/vmatrix/Vmatrix/Bmatrix/cases/
# split/smallmatrix/aligned/gathered），避免「align 内降级、array 内却硬阻断」的不一致。
_MATH_ENV_RE = re.compile(
    r"\\begin\{(equation|equation\*|align|align\*|gather|gather\*|multline|multline\*|"
    r"flalign|flalign\*|alignat|alignat\*|displaymath|math|"
    r"array|matrix|matrix\*|pmatrix|pmatrix\*|bmatrix|bmatrix\*|vmatrix|vmatrix\*|"
    r"Vmatrix|Vmatrix\*|Bmatrix|Bmatrix\*|cases|split|smallmatrix|"
    r"aligned|aligned\*|gathered|gathered\*)\}.*?\\end\{\1\}",
    re.DOTALL,
)


def _math_env_line_ranges(tex: str) -> list[tuple[int, int]]:
    """返回 tex 中显示公式环境的 (起, 止) 行号区间（含边界，1-based）。"""
    ranges: list[tuple[int, int]] = []
    for m in _MATH_ENV_RE.finditer(tex):
        start = tex[:m.start()].count("\n") + 1
        end = tex[:m.end()].count("\n") + 1
        ranges.append((start, end))
    return ranges


def _collect_source_texts(log_path: Path) -> list[Path]:
    """收集日志同目录（含子目录兜底）下全部章节 / 附录源码 .tex，供 Overfull 降级统一判定。

    - 单章 SOP 以 cwd=章目录编译 ``_tmp.tex``（其 ``\\input`` 该章的 ``chN.tex``），章目录含
      ``chN.tex`` / ``第N章.tex``；日志行号（at lines A--B）对章节内容指向被 ``\\input`` 的
      源码行号。
    - 整书合并（build）把各章 ``\\input`` 的 ``.tex`` 平铺进 ``_build/``，``main.log`` 的
      同级目录含**所有**章的源码。

    跳过 ``_tmp.tex`` / ``main.tex`` 等编排入口（其 ``\\input`` 真实章节，区间无意义）。
    """
    d = log_path.parent.resolve()
    pats = ("ch*.tex", "第*章.tex", "附录*.tex")
    cands: list[Path] = []
    for p in pats:
        cands.extend(sorted(d.glob(p)))
    if not cands:  # 平铺未命中（如子目录兜底）则递归一层兜底
        for p in pats:
            cands.extend(sorted(d.rglob(p)))
    seen: set[Path] = set()
    out: list[Path] = []
    for c in cands:
        rc = c.resolve()
        if rc in seen:
            continue
        seen.add(rc)
        if c.name in ("_tmp.tex", "main.tex"):
            continue
        out.append(c)
    return out


# ---- Overfull 源行号映射（归一化副本行号 → 作者源文件行号） ----
# 日志的 at lines A--B 指向 chN.tex / _build/第N章.tex（归一化副本），不是作者编辑的
# 第N章/第N章.tex。以下三级 best-effort 定位：内容锚定（精确）→ difflib 行对齐
# （结构化）→ 原样回退（标注「归一化副本行号」）。
_TEX_TOKEN_RE = re.compile(r"\((?:\./)?([^\s()]+\.tex)")


def _current_tex_guess(txt: str, pos: int) -> str | None:
    """返回日志位置 pos 之前**最近打开的** .tex 文件（启发式）。

    LaTeX 用圆括号跟踪文件开关，但日志消息（含 Overfull 行自身）也大量出现括号，
    精确维护弹栈不可靠；而实践中章节文件打开后其内容才被处理——「最近打开者」
    在单章与整书两种布局下都是足够好的猜测。失败返回 None 时由
    内容锚定在所有候选源文件里兜底（不依赖本函数）。
    """
    last: str | None = None
    for m in _TEX_TOKEN_RE.finditer(txt, 0, pos):
        last = m.group(1)
    return last


def _candidate_originals(log: Path) -> list[Path]:
    """收集可能的作者源文件：单章布局（同目录 第N章.tex）与整书布局（项目根章目录）。"""
    d = log.parent.resolve()
    out: list[Path] = []
    seen: set[Path] = set()
    for c in (sorted(d.glob("第*章.tex"))
              + sorted(d.glob("附录*.tex"))
              + sorted(d.parent.glob("第*章/第*章.tex"))
              + sorted(d.parent.glob("附录*/附录*.tex"))):
        rc = c.resolve()
        if rc in seen:
            continue
        seen.add(rc)
        out.append(c)
    return out


def _resolve_pair(log: Path, open_file: str | None) -> tuple[Path, Path] | None:
    """把日志打开文件解析为（归一化副本, 作者源文件）对；无法解析返回 None。"""
    if not open_file:
        return None
    d = log.parent.resolve()
    name = Path(open_file).name
    m = re.fullmatch(r"ch(\d+)\.tex", name)
    if m:  # 单章布局：chN.tex → 同目录 第N章.tex
        orig = d / f"第{m.group(1)}章.tex"
        return (d / name, orig) if orig.exists() else None
    if (name.startswith("第") or name.startswith("附录")) and name.endswith(".tex"):
        orig = d.parent / name[:-4] / name  # _build 归一副本 → 项目根章目录原件
        if orig.exists():
            return (d / name, orig)
    return None


def _anchor_tokens(context: str) -> list[str]:
    """从日志 hbox 上下文提取候选锚点标识符（长者优先，最多 4 个）。"""
    ctx = re.sub(r"\\TU/\S*", " ", context)  # 字体标记（\TU/lmtt/m/n/10.95 等）
    toks = re.findall(r"[A-Za-z][A-Za-z0-9_.]{7,}", ctx)
    seen: list[str] = []
    for t in toks:
        if t not in seen:
            seen.append(t)
    return sorted(seen, key=len, reverse=True)[:4]


def _find_anchor(text: str, token: str) -> int | None:
    """在源文本中精确匹配锚点（允许 \\_ 变体），命中返回 1-based 行号。"""
    pat = re.compile(re.escape(token).replace("_", r"\\?_"))
    m = pat.search(text)
    if not m:
        return None
    return text.count("\n", 0, m.start()) + 1


def _build_line_map(orig_text: str, norm_text: str):
    """用 difflib 对齐作者源与归一化副本的行序列，返回 chN 行号 → 源行号 的映射函数。

    归一化（normalize_text）以「行内改写 + 少量增行」为主，difflib 的匹配块
    能精确吸收 wrap_tikz 等造成的行数漂移，比「按注入数折算」稳健。
    """
    sm = difflib.SequenceMatcher(
        None, orig_text.split("\n"), norm_text.split("\n"), autojunk=False
    )
    blocks = sm.get_matching_blocks()

    def to_orig(ch_line1: int) -> int:
        i = ch_line1 - 1
        best = None
        for blk in blocks:
            if blk.b <= i < blk.b + blk.size:
                return blk.a + (i - blk.b) + 1
            if blk.b + blk.size <= i:
                best = blk
        if best is not None:
            return best.a + best.size  # 落在非匹配区：钳到上一匹配块末尾
        return 1

    return to_orig


def _table_hints(orig_text: str, src_line: int) -> list[dict]:
    """若源行落入 tabularx 内，返回该表中含超长不可断长串的候选单元格（行号为全文行号）。"""
    lines = orig_text.split("\n")
    idx = src_line - 1
    if idx < 0 or idx >= len(lines):
        return []
    # 后向寻找 \begin{tabularx}：跳过 \end{tabularx}/\end{table} 边界行（表格
    # Overfull 的日志行号常落在这些边界上）；撞到 \begin{table} 或章节标题
    # 则说明该位置在表格之外。
    begin = None
    for i in range(idx, -1, -1):
        if r"\begin{tabularx}" in lines[i]:
            begin = i
            break
        if r"\end{tabularx}" in lines[i] or r"\end{table}" in lines[i]:
            continue
        if r"\begin{table}" in lines[i] or "\\section" in lines[i] or "\\chapter" in lines[i]:
            return []  # 在表格之外
    if begin is None:
        return []
    end = None
    for i in range(begin + 1, len(lines)):
        if r"\end{tabularx}" in lines[i]:
            end = i
            break
    if end is None:
        return []
    block = "\n".join(lines[begin:end + 1])
    hits = scan_squeezed_tables(block, threshold=20)
    for h in hits:
        h["line"] += begin  # block 内 1-based → 全文 1-based
    return hits[:3]


def _locate_overfull(log: Path, txt: str, a: int, pos: int,
                     _pair_cache: dict, _text_cache: dict) -> dict | None:
    """对一条阻断级 Overfull 做源定位，返回 {file, line, method, content, hints} 或 None。"""
    open_file = _current_tex_guess(txt, pos)
    # 锚点上下文从 Overfull 行的**下一行**开始（本行的 Overfull/paragraph/lines
    # 等日志词汇会成为噪声锚点），取后续 hbox 排版内容。
    ctx_start = txt.find("\n", pos)
    context = txt[ctx_start:ctx_start + 600] if ctx_start != -1 else ""
    tokens = _anchor_tokens(context)
    candidates = _candidate_originals(log)

    def _read(p: Path) -> str:
        if p not in _text_cache:
            try:
                _text_cache[p] = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                _text_cache[p] = ""
        return _text_cache[p]

    # 第一级：内容锚定（在所有候选源文件中精确匹配，不依赖 paren 栈的正确性）
    for token in tokens:
        for cand in candidates:
            hit = _find_anchor(_read(cand), token)
            if hit:
                return {
                    "file": cand.name, "line": hit, "method": "内容锚定",
                    "content": _read(cand).split("\n")[hit - 1].strip()[:100],
                    "hints": _table_hints(_read(cand), hit),
                }
    # 第二级：difflib 行对齐（需要解析出 归一化副本→作者源 的配对）
    pair = _resolve_pair(log, open_file)
    if pair is not None:
        norm, orig = pair
        if pair not in _pair_cache:
            _pair_cache[pair] = _build_line_map(_read(orig), _read(norm))
        src_line = _pair_cache[pair](a)
        lines = _read(orig).split("\n")
        content = lines[src_line - 1].strip()[:100] if 0 < src_line <= len(lines) else ""
        return {
            "file": orig.name, "line": src_line, "method": "行号对齐",
            "content": content, "hints": _table_hints(_read(orig), src_line),
        }
    return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker overflow",
        description="xelatex 编译日志体检（Overfull / 缺失字符 / 重复 label / 断链 / Fatal）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker overflow _tmp.log   # 单章日志\n"
            "  python -m pdfmaker overflow main.log    # 整书日志\n"
            "  python -m pdfmaker overflow             # 自动寻找 _tmp.log / main.log"
        ),
    )
    parser.add_argument("log", nargs="?", help="编译日志路径（省略则自动寻找）")
    args = parser.parse_args(argv)

    if args.log:
        log = Path(args.log)
        if not log.is_absolute():
            log = Path.cwd() / log
        if not log.exists():
            # 显式路径找不到 → 向上回溯找同名日志 / 常规 find_log（不向下 rglob，避免跨项目误匹配）
            alt = _search_up(Path(args.log).name) or find_log()
            if alt:
                log = alt
    else:
        log = find_log()
    if log is None or not log.exists():
        raise SystemExit(
            "[overflow] 找不到日志文件。请显式传入路径"
            "（如 python -m pdfmaker overflow _tmp.log），或先完成一次编译。"
        )

    txt = log.read_text(encoding="utf-8", errors="ignore")

    # hbox（too wide，宽度溢出，可能阻断）与 vbox（too high，高度溢出，仅警告）分别计数，
    # 避免把 vbox 误算进「Overfull \hbox」总数。
    overfull_hbox_count = len(re.findall(r"Overfull \\hbox", txt))
    overfull_vbox_count = len(re.findall(r"Overfull \\vbox", txt))
    # 提取每条 Overfull \hbox（too wide）的源码行区间（at lines A--B / at line A），用于代码块降级判定。
    overfull_lines = [
        (int(a), int(b) if b else int(a))
        for a, b in re.findall(
            r"Overfull \\hbox\s*\([\d.]+pt too wide\).*?at lines? (\d+)(?:--(\d+))?",
            txt,
        )
    ]
    # vbox（too high）位置仅作提示，不阻断（多因浮动体/图表略高于页，LaTeX 已自动分页）。
    vbox_lines = [
        (int(a), int(b) if b else int(a))
        for a, b in re.findall(
            r"Overfull \\vbox\s*\([\d.]+pt too high\).*?at lines? (\d+)(?:--(\d+))?",
            txt,
        )
    ]
    # verbatim/codeblock/lstlisting 与显示公式环境内的 Overfull 不可断词/
    # 超宽仅影响美观、不影响编译正确性 → 降级为警告（仍打印，但不计入阻断）。
    code_ranges: list[tuple[int, int]] = []
    math_ranges: list[tuple[int, int]] = []
    for src_path in _collect_source_texts(log):
        try:
            src_text = src_path.read_text(encoding="utf-8", errors="ignore")
            code_ranges += _codeblock_line_ranges(src_text)
            math_ranges += _math_env_line_ranges(src_text)
        except Exception:
            continue
    overfull_code: list[tuple[int, int]] = []
    overfull_math: list[tuple[int, int]] = []
    overfull_block: list[tuple[int, int]] = []
    for (a, b) in overfull_lines:
        if code_ranges and any(s <= a and b <= e for (s, e) in code_ranges):
            overfull_code.append((a, b))
        elif math_ranges and any(s <= a and b <= e for (s, e) in math_ranges):
            overfull_math.append((a, b))
        else:
            overfull_block.append((a, b))
    overfull = overfull_block  # 下游阻断判定（不含降级项）
    missing = re.findall(r"Missing character", txt)
    multidef = re.findall(r"multiply-defined", txt)
    undefref = re.findall(r"(?:undefined references?|Reference .* undefined)", txt)
    fatal = re.findall(r"(?:Fatal error|Emergency stop|LaTeX Error)", txt)
    underfull_hbox = re.findall(r"Underfull \\hbox", txt)
    underfull_vbox = re.findall(r"Underfull \\vbox", txt)
    underfull = underfull_hbox + underfull_vbox

    print(f"日志：{log}")
    downgraded = len(overfull_code) + len(overfull_math)
    code_note = ""
    if downgraded:
        parts = []
        if overfull_code:
            parts.append(f"降级(代码块){len(overfull_code)}")
        if overfull_math:
            parts.append(f"降级(公式){len(overfull_math)}")
        code_note = "，" + " + ".join(parts)
    print(f"  Overfull \\hbox        : 总 {overfull_hbox_count}，阻断 {len(overfull_block)}{code_note}"
          f"  {'<-- 阻断' if overfull_block else '(OK)'}")
    print(f"  Overfull \\vbox        : 总 {overfull_vbox_count}（高度溢出，仅警告不阻断）")
    print(f"  Missing character     : {len(missing)}  {'<-- 阻断' if missing else '(OK)'}")
    print(f"  multiply-defined label: {len(multidef)}  {'<-- 阻断' if multidef else '(OK)'}")
    print(f"  undefined references  : {len(undefref)}  {'<-- 阻断' if undefref else '(OK)'}")
    print(f"  Fatal/Error           : {len(fatal)}  {'<-- 阻断' if fatal else '(OK)'}")
    print(f"  Underfull \\hbox/vbox  : 总 {len(underfull)}"
          f"（hbox {len(underfull_hbox)} / vbox {len(underfull_vbox)}），仅警告不阻断")

    if overfull:
        # 逐行抓取：LaTeX 会把 "Overfull \hbox (Xpt too wide) in paragraph at lines A--B"
        # 打在同一行，这一行本身就含定位信息，直接展示即可。
        # 对每条阻断级 Overfull 附「源文件行号」定位（内容锚定 / 行号对齐），
        # 落入表格时再列出含超长不可断长串的候选单元格——直接指出「哪一格」。
        print("\n前几条 Overfull 位置（去重，附源文件定位）：")
        seen: set[str] = set()
        shown = 0
        _pair_cache: dict = {}
        _text_cache: dict = {}
        for m in re.finditer(r"^Overfull \\hbox[^\n]*$", txt, flags=re.MULTILINE):
            snippet = m.group(0).strip()
            key = snippet[:60]
            if key in seen:
                continue
            seen.add(key)
            print(f"  - {snippet[:140]}")
            lm = re.search(r"at lines? (\d+)(?:--(\d+))?", snippet)
            if lm:
                loc = _locate_overfull(log, txt, int(lm.group(1)), m.start(),
                                       _pair_cache, _text_cache)
                if loc:
                    print(f"      → 源定位：{loc['file']} 行 {loc['line']}（{loc['method']}）")
                    if loc["content"]:
                        print(f"      内容：{loc['content']}")
                    for h in loc["hints"]:
                        print(f"      表格候选：行 {h['line']}（第 {h['col']} 列）"
                              f" {h['run']}（{h['length']} 字形）")
                else:
                    print("      → 源定位：未能映射（上方行号为归一化副本 chN/_build 行号）")
            shown += 1
            if shown >= MAX_SHOWN:
                break
        if not seen:
            print("  （日志中未能提取到明细行，请直接搜索日志里的 Overfull）")
        if overfull_code:
            print(f"  （其中 {len(overfull_code)} 条位于 verbatim/codeblock/lstlisting 内，"
                  f"不可断词，已降级为警告：行 {overfull_code}）")
        if overfull_math:
            print(f"  （其中 {len(overfull_math)} 条位于显示公式环境内，超宽仅影响美观、不影响编译，"
                  f"已降级为警告：行 {overfull_math}）")

    if vbox_lines:
        print(f"\n[提示] 存在 {len(vbox_lines)} 条 Overfull \\vbox（高度溢出，不阻断）："
              f"多为浮动体 / 图表略高于页高，LaTeX 已自动分页；若想消除，可在对应 figure 加 "
              f"[t]/[b] 放置项或适当缩小图高（行区间：{vbox_lines}）。")

    if missing:
        chars = sorted(set(re.findall(r"Missing character: There is no (\S+)", txt)))
        if chars:
            print(f"\n缺失字符（去重，前 20 个）：{' '.join(chars[:20])}")

    # ---- Overfull 根因提示（按溢出宽度给修复方向，减少排错时间） ----
    if overfull:
        widths = [float(w) for w in re.findall(r"\(([\d.]+)pt too wide\)", txt) if w]
        print("\n[排查建议] 常见 Overfull 根因与修复：")
        if widths and any(10 <= w <= 35 for w in widths):
            print("  • 溢出≈段落缩进 \\parindent（11pt 下 2em≈21.9pt）：极可能是「紧跟空行的整宽"
                  "表格/tabularx」被段落缩进推宽。在 \\begin{tabularx/tabular/table} 前加 \\noindent。")
        if widths and max(widths) > 35:
            print("  • 溢出较大(>35pt)：存在不可断词长串或双栏过窄。缩短该行内容 / 改用 p{宽度} 列"
                  " / 缩小字号 / 拆词。")
        print("  • TikZ 节点内 `\\\\` 无 align= 会触发 missing \\item Fatal"
              "（已由 balance 步骤 10 预检拦截，见上方阻断项）。")
        print("  • 前置部分（序言/术语表）整宽表格：合并前 build 会专门预检 \\noindent。")

    blocking = bool(overfull or missing or multidef or undefref or fatal)
    if blocking:
        print("\n[FAIL] 存在阻断级问题，必须先修源码再交付。")
        return 1
    print("\n[OK] 阻断级信号全清（Underfull 若过多可顺手优化，不阻断）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
