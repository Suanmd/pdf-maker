# -*- coding: utf-8 -*-
"""fix_labels.py - 跨章重复 \\label 去重（构建期修复工具）。

用途
----
整书合并前，检测在多个章节里被重复定义的 \\label（如 fig:pipeline / tab:cmp）。
LaTeX 取最后一次定义，会导致前面章节的 \\ref 全部指向错误编号。本工具把每个
冲突 label 按章重命名为 ``原label-ch<N>``，并同步改写该章内的
\\ref / \\cref / \\autoref / \\eqref / \\pageref。

安全检查
--------
若某冲突 label 被「未定义它的章节」跨章引用，则中止并提示手工处理，
绝不擅自改名（否则会产生 ?? 断链）。

是否调用 / 何时调用
------------------
由整书合并 SOP 在「所有单章通过之后、xelatex 之前」调用一次。
它不是每章必跑，而是整书级一次性修复；修改后需重跑 fix.py + 编译 + check_overflow。
用法：
    python fix_labels.py [ROOT]     # 默认当前目录
    python fix_labels.py /path/to/book

退出码：0 已完成（无论有无改动）；2 检测到跨章引用、中止改名。
"""
import re
import sys
import glob
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|cref|autoref|eqref|pageref)\{([^}]+)\}")


def collect(root: Path) -> list[str]:
    pats = [str(root / "第*章" / "第*章.tex"), str(root / "第*章.tex")]
    files = sorted({f for p in pats for f in glob.glob(p)})
    return files


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(".")
    files = collect(root)
    if not files:
        raise SystemExit(f"[fix_labels.py] 在 {root} 找不到 第*章/第*章.tex")

    texts: dict[str, str] = {}
    defined: dict[str, set[str]] = {}
    for f in files:
        chap = re.search(r"第(\d+)章", str(f))
        chap = chap.group(1) if chap else "?"
        txt = Path(f).read_text(encoding="utf-8")
        texts[chap] = txt
        for m in LABEL_RE.finditer(txt):
            defined.setdefault(m.group(1), set()).add(chap)

    collide = {l: chs for l, chs in defined.items() if len(chs) > 1}
    print(f"[fix_labels.py] 冲突 label 数：{len(collide)}")
    for l, chs in sorted(collide.items()):
        print(f"  {l}: 章节 {sorted(collide[l])}")

    # 跨章引用检查：冲突 label 被「未定义它的章节」引用 → 中止
    cross: dict[str, dict[str, int]] = {}
    for chap, txt in texts.items():
        for m in REF_RE.finditer(txt):
            lab = m.group(1)
            if lab in collide and chap not in defined[lab]:
                cross.setdefault(lab, {}).setdefault(chap, 0)
                cross[lab][chap] += 1
    if cross:
        print("\n!!! 检测到跨章引用，中止自动改名，请手工处理：")
        for l, cm in cross.items():
            print(f"  {l}: 被非定义章节引用 {cm}")
        return 2

    # 构建改名映射并应用
    rename: dict[str, dict[str, str]] = {}
    for l, chs in collide.items():
        rename[l] = {}
        for c in sorted(chs):
            newl = f"{l}-ch{c}"
            if newl in defined:
                raise SystemExit(f"[fix_labels.py] 目标名 {newl} 已存在，放弃。")
            rename[l][c] = newl

    print("\n应用改名：")
    for f in files:
        chap = re.search(r"第(\d+)章", str(f)).group(1)
        txt = texts[chap]
        changed = 0
        for l, chs in collide.items():
            if chap not in chs:
                continue
            newl = rename[l][chap]
            txt, n1 = re.subn(
                r"\\label\{" + re.escape(l) + r"\}", r"\\label{" + newl + "}", txt
            )
            txt, n2 = re.subn(
                r"\\(ref|cref|autoref|eqref|pageref)\{" + re.escape(l) + r"\}",
                r"\\\1{" + newl + "}",
                txt,
            )
            changed += n1 + n2
        if changed:
            Path(f).write_text(txt, encoding="utf-8")
            print(f"  ch{chap}: {changed} 处替换")
    print("\n完成。重跑 fix.py 并重新编译，再跑 check_overflow.py 确认 0 冲突。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
