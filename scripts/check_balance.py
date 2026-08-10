# -*- coding: utf-8 -*-
"""check_balance.py - 章节结构与引用均衡性检查（体检之二）。

用途
----
判断单章「写得是否均衡、引用是否自洽」，是 check.py 统计之后的质量关卡。

检查项
------
1. 每个 subsection 的正文字数是否达到下限（过少说明该节单薄）。
2. 表格数量是否达到建议下限。
2b. 配图数量是否达到建议下限（每章至少 1 张图，图文并茂更易读）。
3. bibitem（参考文献条目）数量与链接数量是否一致——每条文献都应带一个可核验的链接。
   链接同时统计 \\url{...} 与 \\href{...}{...}（fix.py 会把前者转成后者，两种都算数）。
4. 孤儿 bibitem：定义了条目却没有任何 \\cite 引用它。
5. 悬空 cite：\\cite 了某个键却没有对应的 \\bibitem（编译后会变成 ??）。
6. 可选标签告警：\\bibitem[label]{key} 会让编号变成 label 而非从 [1] 顺序编，
   本脚本能正确统计但仍会提示改成 \\bibitem{key}（约定见 SKILL.md § 12）。

是否调用
--------
由单章编译 SOP 在「check.py 之后、xelatex 之前」调用。发现问题以非零退出码提示，
但通常作为「告警」而非硬阻断——由作者判断是否修正（硬卡口是 check_overflow.py）。

调用时机
--------
python check_balance.py [CH_NUM]   # 默认第 1 章
python check_balance.py 3
python check_balance.py 附录A

退出码：0 全部通过；存在任一问题（小节过短 / bibitem≠链接数 / 孤儿条目 / 悬空引用）时非零。
"""
import argparse
import re
import sys

from common import setup_utf8, resolve_source, strip_blocks, chinese_count

setup_utf8()

MIN_CHARS = 300      # 单个 subsection 的中文字数下限
MIN_TABLES = 4       # 建议的表格数量下限
MIN_IMAGES = 1       # 建议的配图数量下限（每章至少 1 张）


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check_balance.py",
        description="章节结构与引用均衡性检查（小节字数 / 表格数 / 引用闭合）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python check_balance.py 4    # 检查第 4 章\n"
            "  python check_balance.py 附录A # 检查附录 A\n\n"
            "质量告警，不硬阻断；硬卡口见 check_overflow.py。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args()

    src = resolve_source(args.chapter, "check_balance.py")
    content = src.read_text(encoding="utf-8")
    pure = strip_blocks(content)
    # 去除 \verb|...| 等逐字内容，避免其中的 \url/\cite 字样被误判为真实命令
    no_verb = re.sub(r"\\verb([^a-zA-Z]).*?\1", "", content, flags=re.DOTALL)

    print(f"源文件: {src}")
    problems = 0

    # ---- 1. 各 subsection 字数 ----
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\\subsection\{([^}]+)\}", pure)]
    print(f"共 {len(marks)} 个 subsection:")
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(pure)
        chars = chinese_count(pure[start:end])
        flag = "  <-- 过少!" if chars < MIN_CHARS else ""
        if chars < MIN_CHARS:
            problems += 1
        print(f"  {i + 1}. {title[:30]}: {chars} 中文字{flag}")

    # ---- 2. 表格数 ----
    table_count = content.count("\\begin{table}")
    print(f"\n表格: {table_count}（建议 >= {MIN_TABLES}）")

    # ---- 2b. 配图数 ----
    # 模板已引入 graphicx 包，章节可用 \includegraphics{...} 插图；
    # 统计出现次数作为「图文并茂」的软推荐，不计入硬阻断 problems。
    image_count = len(re.findall(r"\\includegraphics", content))
    print(f"配图: {image_count}（建议 >= {MIN_IMAGES}）")
    if image_count < MIN_IMAGES:
        print(
            f"[建议] 本章配图偏少（0 张），建议至少插入 {MIN_IMAGES} 张图"
            "（如景点/地图/菜品实拍、示意图），避免纯文字堆砌、提升可读性。"
        )

    # ---- 3. bibitem 与链接数 ----
    # 兼容 \bibitem{key} 与 \bibitem[label]{key} 两种写法
    bibitem_keys = re.findall(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", no_verb)
    bibitem_count = len(bibitem_keys)
    link_count = len(re.findall(r"\\url\{", no_verb)) + len(re.findall(r"\\href\{", no_verb))

    # ---- 4/5. 引用完整性 ----
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
        problems += 1
        print("[警告] 以下 bibitem 未被正文引用（孤儿条目）: " + ", ".join(orphans))
    dangling = sorted(cite_keys - bibitem_set)
    if dangling:
        problems += 1
        print("[警告] 以下 \\cite 键无对应 \\bibitem（悬空引用）: " + ", ".join(dangling))
    if bibitem_count != link_count:
        problems += 1
        print("[警告] bibitem 数与链接数不一致（每条文献应带一个可核验链接）!")

    # ---- 6. 可选标签提示（不计入 problems，仅建议） ----
    opt_labeled = re.findall(r"\\bibitem\s*\[[^\]]*\]", no_verb)
    if opt_labeled:
        print(
            f"[建议] 检测到 {len(opt_labeled)} 处 \\bibitem[label]{{key}} 可选标签，"
            "建议改为 \\bibitem{key} 以保证从 [1] 顺序编号（SKILL.md § 12）。"
        )

    print(f"\n结论: {'通过' if problems == 0 else f'{problems} 项待确认'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
