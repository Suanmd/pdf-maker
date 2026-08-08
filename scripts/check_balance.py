# -*- coding: utf-8 -*-
"""check_balance.py - 章节结构与引用均衡性检查（体检之二）。

用途
----
判断单章「写得是否均衡、引用是否自洽」，是 check.py 统计之后的质量关卡。

检查项
------
- 每个 subsection 的正文中文字数是否达到下限（过少说明该节单薄）。
- 表格数量是否达到建议下限。
- bibitem（参考文献条目）数量与 url（正文引用）数量是否一致
  （不一致往往意味着「写了条目却没在正文中引用」或反之）。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「check.py 之后、xelatex 之前」调用。发现严重不均衡时会
以非零退出码提示，但通常作为「告警」而非硬阻断——由作者判断是否修正。
用法：
    python check_balance.py [CH_NUM]   # 默认第 1 章
    python check_balance.py 3

退出码：0 通过；存在不一致（如 bibitem≠url）时非零。
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
        raise SystemExit(f"[check_balance.py] 找不到: {SRC}")

    CONTENT = SRC.read_text(encoding="utf-8")

    # 去除表格 / 图 / verbatim 块，按 subsection 切分正文
    pure = re.sub(
        r"\\begin\{table\}.*?\\end\{table\}"
        r"|\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}"
        r"|\\begin\{verbatim\}.*?\\end\{verbatim\}",
        "",
        CONTENT,
        flags=re.DOTALL,
    )

    SUBSECTIONS = re.findall(r"\\subsection\{([^}]+)\}", pure)
    MIN_CHARS = 300
    print(f"共 {len(SUBSECTIONS)} 个 subsection:")
    problems = 0
    for i, title in enumerate(SUBSECTIONS, 1):
        start = pure.find(f"\\subsection{{{title}}}")
        end = (
            pure.find(f"\\subsection{{{SUBSECTIONS[i]}}}", start + 1)
            if i < len(SUBSECTIONS)
            else len(pure)
        )
        if end < 0:
            end = len(pure)
        chars = len(re.findall(r"[\u4e00-\u9fff]", pure[start:end]))
        flag = "  ⚠️ 过少!" if chars < MIN_CHARS else ""
        if chars < MIN_CHARS:
            problems += 1
        print(f"  {i}. {title[:30]}: {chars} 中文字{flag}")

    table_count = CONTENT.count("\\begin{table}")
    bibitem_count = CONTENT.count("\\bibitem{")
    url_count = len(re.findall(r"\\url\{", CONTENT))
    print(f"\n表格: {table_count}（建议 ≥ 4）")
    print(f"bibitem: {bibitem_count}，URL: {url_count}")
    if bibitem_count != url_count:
        print("⚠️ bibitem 数与 URL 数不一致!")
        problems += 1

    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
