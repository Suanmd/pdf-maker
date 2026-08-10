# -*- coding: utf-8 -*-
"""check.py - 章节内容结构统计（体检之一）。

用途
----
对单个章节源文件做轻量静态统计分析，帮助判断「这一章写得够不够、结构是否完整」。

检查项
------
- 中文字数（去除表格 / 图 / verbatim / verb 块后的正文）。
- TeX 字节数。
- 章节层级计数：chapter / section / subsection / subsubsection。
- 元素计数：tikz 图、table、verbatim、multirow、bibitem、链接（url + href）。

是否调用
--------
由单章编译 SOP 在「fix.py 之后、xelatex 之前」调用，作为内容密度参考。
本脚本只做统计、不阻断流程（是否达标由 check_balance.py 判定）。

调用时机
--------
python check.py [CH_NUM]     # 默认第 1 章
python check.py 3
python check.py 附录A

退出码：0（统计用途，不判定失败）；源文件缺失时非零。
"""
import argparse
import re
import sys

from common import setup_utf8, resolve_source, strip_blocks, chinese_count

setup_utf8()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check.py",
        description="章节内容结构统计（字数 / 层级 / 元素）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python check.py 4       # 统计第 4 章\n"
            "  python check.py 附录A    # 统计附录 A\n\n"
            "只统计不阻断；达标判定见 check_balance.py。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args()

    src = resolve_source(args.chapter, "check.py")
    content = src.read_text(encoding="utf-8")

    # 去除表格 / 图 / verbatim / verb 块，只对正文统计中文字数
    no_code = strip_blocks(content)
    n_url = len(re.findall(r"\\url\{", content))
    n_href = len(re.findall(r"\\href\{", content))

    print(f"源文件: {src}")
    print(f"中文字数: {chinese_count(no_code)}")
    print(f"TeX 字节: {len(content)}")
    print(f"chapter:         {content.count(r'\chapter{')}")
    print(f"section:         {content.count(r'\section{')}")
    print(f"subsection:      {content.count(r'\subsection{')}")
    print(f"subsubsection:   {content.count(r'\subsubsection{')}")
    print(f"tikz:            {content.count(r'\begin{tikzpicture}')}")
    print(f"table:           {content.count(r'\begin{table}')}")
    print(f"verbatim:        {content.count(r'\begin{verbatim}')}")
    print(f"multirow:        {content.count(r'\multirow{')}")
    print(f"bibitem:         {len(re.findall(r'\\bibitem', content))}")
    print(f"链接:            {n_url + n_href}  (url {n_url} + href {n_href})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
