# -*- coding: utf-8 -*-
"""check —— 章节内容结构统计（体检之一）。

对单个章节源文件做轻量静态统计分析，帮助判断「这一章写得够不够、结构是否完整」。

检查项
------
- 中文字数（去除表格 / 图 / verbatim / verb 块后的正文）。
- TeX 字节数。
- 章节层级计数：chapter / section / subsection / subsubsection。
- 元素计数：tikz 图、table、verbatim、multirow、bibitem、链接（url + href）。
- 编译前风险预检（warning 级，不阻断）：扫描「CJK 字体缺字」风险字符
  （≥ ≤ ≈ ≠ ①-⑩ 等）与疑似被截断的残破 URL，把 xelatex 的 Missing character /
  验活失败挡在编译之前。
- 排版样式门禁（阻断级）：三线表须用 booktabs 规则（禁用裸 ``\\hline`` 与列格式竖线
  ``|``，**且必须含** ``\\toprule``/``\\bottomrule`` 顶底线，裸表格无规则线也阻断），
  伪代码/代码块须用共享 preamble 的 ``codeblock`` 环境（禁用裸 ``verbatim`` /
  ``lstlisting``），且 **表题须在上、图题须在下**（caption 位置错位也阻断）。退化/不规范
  写法直接 exit 1 阻断，防止后续章节回归（第 10–12 章曾退化，已回填；已强化规则线
  齐全与 caption 位置）。
- 字数硬门禁：正文字数低于 ``--min-chars``（默认 ``CHAPTER_MIN_CHARS``）时 exit 1 阻断；
  附录 / 短章可用 ``--no-gate`` 放行。

退出码：0 达标 / 1 排版样式违规 或 字数低于硬门禁下限（或源文件缺失）。
"""

import argparse
import re
import sys

from pdfmaker.core import (
    char_count,
    chinese_count,
    count_visible_body,
    resolve_source,
    scan_codeblock_nonascii,
    scan_cite_undef,
    scan_crossref,
    scan_glyphs,
    scan_raw_verbatim,
    scan_table_style,
    scan_table_rules,
    scan_caption_position,
    scan_tikz_amp,
    scan_truncated_urls,
    scan_redundant_heading_number,
    setup_utf8,
    strip_latex_comments,
    strip_nonbody,
)
import pdfmaker.core.config as cfg

setup_utf8()


