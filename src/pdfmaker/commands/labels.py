# -*- coding: utf-8 -*-
"""labels —— 跨章重复 \\label 去重（构建期去重工具）。

整书合并前，检测在多个章节里被重复定义的 \\label（如 fig:pipeline / tab:cmp）。
LaTeX 取最后一次定义，会导致前面章节的 \\ref 全部指向错误编号。本工具把每个
冲突 label 按章重命名为 原label-ch<N>（附录为 原label-ch附录X），并同步改写该章内的
\\ref / \\cref / \\autoref / \\eqref / \\pageref。

安全检查
--------
若某冲突 label 被「未定义它的章节」跨章引用，则中止并提示手工处理，
绝不擅自改名（否则会产生 ?? 断链）。

退出码
------
0 已完成（无论有无改动）；2 检测到跨章引用、中止改名。
"""

import argparse
import re
import sys
from pathlib import Path

from pdfmaker.core.chapters import collect_chapters
from pdfmaker.core.paths import setup_utf8

setup_utf8()

LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|cref|autoref|eqref|pageref)\{([^}]+)\}")


def chapter_key(f: str) -> str:
    """从文件路径解析章节标识：第N章 → N；附录X → 附录X；否则 ?。"""
    m = re.search(r"第(\d+)章", str(f))
    if m:
        return m.group(1)
    m = re.search(r"附录([^/\\]+?)\.tex", str(f))
    if m:
        return "附录" + m.group(1)
    return "?"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker labels",
        description="跨章重复 \\label 去重（构建期去重，不每章必跑）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker labels .            # 当前目录为书稿根\n"
            "  python -m pdfmaker labels /path/to/book"
        ),
    )
    parser.add_argument("root", nargs="?", default=".", help="书稿项目根目录，默认当前目录")
    args = parser.parse_args(argv)

    root = Path(args.root)
    # 章节枚举与整书合并 / 全量验活共用同一真源（core.chapters.collect_chapters），
    # 覆盖标准布局与扁平布局，按章号数值排序。
    files = collect_chapters(root)
    if not files:
        raise SystemExit(f"[labels] 在 {root} 找不到 第*章/第*章.tex 或 附录*/附录*.tex")

    texts: dict[str, str] = {}
    defined: dict[str, set[str]] = {}
    for f in files:
        chap = chapter_key(f)
        txt = Path(f).read_text(encoding="utf-8")
        texts[chap] = txt
        for m in LABEL_RE.finditer(txt):
            defined.setdefault(m.group(1), set()).add(chap)

    collide = {lab: chs for lab, chs in defined.items() if len(chs) > 1}
    print(f"[labels] 冲突 label 数：{len(collide)}")
    for lab, chs in sorted(collide.items()):
        print(f"  {lab}: 章节 {sorted(chs)}")

    # ---- 跨章引用检查：冲突 label 被「未定义它的章节」引用 → 中止 ----
    cross: dict[str, dict[str, int]] = {}
    for chap, txt in texts.items():
        for m in REF_RE.finditer(txt):
            lab = m.group(1)
            if lab in collide and chap not in defined[lab]:
                cross.setdefault(lab, {}).setdefault(chap, 0)
                cross[lab][chap] += 1
    if cross:
        print("\n!!! 检测到跨章引用，中止自动改名，请手工处理：")
        for lab, cm in cross.items():
            print(f"  {lab}: 被非定义章节引用 {cm}")
        return 2

    # ---- 构建改名映射并应用 ----
    rename: dict[str, dict[str, str]] = {}
    for lab, chs in collide.items():
        rename[lab] = {}
        for c in sorted(chs):
            newl = f"{lab}-ch{c}"
            if newl in defined:
                raise SystemExit(f"[labels] 目标名 {newl} 已存在，放弃。")
            rename[lab][c] = newl

    if not collide:
        print("[labels] 无跨章重复 label，无需改名。")
        return 0

    print("\n应用改名：")
    for f in files:
        chap = chapter_key(f)
        txt = texts[chap]
        changed = 0
        for lab, chs in collide.items():
            if chap not in chs:
                continue
            newl = rename[lab][chap]
            txt, n1 = re.subn(
                r"\\label\{" + re.escape(lab) + r"\}", r"\\label{" + newl + "}", txt
            )
            txt, n2 = re.subn(
                r"\\(ref|cref|autoref|eqref|pageref)\{" + re.escape(lab) + r"\}",
                r"\\\1{" + newl + "}",
                txt,
            )
            changed += n1 + n2
        if changed:
            Path(f).write_text(txt, encoding="utf-8")
            print(f"  ch{chap}: {changed} 处替换")
    print("\n完成。重跑 fix 并重新编译，再跑 overflow 确认 0 冲突。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
