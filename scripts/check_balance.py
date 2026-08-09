# -*- coding: utf-8 -*-
"""check_balance.py - 章节结构与引用均衡性检查（体检之二）。

用途
----
判断单章「写得是否均衡、引用是否自洽」，是 check.py 统计之后的质量关卡。

检查项
------
1. 每个 subsection 的正文中文字数是否达到下限（过少说明该节单薄）。
2. 表格数量是否达到建议下限。
3. bibitem（参考文献条目）数量与链接数量是否一致——每条文献都应带一个可核验的
   链接。链接同时统计 ``\\url{...}`` 与 ``\\href{...}{...}``（fix.py 会把前者
   转成后者，两种写法都算数）。
4. 孤儿 bibitem：定义了条目却没有任何 ``\\cite`` 引用它。
5. 悬空 cite：``\\cite`` 了某个键却没有对应的 ``\\bibitem``（编译后会变成 ??）。
6. 可选标签告警：``\\bibitem[label]{key}`` 会让编号变成 label 而非从 [1] 顺序编，
   本脚本能正确统计但仍会提示改成 ``\\bibitem{key}``（约定见 SKILL.md § 14）。

路径解析规则
------------
与 fix.py 一致：依次尝试
``<CWD>/第N章/第N章.tex`` → ``<CWD>/第N章.tex`` →
``<脚本目录>/第N章/第N章.tex`` → ``<脚本目录>/第N章.tex``。
支持附录：``python check_balance.py 附录A``。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「check.py 之后、xelatex 之前」调用。发现问题时以非零退出码提示，
但通常作为「告警」而非硬阻断——由作者判断是否修正（硬卡口是 check_overflow.py）。
用法：
    python check_balance.py [CH_NUM]   # 默认第 1 章
    python check_balance.py 3
    python check_balance.py 附录A

退出码：0 全部通过；存在任一问题（小节过短 / bibitem≠链接数 / 孤儿条目 / 悬空引用）时非零。
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

MIN_CHARS = 300      # 单个 subsection 的中文字数下限
MIN_TABLES = 4       # 建议的表格数量下限


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


def strip_blocks(text: str) -> str:
    """去掉表格 / 图 / verbatim 块，避免它们的内容混进正文字数。"""
    return re.sub(
        r"\\begin\{table\}.*?\\end\{table\}"
        r"|\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}"
        r"|\\begin\{verbatim\}.*?\\end\{verbatim\}",
        "",
        text,
        flags=re.DOTALL,
    )


def main() -> int:
    arg = sys.argv[1] if len(sys.argv) > 1 else "1"
    SRC = resolve_source(arg, "check_balance.py")
    CONTENT = SRC.read_text(encoding="utf-8")
    pure = strip_blocks(CONTENT)
    # 去除 \verb|...| 等逐字内容，避免其中的 \url/\cite 字样被误判为真实命令
    no_verb = re.sub(r"\\verb([^a-zA-Z]).*?\1", "", CONTENT, flags=re.DOTALL)

    print(f"源文件: {SRC}")
    problems = 0

    # ---- 1. 各 subsection 字数 ----
    # 用 finditer 记录真实位置，重名小节也能正确切分
    marks = [(m.start(), m.group(1)) for m in re.finditer(r"\\subsection\{([^}]+)\}", pure)]
    print(f"共 {len(marks)} 个 subsection:")
    for i, (start, title) in enumerate(marks):
        end = marks[i + 1][0] if i + 1 < len(marks) else len(pure)
        chars = len(re.findall(r"[\u4e00-\u9fff]", pure[start:end]))
        flag = "  <-- 过少!" if chars < MIN_CHARS else ""
        if chars < MIN_CHARS:
            problems += 1
        print(f"  {i + 1}. {title[:30]}: {chars} 中文字{flag}")

    # ---- 2. 表格数 ----
    table_count = CONTENT.count("\\begin{table}")
    print(f"\n表格: {table_count}（建议 >= {MIN_TABLES}）")

    # ---- 3. bibitem 与链接数 ----
    # 兼容 \bibitem{key} 与 \bibitem[label]{key} 两种写法
    bibitem_keys = re.findall(r"\\bibitem\s*(?:\[[^\]]*\])?\s*\{([^}]*)\}", no_verb)
    bibitem_count = len(bibitem_keys)
    link_count = len(re.findall(r"\\url\{", no_verb)) + len(re.findall(r"\\href\{", no_verb))

    # ---- 4/5. 引用完整性 ----
    cite_keys = set()
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
            "建议改为 \\bibitem{key} 以保证从 [1] 顺序编号（SKILL.md § 14）。"
        )

    print(f"\n结论: {'通过' if problems == 0 else f'{problems} 项待确认'}")
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
