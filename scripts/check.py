# -*- coding: utf-8 -*-
"""check.py - 章节内容结构统计（体检之一）。

用途
----
对单个章节源文件做轻量静态统计分析，帮助判断「这一章写得够不够、结构是否完整」。

检查项
------
- 中文字数（去除表格 / 图 / verbatim 块后的正文）。
- TeX 字节数。
- 章节层级计数：chapter / section / subsection / subsubsection。
- 元素计数：tikz 图、table、verbatim、multirow、bibitem、url。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「fix.py / verify_urls 之后、xelatex 之前」调用，作为内容密度参考。
本脚本只做统计、不阻断流程（是否达标由 check_balance.py 判定）。
用法：
    python check.py [CH_NUM]          # 默认第 1 章
    python check.py 3

退出码：始终为 0（统计用途，不判定失败）。
"""
import re
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

HERE = Path(__file__).parent


def main() -> int:
    CH_NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    SRC = HERE / f"第{CH_NUM}章.tex"
    if not SRC.exists():
        raise SystemExit(f"[check.py] 找不到: {SRC}")

    CONTENT = SRC.read_text(encoding="utf-8")

    # 去除表格 / 图 / verbatim 块，只对正文统计中文字数
    no_code = re.sub(r"\\begin\{verbatim\}.*?\\end\{verbatim\}", "", CONTENT, flags=re.DOTALL)
    no_code = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", no_code, flags=re.DOTALL)
    no_code = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", "", no_code, flags=re.DOTALL)

    chinese = re.findall(r"[\u4e00-\u9fff]", no_code)
    print(f"中文字数: {len(chinese)}")
    print(f"TeX 字节: {len(CONTENT)}")
    print(f"chapter:         {CONTENT.count(r'\chapter{')}")
    print(f"section:         {CONTENT.count(r'\section{')}")
    print(f"subsection:      {CONTENT.count(r'\subsection{')}")
    print(f"subsubsection:   {CONTENT.count(r'\subsubsection{')}")
    print(f"tikz:            {CONTENT.count(r'\begin{tikzpicture}')}")
    print(f"table:           {CONTENT.count(r'\begin{table}')}")
    print(f"verbatim:        {CONTENT.count(r'\begin{verbatim}')}")
    print(f"multirow:        {CONTENT.count(r'\multirow{')}")
    print(f"bibitem:         {CONTENT.count(r'\bibitem{')}")
    print(f"url:             {len(re.findall(r'\\url\{', CONTENT))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
