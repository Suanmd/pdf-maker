# -*- coding: utf-8 -*-
"""balance —— 章节结构与引用均衡性检查（体检之二）。

判断单章「写得是否均衡、引用是否自洽」，是 check 统计之后的质量关卡。

检查项
------
1. 每个 section / subsection / subsubsection 的正文量是否达标（过少说明该节单薄）；
   section 完全空白为阻断级，其余为空/偏短为建议级。统计保留表格单元格文字，
   避免「纯表格节」误判空白。用 char_count 统计「非空可见字符」（CJK + 拉丁 + 数字
   + 标点），而非仅数中文，避免「中英文混排/含少量公式的小节」被误判过短。
2. 表格数量是否达到建议下限（建议告警，不阻断）。
3. 配图数量是否达到建议下限（建议每章 ≥ 1 张，建议告警，不阻断）。
4. bibitem 与链接数一致——每条文献都应带一个可核验的链接（阻断）。
5. 参考文献数量下限——cfg.MIN_REFS > 0 时才做建议级告警（默认 0 = 不设下限，
   按需引用；零引用是合法形态）。
6. 孤儿 bibitem：定义了条目却没有任何 \\cite 引用它（阻断）。
7. 悬空 cite：\\cite 了某个键却没有对应的 \\bibitem（阻断）。
8. 参考文献/正文含「疑似截断 URL」（含省略号/空白/3+ 连续点） → 阻断。
9. 可选标签告警：\\bibitem[label]{key} 会让编号变 label，仅建议不阻断。
10. TikZ 节点 ``\\\\`` 换行（无 align=）阻断：编译期 missing \\item Fatal。
11. TikZ 节点未转义 ``&`` 阻断：编译期 Missing $ inserted / 对齐符错误。

退出码（阻断/建议分明）
----------------------
0  无阻断级问题（仅建议项不算阻断，可正常继续）。
1  存在任一阻断级问题（小节完全空白 / 引用不闭合 / bibitem 缺链接 / 截断 URL / TikZ 坏节点）。
"""

import argparse
import re
import sys

import pdfmaker.core.config as cfg
from pdfmaker.core import (
    char_count,
    resolve_source,
    scan_tikz_amp,
    scan_tikz_badbreak,
    scan_truncated_urls,
    setup_utf8,
    strip_latex_comments,
    strip_nonbody,
)
from pdfmaker.core.watchdog import ScanTimeoutError, scan_watchdog

setup_utf8()


def count_figures(content: str) -> int:
    """配图数 = 位图（\\includegraphics）+ TikZ 矢量图（\\begin{tikzpicture}）。

    两者都算「图」。只数 \\includegraphics 会漏掉纯 TikZ 矢量图，
    让只有矢量图的章节被误判「缺图」。
    """
    image_count = len(re.findall(r"\\includegraphics", content))
    tikz_count = content.count("\\begin{tikzpicture}")
    return image_count + tikz_count


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker balance",
        description="章节结构与引用均衡性检查（小节字数 / 表格数 / 引用闭合 / 截断 URL / TikZ）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker balance 4    # 检查第 4 章\n"
            "  python -m pdfmaker balance 附录A # 检查附录 A\n\n"
            "阻断级问题 exit 1；仅建议项不阻断（exit 0）。硬卡口见 overflow。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args(argv)

    # 扫描看门狗：正则扫描若指数回溯会永久空转，超时按阻断处理（exit 1）
    try:
        with scan_watchdog(cfg.SCAN_TIMEOUT, "balance"):
            return _run(args)
    except ScanTimeoutError:
        print(
            f"[balance] 扫描超过 {cfg.SCAN_TIMEOUT:g}s 时限（疑似正则回溯或病态输入），"
            f"exit 1 阻断。请检查章节源码中的未闭合定界符，"
            f"或经 PDFMAKER_SCAN_TIMEOUT / .pdfmaker.toml 的 scan_timeout 放宽时限。",
            file=sys.stderr,
        )
        return 1


