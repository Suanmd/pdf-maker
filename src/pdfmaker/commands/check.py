# -*- coding: utf-8 -*-
"""check —— 章节内容结构统计与编译前门禁（体检之一）。

对单个章节源文件做轻量静态统计分析，帮助判断「这一章写得够不够、结构是否完整」，
并把排版退化与悬空引用挡在 xelatex 之前。

检查项
------
- 字数统计：正文字数（cjk / visible 两种口径，均保留表格单元格文字）、TeX 字节数。
- 结构计数：chapter / section / subsection / subsubsection 层级，tikz 图、table、
  verbatim、multirow、bibitem、链接（url + href）元素。
- 编译前风险预检（warning 级，不阻断）：缺字字符 / 截断 URL / TikZ 未转义 & /
  代码块非 ASCII / 跨章 \\ref / 标题手写前导编号 / \\texttt 不可断行长串 /
  tabularx 单列挤压。
- 悬空引用门禁（阻断级）：正文 \\cite 键必须存在本文件 \\bibitem 定义，否则 exit 1。
- 排版样式门禁（阻断级）：三线表禁用裸 \\hline 与列格式竖线 ``|`` 且必须含
  \\toprule/\\bottomrule 顶底线；伪代码禁用裸 verbatim/lstlisting；表题须在上、
  图题须在下。退化写法直接 exit 1 阻断，防止后续章节回归。
- 字数门禁（默认告警级，--strict 阻断）：正文字数低于 ``--min-chars``（默认
  ``CHAPTER_MIN_CHARS``）时打印 WARN 与具体缺口并 exit 0（不阻断）；
  加 ``--strict`` 恢复硬阻断。附录 / 短章可用 ``--no-gate`` 关闭评估。

退出码
------
0 达标（或字数未达标但未开 --strict）；1 排版样式违规 / 悬空引用 / --strict 下字数不足（或源文件缺失）。
"""

import argparse
import re
import sys

import pdfmaker.core.config as cfg
from pdfmaker.core import (
    char_count,
    chinese_count,
    count_visible_body,
    resolve_source,
    scan_caption_position,
    scan_cite_undef,
    scan_codeblock_nonascii,
    scan_crossref,
    scan_glyphs,
    scan_raw_verbatim,
    scan_redundant_heading_number,
    scan_squeezed_tables,
    scan_table_rules,
    scan_table_style,
    scan_tikz_amp,
    scan_truncated_urls,
    scan_unbreakable_runs,
    setup_utf8,
    strip_latex_comments,
    strip_nonbody,
)
from pdfmaker.core.watchdog import ScanTimeoutError, scan_watchdog

setup_utf8()


def evaluate_gate(count: int, min_chars: int, max_chars: int = 0,
                  no_gate: bool = False) -> tuple[bool, str]:
    """字数门禁判定，返回 (passed, message)。

    - no_gate=True：仅统计不评估，永远 passed；
    - count < min_chars：未达标（过短）；默认仅告警（main exit 0），--strict 才 exit 1；
    - max_chars > 0 且 count > max_chars：未达标（过长），处理同过短；
    - 否则通过。max_chars=0 表示不限制上限（延续「字数/引用不设上限」的宽松哲学）。

    抽成纯函数便于复用，避免依赖文件系统。注意：本函数只管「达标与否」的判定，
    阻断/告警的策略差异在 main 中体现（默认告警，避免内容已达标时被迫注水）。
    """
    if no_gate:
        return True, "字数门禁已关闭（--no-gate）：仅统计，不评估。"
    if count < min_chars:
        return False, f"字数不足：{count} < 下限 {min_chars}"
    if max_chars > 0 and count > max_chars:
        return False, f"字数超长：{count} > 上限 {max_chars}"
    return True, f"字数达标：{min_chars} <= {count}" + (f" <= {max_chars}" if max_chars > 0 else "")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker check",
        description="章节内容结构统计 + 编译前风险预检 + 排版样式/字数门禁",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker check 4       # 统计第 4 章\n"
            "  python -m pdfmaker check 附录A    # 统计附录 A\n\n"
            "结构均衡判定见 balance；边写边查可用 lint（仅提示不阻断）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    parser.add_argument("--min-chars", type=int, default=None,
                        help=f"字数下限参考值（默认 {cfg.CHAPTER_MIN_CHARS}；低于仅告警不阻断，"
                             f"--strict 时才 exit 1）")
    parser.add_argument("--max-chars", type=int, default=None,
                        help=f"字数上限参考值（默认 {cfg.CHAPTER_MAX_CHARS}，0=不限制；策略同下限）")
    parser.add_argument("--no-gate", action="store_true",
                        help="完全关闭字数评估：仅统计，连告警也不打印（用于附录/短章等合法短章节）")
    parser.add_argument("--strict", action="store_true",
                        help="字数未达标时 exit 1 阻断（恢复硬门禁行为；"
                             "默认仅告警——字数是内容厚度的主观代理指标，不应逼作者注水凑数）")
    parser.add_argument("--count-mode", choices=["cjk", "visible"], default=None,
                        help=f"字数计数口径（默认 {cfg.CHAPTER_COUNT_MODE}；"
                             "cjk=仅中文，visible=非空可见字符，与小节口径一致）")
    args = parser.parse_args(argv)

    # 扫描看门狗：正则扫描若指数回溯会永久空转，超时按阻断处理（exit 1）
    try:
        with scan_watchdog(cfg.SCAN_TIMEOUT, "check"):
            return _run(args)
    except ScanTimeoutError:
        print(
            f"[check] 扫描超过 {cfg.SCAN_TIMEOUT:g}s 时限（疑似正则回溯或病态输入），"
            f"exit 1 阻断。请检查章节源码中的未闭合定界符（如裸 $），"
            f"或经 PDFMAKER_SCAN_TIMEOUT / .pdfmaker.toml 的 scan_timeout 放宽时限。",
            file=sys.stderr,
        )
        return 1