def evaluate_gate(count: int, min_chars: int, max_chars: int = 0,
                  no_gate: bool = False) -> tuple[bool, str]:
    """字数硬门禁判定，返回 (passed, message)。

    - no_gate=True：仅统计不阻断，永远 passed。
    - count < min_chars：未通过（过短），main 应 exit 1。
    - max_chars > 0 且 count > max_chars：未通过（过长），main 应 exit 1。
    - 否则通过。max_chars=0 表示不限制上限（延续「字数/引用不设上限」的宽松哲学）。
    抽成纯函数便于复用，避免依赖文件系统。
    """
    if no_gate:
        return True, "字数门禁已关闭（--no-gate）：仅统计，不阻断。"
    if count < min_chars:
        return False, f"字数不足：{count} < 下限 {min_chars}"
    if max_chars > 0 and count > max_chars:
        return False, f"字数超长：{count} > 上限 {max_chars}"
    return True, f"字数达标：{min_chars} <= {count}" + (f" <= {max_chars}" if max_chars > 0 else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker check",
        description="章节内容结构统计（字数 / 层级 / 元素）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker check 4       # 统计第 4 章\n"
            "  python -m pdfmaker check 附录A    # 统计附录 A\n\n"
            "只统计不阻断；达标判定见 balance。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    parser.add_argument("--min-chars", type=int, default=None,
                        help=f"字数硬门禁下限（默认 {cfg.CHAPTER_MIN_CHARS}；低于则 exit 1）")
    parser.add_argument("--max-chars", type=int, default=None,
                        help=f"字数硬门禁上限（默认 {cfg.CHAPTER_MAX_CHARS}，0=不限制；高于则 exit 1）")
    parser.add_argument("--no-gate", action="store_true",
                        help="关闭字数硬门禁：仅统计不阻断（用于附录/短章等合法短章节）")
    parser.add_argument("--count-mode", choices=["cjk", "visible"], default=None,
                        help=f"字数计数口径（默认 {cfg.CHAPTER_COUNT_MODE}；"
                             "cjk=仅中文，visible=非空可见字符，与小节口径一致）")
    args = parser.parse_args(argv)

    src = resolve_source(args.chapter, "pdfmaker check")
    content = src.read_text(encoding="utf-8")
    # 结构性统计前剥离 LaTeX 注释，避免注释行里的命令字样被误计（如文件头注释含 \\bibitem）
    content_nc = strip_latex_comments(content)

    # 去除表格 / 图 / verbatim / verb 块，只对正文统计中文字数
    n_url = len(re.findall(r"\\url\{", content_nc))
    n_href = len(re.findall(r"\\href\{", content_nc))

    count_mode = args.count_mode or cfg.CHAPTER_COUNT_MODE
    # #172：visible 计数保留表格单元格文字（count_visible_body 内含 strip_nonbody），
    # 避免「软章」被迫凑字；cjk 模式同样保留表格文字，口径一致。
    if count_mode == "visible":
        count = count_visible_body(content_nc)
    else:
        count = chinese_count(strip_nonbody(content_nc))
    print(f"源文件: {src}")
    print(f"字数({count_mode}): {count}（含表格单元格文字）")
    print(f"TeX 字节: {len(content)}")
    print(f"chapter:         {content_nc.count(r'\chapter{')}")
    print(f"section:         {content_nc.count(r'\section{')}")
    print(f"subsection:      {content_nc.count(r'\subsection{')}")
    print(f"subsubsection:   {content_nc.count(r'\subsubsection{')}")
    print(f"tikz:            {content_nc.count(r'\begin{tikzpicture}')}")
    print(f"table:           {content_nc.count(r'\begin{table}')}")
    print(f"verbatim:        {content_nc.count(r'\begin{verbatim}')}")
    print(f"multirow:        {content_nc.count(r'\multirow{')}")
    print(f"bibitem:         {len(re.findall(r'\\bibitem', content_nc))}")
    print(f"链接:            {n_url + n_href}  (url {n_url} + href {n_href})")

    # ---- 编译前风险预检（warning 级，不阻断） ----
    print("\n--- 编译前风险预检（warning 级，不阻断；建议在 xelatex 前修掉） ---")
    glyphs = scan_glyphs(content)
    if glyphs:
        print(f"  [字符风险] 检测到 {len(glyphs)} 处「CJK 字体可能缺字」字符（编译会 Missing character）：")
        seen_pairs: set[tuple[str, str]] = set()
        for g in glyphs:
            pair = (g["char"], g["suggestion"])
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            print(f"    - 「{g['char']}」(U+{ord(g['char']):04X}) → 建议改用 {g['suggestion']}")
        print("    提示：在正文（非 math mode）直接使用 ≥ ≤ ≈ ≠ ①-⑩ 会触发缺字，"
              "改用数学写法或纯文本编号。")
    else:
        print("  [字符风险] 未发现已知缺字风险字符 (OK)")

    trunc = scan_truncated_urls(content_nc)
    if trunc:
        print(f"  [截断 URL] 检测到 {len(trunc)} 处疑似被截断的残破链接（编译/验活会失败）：")
        for u in trunc[:10]:
            print(f"    - {u}")
        print("    提示：素材源常把长 URL 截成 …/foo...，须换素材里的完整 LIVE 链接。")
    else:
        print("  [截断 URL] 未发现疑似截断链接 (OK)")

    # ---- TikZ 节点未转义 & 预检（warning 级，不阻断） ----
    amp = scan_tikz_amp(content)
    if amp:
        print(f"  [TikZ &] 检测到 {len(amp)} 处节点文本内未转义 `&`（编译会 Missing $ inserted）：")
        for h in amp[:10]:
            print(f"    - 行 {h['line']}: ...{h['snippet']}")
        print("    提示：对齐节点内 & 是列分隔符；改用 `／` 或 `\\&`，或写成 `Add / Norm`。")
    else:
        print("  [TikZ &] 未发现未转义 & (OK)")

    # ---- 代码块非 ASCII 预检（warning 级，不阻断） ----
