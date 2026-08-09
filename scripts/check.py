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
- 元素计数：tikz 图、table、verbatim、multirow、bibitem、链接（url + href）。

路径解析规则
------------
与 fix.py 一致：依次尝试
``<CWD>/第N章/第N章.tex`` → ``<CWD>/第N章.tex`` →
``<脚本目录>/第N章/第N章.tex`` → ``<脚本目录>/第N章.tex``。
支持附录：``python check.py 附录A``。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「fix.py / verify_urls 之后、xelatex 之前」调用，作为内容密度参考。
本脚本只做统计、不阻断流程（是否达标由 check_balance.py 判定）。
用法：
    python check.py [CH_NUM]          # 默认第 1 章
    python check.py 3
    python check.py 附录A

退出码：0（统计用途，不判定失败）；源文件缺失时非零。
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


def resolve_source(arg: str, tool: str) -> Path:
    """定位章节 / 附录源文件（CWD 优先，脚本目录兜底）。"""
    stem = arg if arg.startswith("附录") else f"第{arg}章"
    tried = []
    for base in (Path.cwd(), HERE):
        for cand in (base / stem / f"{stem}.tex", base / f"{stem}.tex"):
            tried.append(cand)
            if cand.exists():
                return cand
    lines = "\n".join(f"    {p}" for p in dict.fromkeys(tried))
    raise SystemExit(f"[{tool}] 找不到 {stem}.tex，已尝试以下位置：\n{lines}")


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"
    SRC = resolve_source(arg, "check.py")

    CONTENT = SRC.read_text(encoding="utf-8")

    # 去除表格 / 图 / verbatim 块，只对正文统计中文字数
    no_code = re.sub(r"\\begin\{verbatim\}.*?\\end\{verbatim\}", "", CONTENT, flags=re.DOTALL)
    no_code = re.sub(r"\\begin\{table\}.*?\\end\{table\}", "", no_code, flags=re.DOTALL)
    no_code = re.sub(r"\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}", "", no_code, flags=re.DOTALL)
    # 去除 \verb|...| 逐字内容，避免其中的 \url/\href 字样被误计
    no_code = re.sub(r"\\verb([^a-zA-Z]).*?\1", "", no_code, flags=re.DOTALL)

    chinese = re.findall(r"[\u4e00-\u9fff]", no_code)
    n_url = len(re.findall(r"\\url\{", CONTENT))
    n_href = len(re.findall(r"\\href\{", CONTENT))

    print(f"源文件: {SRC}")
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
    print(f"bibitem:         {len(re.findall(r'\\bibitem', CONTENT))}")
    print(f"链接:            {n_url + n_href}  (url {n_url} + href {n_href})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