def _run(args) -> int:
    """balance 的均衡检查主体（在 main 的看门狗时限内运行）。"""
    src = resolve_source(args.chapter, "pdfmaker balance")
    content = src.read_text(encoding="utf-8")
    # 结构性统计前剥离 LaTeX 注释，避免注释行里的命令字样被误计（如 \bibitem / 注释掉的 tikz）
    content_nc = strip_latex_comments(content)
    body = strip_nonbody(content_nc)  # 保留表格单元格文字，骨架校验更准确
    # 去除 \verb|...| 等逐字内容，避免其中的 \url/\cite 字样被误判为真实命令
    no_verb = re.sub(r"\\verb([^a-zA-Z]).*?\1", "", content_nc, flags=re.DOTALL)

    print(f"源文件: {src}")
    blocking: list[str] = []   # 阻断级问题（exit 1）
    advisory: list[str] = []   # 建议项（exit 0）

    # ---- 1. 各 subsection 字数（非空可见字符，保留表格单元格） ----
    marks = [(m.end(), m.group(1)) for m in re.finditer(r"\\subsection\{([^}]+)\}", body)]
    print(f"共 {len(marks)} 个 subsection（字数 = 非空可见字符，含表格单元格/中英文/数字/标点）：")
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(body)
        chars = char_count(body[start:end])
        if chars == 0:
            blocking.append(f"subsection「{title}」完全空白（0 字符）")
            flag = "  <-- 阻断:空白!"
        elif chars < cfg.MIN_CHARS:
            advisory.append(f"subsection「{title}」偏短（{chars} < {cfg.MIN_CHARS}）")
            flag = f"  <-- 偏短({chars})"
        else:
            flag = f"  ({chars})"
        print(f"  {i + 1}. {title[:30]}: {chars}{flag}")

    # ---- 1b. 各 section 字数（整章骨架校验） ----
    # 用保留表格单元格的 body 统计，避免「纯表格节」被误判空白。section 完全空白为阻断。
    sec_marks = [(m.end(), m.group(1)) for m in re.finditer(r"\\section\{([^}]+)\}", body)]
    print(f"\n共 {len(sec_marks)} 个 section（字数 = 非空可见字符，含表格单元格）：")
    for i, (start, title) in enumerate(sec_marks):
        end = sec_marks[i + 1][0] if i + 1 < len(sec_marks) else len(body)
        chars = char_count(body[start:end])
        if chars == 0:
            blocking.append(f"section「{title}」完全空白（0 字符）")
            flag = "  <-- 阻断:空白!"
        elif chars < cfg.MIN_CHARS:
            advisory.append(f"section「{title}」偏短（{chars} < {cfg.MIN_CHARS}）")
            flag = f"  <-- 偏短({chars})"
        else:
            flag = f"  ({chars})"
        print(f"  {i + 1}. {title[:30]}: {chars}{flag}")

    # ---- 1c. 各 subsubsection 字数（建议级，不阻断） ----
    subsub_marks = [(m.end(), m.group(1)) for m in re.finditer(r"\\subsubsection\{([^}]+)\}", body)]
    if subsub_marks:
        print(f"\n共 {len(subsub_marks)} 个 subsubsection（建议级）：")
        for i, (start, title) in enumerate(subsub_marks):
            end = subsub_marks[i + 1][0] if i + 1 < len(subsub_marks) else len(body)
            chars = char_count(body[start:end])
            if chars == 0:
                advisory.append(f"subsubsection「{title}」完全空白（0 字符）")
                flag = "  <-- 建议:空白?"
            elif chars < cfg.MIN_CHARS:
                advisory.append(f"subsubsection「{title}」偏短（{chars} < {cfg.MIN_CHARS}）")
                flag = f"  <-- 偏短({chars})"
            else:
                flag = f"  ({chars})"
            print(f"  {i + 1}. {title[:30]}: {chars}{flag}")

    # ---- 2. 表格数（建议） ----
    table_count = content_nc.count("\\begin{table}")
    print(f"\n表格: {table_count}（建议 >= {cfg.MIN_TABLES}）")
    if table_count < cfg.MIN_TABLES:
        advisory.append(f"表格数 {table_count} < 建议 {cfg.MIN_TABLES}")

    # ---- 3. 配图数（建议） ----
    # 配图 = 位图（\includegraphics）+ TikZ 矢量图（\begin{tikzpicture}）——两者都是图。
    image_count = len(re.findall(r"\\includegraphics", content_nc))
    tikz_count = content_nc.count("\\begin{tikzpicture}")
    figure_count = count_figures(content_nc)
    print(f"配图: {figure_count}（建议 >= {cfg.MIN_IMAGES}；含 \\includegraphics {image_count} + TikZ {tikz_count}）")
    if figure_count < cfg.MIN_IMAGES:
        advisory.append(f"配图数 {figure_count} < 建议 {cfg.MIN_IMAGES}，建议补充示意图/实拍/图表")

    # ---- 4/6/7. 引用完整性 + 链接一致性 ----
    bibitem_keys = re.findall(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", no_verb)
    bibitem_count = len(bibitem_keys)
    link_count = len(re.findall(r"\\url\{", no_verb)) + len(re.findall(r"\\href\{", no_verb))

    cite_keys: set[str] = set()
    for m in re.finditer(r"\\cite[a-zA-Z]*\s*(?:\[[^\]]*\])*\s*\{([^}]*)\}", no_verb):
        for k in m.group(1).split(","):
            k = k.strip()
            if k:
                cite_keys.add(k)
    bibitem_set = set(bibitem_keys)

    print(f"bibitem: {bibitem_count}，链接: {link_count}，被引用键: {len(cite_keys)}")

    orphans = sorted(bibitem_set - cite_keys)
    if orphans:
        blocking.append("孤儿 bibitem（未被引用）: " + ", ".join(orphans))
        print("[阻断] 以下 bibitem 未被正文引用（孤儿条目）: " + ", ".join(orphans))
    dangling = sorted(cite_keys - bibitem_set)
    if dangling:
        blocking.append("悬空 cite（无对应 bibitem）: " + ", ".join(dangling))
        print("[阻断] 以下 \\cite 键无对应 \\bibitem（悬空引用）: " + ", ".join(dangling))
    if bibitem_count != link_count:
        blocking.append(f"bibitem({bibitem_count}) 与链接({link_count}) 数不一致")
        print("[阻断] bibitem 数与链接数不一致（每条文献应带一个可核验链接）!")

    # ---- 5. 参考文献数量建议（MIN_REFS > 0 时才生效，默认 0 不设下限） ----
    # 哲学：引用是论证的需要而非章节配额；资料无外部文献时完全不写，
    # 严禁为凑数而造引用。仅当项目经 PDFMAKER_MIN_REFS / .pdfmaker.toml 显式设置了
    # 正整数下限时才打印建议。零引用章（bibitem==0 且 link==0）始终豁免。
    zero_ref_chapter = (bibitem_count == 0 and link_count == 0)
    if cfg.MIN_REFS > 0 and bibitem_count < cfg.MIN_REFS and not zero_ref_chapter:
        advisory.append(
            f"参考文献数 {bibitem_count} < 项目建议下限 {cfg.MIN_REFS}"
        )
        print(f"[建议] 参考文献仅 {bibitem_count} 条，低于项目设置的下限 {cfg.MIN_REFS} "
              "条（建议按需核查）。")

    # ---- 8. 截断 URL（阻断） ----
    trunc = scan_truncated_urls(content_nc)
    if trunc:
        blocking.append(f"疑似截断 URL ×{len(trunc)}")
        print("[阻断] 以下 URL 疑似被素材源截断，须替换为完整 LIVE 链接：")
        for u in trunc[:10]:
            print(f"    - {u}")

    # ---- 9. 可选标签提示（仅建议） ----
    opt_labeled = re.findall(r"\\bibitem\s*\[[^\]]*\]", no_verb)
    if opt_labeled:
        advisory.append(f"{len(opt_labeled)} 处 \\bibitem[label] 建议改为 \\bibitem{{key}}")
        print(
            f"[建议] 检测到 {len(opt_labeled)} 处 \\bibitem[label]{{key}} 可选标签，"
            "建议改为 \\bibitem{key} 以保证从 [1] 顺序编号。"
        )

    # ---- 10. TikZ 节点 `\\` 换行（无 align=）阻断：编译期 missing \item Fatal ----
    tikz_hits = scan_tikz_badbreak(content_nc)
    if tikz_hits:
        blocking.append(
            f"TikZ 节点含 `\\\\` 换行但未声明 align= ×{len(tikz_hits)}"
            f"（编译会触发 missing \\item Fatal）"
        )
        print("[阻断] 以下 TikZ 节点在文本内用了 `\\\\` 换行却未声明 align=，"
              "xelatex 会报 missing \\item Fatal：")
        for h in tikz_hits[:10]:
            print(f"    行 {h['line']}: ...{h['snippet']}")
        print("    修复：在节点选项加 align=left（如 \\node[align=left]{A\\\\B}），"
              "或改用全角括号「（）」替代 \\\\ 换行。")

    # ---- 11. TikZ 节点未转义 & 阻断：编译期 Missing $ inserted / 对齐符错误 ----
    tikz_amp = scan_tikz_amp(content_nc)
    if tikz_amp:
        blocking.append(
            f"TikZ 节点含未转义 & ×{len(tikz_amp)}"
            f"（编译会触发 Missing $ inserted / 对齐符错误）"
        )
        print("[阻断] 以下 TikZ 节点文本内含未转义 `&`（在对齐节点里是列分隔符）：")
        for h in tikz_amp[:10]:
            print(f"    行 {h['line']}: ...{h['snippet']}")
        print("    修复：对齐节点内需要连接词时，改用 `／` 或转义 `\\&`，"
              "或写成 `Add / Norm` 这类无 & 形式。")

    # ---- 汇总 ----
    print("\n结论:")
    if advisory:
        print(f"  建议项({len(advisory)}，不阻断):")
        for a in advisory:
            print(f"    - {a}")
    if blocking:
        print(f"  阻断项({len(blocking)}，必须修正):")
        for b in blocking:
            print(f"    - {b}")
        print(f"\n[FAIL] 存在 {len(blocking)} 项阻断级问题，exit 1。修正后重跑。")
        return 1
    print("  [OK] 无阻断级问题（exit 0）。建议项可酌情优化。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
