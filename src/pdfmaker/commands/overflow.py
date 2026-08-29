# -*- coding: utf-8 -*-
"""overflow —— xelatex 编译日志体检（体检之三，阻断级）。

编译完成后，解析 xelatex 生成的 .log，汇总「会让成品出问题的」信号，
作为单章 / 整书交付前的最后一道卡口。

检查项（阻断级：存在即非零退出）
---------------------------------
- Overfull \\hbox       ：段落 / 显示公式 / 节点文字溢出页面宽度。
- Missing character     ：字体缺失（豆腐块 / 空白）。
- multiply-defined      ：同一 \\label 跨章重名，导致 \\ref 指向错误编号。
- undefined references  ：引用断链（??）。
- LaTeX Error / Fatal   ：编译致命错误。

非阻断（仅提示）：Underfull \\hbox（松散度警告，不强制）。

发现 Overfull 时会打印前若干条所在行（含 at lines X--Y），便于直接定位源码；
并按溢出宽度给出常见根因与修复方向，减少排错时间。

退出码：0 阻断级信号全清；非 0 存在阻断级问题或找不到日志。
"""

import argparse
import re
import sys
from pathlib import Path

from pdfmaker.core.paths import setup_utf8

setup_utf8()

MAX_SHOWN = 8   # Overfull 明细最多打印几条


def _search_up(name: str) -> Path | None:
    """从 cwd 向上回溯（到盘符根），找名为 name 的日志文件。"""
    cur = Path.cwd()
    seen: set[Path] = set()
    for _ in range(12):
        cand = cur / name
        if cand.exists():
            return cand
        parent = cur.parent
        if parent == cur or parent in seen:
            break
        seen.add(parent)
        cur = parent
    return None


def find_log() -> Path | None:
    """在当前目录、脚本目录、脚本父目录，以及 cwd 祖先链中寻找常见日志文件名。"""
    here = Path(__file__).parent
    bases = [Path.cwd(), here, here.parent]
    cur = Path.cwd()
    for _ in range(12):
        cur = cur.parent
        if cur == cur.parent:
            break
        bases.append(cur)
    for cand in ("_tmp.log", "main.log", "book.log"):
        for base in bases:
            p = base / cand
            if p.exists():
                return p
    return None


# 代码/逐字环境：其长行不可断词，Overfull 硬阻断意义有限 → 降级为警告。
_CODE_ENV_RE = re.compile(
    r"\\begin\{(verbatim|codeblock|lstlisting)\}.*?\\end\{\1\}", re.DOTALL
)


def _codeblock_line_ranges(tex: str) -> "list[tuple[int, int]]":
    """返回 tex 中 verbatim/codeblock/lstlisting 环境的 (起,止) 行号区间（含边界，1-based）。"""
    ranges: list[tuple[int, int]] = []
    for m in _CODE_ENV_RE.finditer(tex):
        start = tex[:m.start()].count("\n") + 1
        end = tex[:m.end()].count("\n") + 1
        ranges.append((start, end))
    return ranges


# 显示公式环境：其长行超宽仅影响美观、不影响编译正确性 → 与代码块同待遇降级为警告。
# 原白名单只含 equation/align/gather/multline/flalign/alignat/displaymath/math，
# 漏掉了 array/matrix/pmatrix/bmatrix/vmatrix/Vmatrix/Bmatrix/cases/split/smallmatrix/
# aligned/gathered 等 AMS 数学环境——这些环境内公式超宽仍被硬阻断，与 align 内降级
# 行为不一致（某章 VMD 公式是 array 超宽，当时只能手动拆行绕过）。一并纳入降级白名单。
_MATH_ENV_RE = re.compile(
    r"\\begin\{(equation|equation\*|align|align\*|gather|gather\*|multline|multline\*|"
    r"flalign|flalign\*|alignat|alignat\*|displaymath|math|"
    r"array|matrix|matrix\*|pmatrix|pmatrix\*|bmatrix|bmatrix\*|vmatrix|vmatrix\*|"
    r"Vmatrix|Vmatrix\*|Bmatrix|Bmatrix\*|cases|split|smallmatrix|"
    r"aligned|aligned\*|gathered|gathered\*)\}.*?\\end\{\1\}",
    re.DOTALL,
)


def _math_env_line_ranges(tex: str) -> "list[tuple[int, int]]":
    """返回 tex 中显示公式环境的 (起,止) 行号区间（含边界，1-based）。"""
    ranges: list[tuple[int, int]] = []
    for m in _MATH_ENV_RE.finditer(tex):
        start = tex[:m.start()].count("\n") + 1
        end = tex[:m.end()].count("\n") + 1
        ranges.append((start, end))
    return ranges


def _collect_source_texts(log_path: "Path") -> "list[Path]":
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
    if not cands:  # 平铺未命中（如子目录布局）则递归一层兜底
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
    # 避免把 vbox 误算进「Overfull \hbox」总数（旧实现用 (?:hbox|vbox) 合并计数，标签误导）。
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
    for _st in _collect_source_texts(log):
        try:
            _t = _st.read_text(encoding="utf-8", errors="ignore")
            code_ranges += _codeblock_line_ranges(_t)
            math_ranges += _math_env_line_ranges(_t)
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
        print("\n前几条 Overfull 位置（去重）：")
        seen: set[str] = set()
        for line in re.findall(r"^Overfull.*$", txt, flags=re.MULTILINE):
            snippet = line.strip()
            key = snippet[:60]
            if key in seen:
                continue
            seen.add(key)
            print(f"  - {snippet[:140]}")
            if len(seen) >= MAX_SHOWN:
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
              "（已由 balance 步骤 9 预检拦截，见上方阻断项）。")
        print("  • 前置部分（序言/术语表）整宽表格：合并前 build 会专门预检 \\noindent。")

    blocking = bool(overfull or missing or multidef or undefref or fatal)
    if blocking:
        print("\n[FAIL] 存在阻断级问题，必须先修源码再交付。")
        return 1
    print("\n[OK] 阻断级信号全清（Underfull 若过多可顺手优化，不阻断）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