def _run(args) -> int:
    """check 的扫描与门禁主体（在 main 的看门狗时限内运行）。"""
    src = resolve_source(args.chapter, "pdfmaker check")
    content = src.read_text(encoding="utf-8")
    # 结构性统计前剥离 LaTeX 注释，避免注释行里的命令字样被误计（如文件头注释含 \bibitem）
    content_nc = strip_latex_comments(content)

    n_url = len(re.findall(r"\\url\{", content_nc))
    n_href = len(re.findall(r"\\href\{", content_nc))

    count_mode = args.count_mode or cfg.CHAPTER_COUNT_MODE
    # visible 计数保留表格单元格文字（count_visible_body 内含 strip_nonbody），
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

    amp = scan_tikz_amp(content)
    if amp:
        print(f"  [TikZ &] 检测到 {len(amp)} 处节点文本内未转义 `&`（编译会 Missing $ inserted）：")
        for h in amp[:10]:
            print(f"    - 行 {h['line']}: ...{h['snippet']}")
        print("    提示：对齐节点内 & 是列分隔符；改用 `／` 或 `\\&`，或写成 `Add / Norm`。")
    else:
        print("  [TikZ &] 未发现未转义 & (OK)")

    # 等宽字体（Latin Modern Mono）不含希腊字母/中文/全角符号，verbatim/codeblock/
    # lstlisting 内出现非 ASCII 会触发 xelatex 的 Missing character。fix_glyphs 出于
    # 保护代码原样会跳过这些环境，故只能在此提前 warning，提示作者改用纯 ASCII
    # 或把说明移出代码块。
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

    # ctexrep 的 \chapter / \section / \subsection 会自动生成「第 X 章」/「X.Y」编号；
    # 标题里再手写前导编号会与自动编号叠加成「第 X 章 第 X 章」「X.Y X.Y …」的重复
    # 编号。脚手架已从素材标题剥离该前缀，此处兜底提示作者。
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

    # \texttt 等宽字体（Latin Modern Mono）禁用断词，且 / . _ : 等符号在文本模式不构成
    # 断点；超过阈值的长串落在行尾附近即触发 Overfull \hbox——以往只能编译后读 log
    # 才发现（overflow 硬卡口），此处提前到写作期预警（warning 级，不阻断）。
    # 阈值 cfg.LONGRUN_WARN_CHARS（默认 25，0 = 关闭）。
    longrun = scan_unbreakable_runs(content, threshold=cfg.LONGRUN_WARN_CHARS)
    if longrun:
        print(f"  [不可断行长串] 检测到 {len(longrun)} 处 \\texttt 等宽长串"
              f"（≥{cfg.LONGRUN_WARN_CHARS} 字形；启发式预警——落在行尾附近时才可能 Overfull \\hbox）：")
        for h in longrun[:10]:
            print(f"    - 行 {h['line']}: {h['run']}（{h['length']} 字形）")
        print("    提示：缩短标识符、在长串前后垫可断行中文、或用顿号等 CJK 标点代替 / 连排；"
              "阈值可用 PDFMAKER_LONGRUN_WARN_CHARS / .pdfmaker.toml 调整。")
    else:
        print("  [不可断行长串] 未发现超长 \\texttt 等宽串 (OK)")

    # tabularx 的 l/c/r 列不换行：单元格内的超长 \texttt 标识符会把该列撑宽、
    # 把 X 列挤成窄条（单列挤压）。此处提前到写作期预警（warning 级，不阻断），
    # 阈值 cfg.TABLE_SQUEEZE_WARN_CHARS（默认 20，0 = 关闭）。
    squeeze = scan_squeezed_tables(content, threshold=cfg.TABLE_SQUEEZE_WARN_CHARS)
    if squeeze:
        print(f"  [单列挤压] 检测到 {len(squeeze)} 处 tabularx 非 X 列超长不可断长串"
              f"（≥{cfg.TABLE_SQUEEZE_WARN_CHARS} 字形；该列会撑宽并挤压 X 列）：")
        for h in squeeze[:10]:
            print(f"    - 行 {h['line']}（第 {h['col']} 列，{h['letter']} 列）: "
                  f"{h['run']}（{h['length']} 字形）")
        print("    提示：改用 >{\\raggedright\\arraybackslash}p{宽度} 定宽换行列，"
              "或给长串加 \\allowbreak（fix 会对 ≥阈值的长 \\texttt 自动插入）；"
              "阈值可用 PDFMAKER_TABLE_SQUEEZE_WARN_CHARS / .pdfmaker.toml 调整。")
    else:
        print("  [单列挤压] 未发现 tabularx 非 X 列超长串 (OK)")

    # ---- 悬空引用门禁（阻断级，exit 1） ----
    # 正文 \cite 键必须存在本文件 \bibitem 定义；否则 xelatex 报 Citation undefined、
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

    # ---- 排版样式门禁（阻断级，exit 1） ----
    # 三线表：禁用裸 \hline 与列格式竖线 |（须用 booktabs \toprule/\midrule/\bottomrule）。
    # 伪代码：禁用裸 verbatim/lstlisting（须用共享 preamble 的 codeblock 浅灰底环境）。
    # 此处固化为强制规范，后续章节一旦退化即阻断，避免回归（参考 SKILL.md「强制排版规范」）。
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

    # ---- 字数门禁（默认告警不阻断；--strict 恢复硬阻断） ----
    # 设计理由：字数是「内容厚度」的主观代理指标，与排版样式/悬空引用这类
    # 客观错误不同——cjk 口径对中英混排技术写作系统性偏低，硬阻断曾逼出「凑字数注水」
    # 的反模式。软化后：未达标打印 WARN 与具体缺口，由作者自行判断，不再强制返工。
    effective_min = args.min_chars if args.min_chars is not None else cfg.CHAPTER_MIN_CHARS
    effective_max = args.max_chars if args.max_chars is not None else cfg.CHAPTER_MAX_CHARS
    passed, msg = evaluate_gate(count, effective_min, effective_max, args.no_gate)
    if passed:
        print(f"\n  [OK] {msg}")
        return 0
    level = "FAIL" if args.strict else "WARN"
    tail = "（--strict 硬门禁，exit 1）" if args.strict else "（仅告警，不阻断；--strict 可恢复硬门禁）"
    print(f"\n  [{level}] {msg}{tail}")
    gap = effective_min - count
    if gap > 0:
        print(f"    还差 {gap} 字（{count_mode} 口径）。建议：")
        print("      - 若内容确已达标，可忽略本告警；或在 .pdfmaker.toml 调低 chapter_min_chars")
        print(f"      - 若仍在写作中，边写边查：python -m pdfmaker lint {args.chapter}（不阻断，随时复跑）")
        if count_mode == "cjk":
            print("      - 若本章英文/代码占比高，可用 --count-mode visible 重新计量，"
                  "或在 .pdfmaker.toml 设 chapter_count_mode = \"visible\"")
    else:
        print(f"    超出 {-gap} 字（{count_mode} 口径）。可考虑拆分章节；附录可用 --no-gate 关闭评估。")
    return 1 if args.strict else 0


if __name__ == "__main__":
    sys.exit(main())