# 等宽字体（Latin Modern Mono）不含希腊字母/中文/全角符号，verbatim/codeblock/
# lstlisting 内出现非 ASCII 会触发 xelatex 的 Missing character（特殊符号注释踩坑）。
    # fix_glyphs 出于保护代码原样会跳过这些环境，故只能在此提前 warning，提示作者改用
    # 纯 ASCII 或把说明移出代码块（与 glyph/trunc/tikz 同为编译前 warning 级预检）。
    nonascii = scan_codeblock_nonascii(content)
    if nonascii:
        print(f"  [代码块非ASCII] 检测到 {len(nonascii)} 处 verbatim/codeblock/lstlisting 内非 ASCII"
              f"字符（等宽字体缺字，编译会 Missing character）：")
        seen_pairs: set[tuple[str, int]] = set()
        for h in nonascii[:10]:
            key = (h["char"], h["line"])
            if key in seen_pairs:
                continue
            seen_pairs.add(key)
            print(f"    - 行 {h['line']}: 「{h['char']}」(U+{h['codepoint']}) … {h['snippet']}")
        print("    提示：等宽字体不含希腊字母/中文/全角符号；请改用纯 ASCII 或把说明移出代码块。")
    else:
        print("  [代码块非ASCII] 未发现代码块内非 ASCII 字符 (OK)")

    # ---- 跨章 \ref 预检（warning 级，不阻断；#158） ----
    # 本工具红线：跨章引用须写成硬编码「第~N 章」，禁用 \ref 跨章引用。单章写作时若顺手写
    # \ref{cha:c3} 指向其它章（本文件无该 label），提前 warning，提示改为硬编码文本；
    # 悬空 \ref（指向全书都不存在的 label）一并捕获。合并前 xref 会作阻断级校验。
    cross = scan_crossref(content)
    if cross:
        print(f"  [跨章ref] 检测到 {len(cross)} 处 \\ref 指向本文件未定义的 label"
              f"（极可能是跨章引用，应改为硬编码「第~N 章」）：")
        for h in cross[:10]:
            print(f"    - 行 {h['line']}: \\ref{{{h['target']}}} … {h['snippet']}")
        print("    提示：跨章互指须用纯文本「第~N 章」，禁用 \\ref（合并前 xref 会阻断）。")
    else:
        print("  [跨章ref] 未发现指向本文件外 label 的 \\ref (OK)")

    # ---- 章节编号重复预检（warning 级，不阻断） ----
    # ctexrep 的 \chapter / \section / \subsection 会自动生成「第 X 章」/「X.Y」编号；
    # 标题里再手写前导编号会与自动编号叠加成「第 X 章 第 X 章」「X.Y X.Y …」的重复
    # 编号（曾踩此坑）。脚手架已从素材标题剥离该前缀，此处兜底提示作者。
    red = scan_redundant_heading_number(content)
    if red:
        print(f"  [章节编号重复] 检测到 {len(red)} 处标题前导编号（会与 ctexrep 自动编号叠加重复）：")
        for h in red:
            label = "章号" if h["kind"] == "chapter_prefix" else "节号"
            print(f"    - 行 {h['line']}（{h['level']}）：手写{label}「{h['snippet']}」"
                  f" → 应删去前缀，自动编号由 ctexrep 生成")
        print("    提示：章节标题不要手写「第N章」/「N.M」，否则 PDF 出现重复编号。")
    else:
        print("  [章节编号重复] 未发现标题前导编号（OK）")

    # ---- 悬空引用门禁（阻断级，exit 1；#173） ----
    # 正文 \\cite 键必须存在本文件 \\bibitem 定义；否则 xelatex 报 Citation undefined、
    # 正文出现「?」。balance 已在 SOP 偏后阶段校验，此处提前到编译前（xelatex 之前）
    # 拦截，与样式门禁同级，双保险。
    cite_undef = scan_cite_undef(content)
    if cite_undef:
        print("\n--- 悬空引用门禁（阻断级，exit 1） ---")
        seen_keys: set[str] = set()
        for h in cite_undef:
            if h["key"] in seen_keys:
                continue
            seen_keys.add(h["key"])
            print(f"  [悬空cite] 行 {h['line']}: \\cite{{{h['key']}}} 无对应 \\bibitem"
                  f"（编译将报 Citation undefined）")
        print("    提示：正文 \\cite 键必须是本文件 \\bibitem 定义的键；"
              "误删文献请补回，或核实键名拼写。")
        return 1

    # ---- 排版样式门禁（阻断级；质量提升） ----
    # 三线表：禁用裸 \hline 与列格式竖线 |（须用 booktabs \toprule/\midrule/\bottomrule）。
    # 伪代码：禁用裸 verbatim/lstlisting（须用共享 preamble 的 codeblock 浅灰底环境）。
    # 第 10–12 章曾退化为 \hline 网格表 + 裸 verbatim，已回填；此处固化为强制规范，
    # 后续章节一旦再退化即阻断，避免回归（参考 SKILL.md「强制排版规范」）。
    style_hits = (
        scan_table_style(content)
        + scan_raw_verbatim(content)
        + scan_table_rules(content)
        + scan_caption_position(content)
    )
    if style_hits:
        print("\n--- 排版样式门禁（阻断级，exit 1） ---")
        for h in style_hits:
            kind = h.get("kind")
            if kind == "hline":
                print(f"  [三线表] 行 {h['line']}: 裸 \\hline —— 须改用 "
                      f"\\toprule/\\midrule/\\bottomrule（参考 SKILL.md 三线表规范）")
            elif kind == "vrule":
                print(f"  [三线表] 行 {h['line']}: 列格式含竖线 | —— 三线表禁用 vertical rule")
            elif kind == "missing_rule":
                print(f"  [三线表] 行 {h['line']}: 表格缺 \\toprule/\\bottomrule 规则线 —— "
                      f"三线表必须含顶线与底线（参考 SKILL.md 三线表规范）")
            elif kind == "caption_table_below":
                print(f"  [表题位置] 行 {h['line']}: 表题位于表格下方 —— 规范要求表题在上")
            elif kind == "caption_figure_above":
                print(f"  [图题位置] 行 {h['line']}: 图题位于图形上方 —— 规范要求图题在下")
            else:
                print(f"  [伪代码样式] 行 {h['line']}: 裸 \\begin{{{h['env']}}} —— "
                      f"须改用 codeblock 环境（参考 SKILL.md 伪代码规范）")
        print("    提示：三线表与 codeblock 伪代码是本工具强制排版规范，"
              "详见 SKILL.md「强制排版规范」一节。")
        return 1

    # ---- 字数硬门禁（可阻断） ----
    effective_min = args.min_chars if args.min_chars is not None else cfg.CHAPTER_MIN_CHARS
    effective_max = args.max_chars if args.max_chars is not None else cfg.CHAPTER_MAX_CHARS
    passed, msg = evaluate_gate(count, effective_min, effective_max, args.no_gate)
    if passed:
        print(f"\n  [OK] {msg}")
        return 0
    print(f"\n  [FAIL] {msg}（check 硬门禁，exit 1）")
    print("    建议扩充正文至下限以上；附录 / 短章可用 --no-gate 放行。")
    return 1


if __name__ == "__main__":
    sys.exit(main())
