# -*- coding: utf-8 -*-
"""xref —— 跨章文字引用与 \\ref 安全性校验（合并前静态预检）。

pdf-maker 的「红线」规定：跨章 \\ref 不可用（编译后会指向错误编号），章节间互指
必须写成纯文本「第~N~章」。但这带来一个隐患——作者盲写「第~N~章」时可能写错章号
（超出范围、或指向不存在的章）。本工具在合并前做静态预检，把这种盲写错误挡在
编译之前。

检查项
------
1. 文字引用「第X章」（含 第3章 / 第 3 章 / 第~3~章 写法）的章号 X 必须在
   [1, max_chapter] 范围内，否则阻断（写错/越界章号）。
2. 跨章 \\ref / \\cref / \\autoref / \\eqref / \\pageref：若引用的 \\label 定义在其他
   章节，属「跨章引用」——按 pdf-maker 红线判定为阻断，应改为纯文本「第~N~章」。
3. 悬空 \\ref（引用的 \\label 全书都未定义）：warning 级（编译期 overflow 也会抓）。

退出码
------
0 全部通过（仅 warning 不计阻断）；1 存在阻断级问题（越界文字引用 / 跨章 \\ref）；
2 目标解析失败或未找到章节。
"""

import argparse
import re
import sys
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.core import (
    chapter_range,
    collect_chapters,
    resolve_source,
    setup_utf8,
    strip_blocks,
)
from pdfmaker.core.watchdog import ScanTimeoutError, scan_watchdog

setup_utf8()

LABEL_RE = re.compile(r"\\label\{([^}]+)\}")
REF_RE = re.compile(r"\\(?:ref|cref|autoref|eqref|pageref)\{([^}]+)\}")
# 第3章 / 第 3 章 / 第~3~章 都能匹配
TEXTREF_RE = re.compile(r"第[~\s]*(\d+)[~\s]*章")


def _ch_num_of(path: Path) -> int | None:
    """从路径解析数字章号；非数字章（附录等）返回 None。"""
    m = re.search(r"第(\d+)章", str(path))
    return int(m.group(1)) if m else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker xref",
        description="跨章文字引用与 \\ref 安全性校验（合并前静态预检）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker xref .     # 校验整书全部章节引用\n"
            "  python -m pdfmaker xref 4     # 校验第 4 章（仍会扫描全书以构建 label 地图）\n"
            "  python -m pdfmaker xref 第4章/第4章.tex"
        ),
    )
    parser.add_argument("target", nargs="?", default=".",
                        help="书稿根目录（'.'）或章节 N / .tex 路径，默认整书")
    parser.add_argument("--self-only", action="store_true",
                        help="仅校验作为 target 的单个 .tex 文件（仍构建全书 label 地图，"
                             "但不因其它章节的问题而阻断；供单章 SOP 早期自检）")
    parser.add_argument("--expected", type=int, default=None,
                        help="声明全书总章数上限（覆盖 chapter_range 的上限）。渐增写作时，"
                             "缺省则用已存在目录推导的范围。")
    args = parser.parse_args(argv)

    # 扫描看门狗：正则扫描若指数回溯会永久空转，超时按阻断处理（exit 1）
    try:
        with scan_watchdog(cfg.SCAN_TIMEOUT, "xref"):
            return _run(args)
    except ScanTimeoutError:
        print(
            f"[xref] 扫描超过 {cfg.SCAN_TIMEOUT:g}s 时限（疑似正则回溯或病态输入），"
            f"exit 1 阻断。请检查章节源码中的未闭合定界符，"
            f"或经 PDFMAKER_SCAN_TIMEOUT / .pdfmaker.toml 的 scan_timeout 放宽时限。",
            file=sys.stderr,
        )
        return 1


def _run(args) -> int:
    """xref 的引用校验主体（在 main 的看门狗时限内运行）。"""
    p = Path(args.target)
    if args.target in (".", "..") or p.is_dir():
        root = p.resolve() if p.is_dir() else Path.cwd().resolve()
        files = collect_chapters(root)
        single_target = None
    else:
        try:
            single = resolve_source(args.target, "pdfmaker xref")
            # 章节文件位于 第N章/（或 附录X/）子目录时，书稿根是再上一级；
            # 旧扁平布局（第N章.tex 直接在项目根）时书稿根即父目录。
            # 注意方向不能反：root 必须是「含全部章节的目录」，否则
            # collect_chapters 只会扫到目标章自身，全书 label 地图残缺，
            # --self-only 与跨章引用判定都会失效。
            if single.parent.name.startswith(("第", "附录")):
                root = single.parent.parent
            else:
                root = single.parent
            files = collect_chapters(root)
            if not files:
                files = [single]
            single_target = single
        except SystemExit:
            return 2

    if not files:
        print(f"[xref] 在 {root} 下未找到任何章节 .tex")
        return 2

    lo, hi = chapter_range(root)
    if args.expected is not None and args.expected > hi:
        hi = args.expected
    has_numeric = (lo, hi) != (0, 0)
    scope_note = f"（--expected {args.expected}）" if args.expected is not None else ""
    print(f"[xref] 章节范围: {lo}–{hi}{scope_note}；扫描 {len(files)} 个章节文件")

    # ---- 构建全局 label → 所属章号 地图 ----
    label_owner: dict[str, int] = {}
    file_labels: dict[Path, set[str]] = {}
    for f in files:
        txt = Path(f).read_text(encoding="utf-8")
        labels = set(LABEL_RE.findall(txt))
        file_labels[f] = labels
        ch = _ch_num_of(f)
        for lab in labels:
            label_owner[lab] = ch if ch is not None else -1

    blocking: list[str] = []
    warnings: list[str] = []

    for f in files:
        # --self-only 时仅报告作为 target 的章节文件，避免单章 SOP 因
        # 其它章节的历史问题而误阻断（仍用全书 label 地图判定跨章引用）。
        if args.self_only and single_target is not None:
            if Path(f).resolve() != Path(single_target).resolve():
                continue
        ch = _ch_num_of(f)
        txt = Path(f).read_text(encoding="utf-8")
        pure = strip_blocks(txt)  # 去掉表格/图/verbatim/verb，避免逐字块误判
        name = f.name

        # ---- 1. 文字引用「第X章」章号范围 ----
        # 若全书无数字章（如纯附录/未分章草稿），chapter_range 返回 (0,0)，
        # 此时无法判定合法范围，跳过越界检查，避免误伤全部「第N章」文字引用。
        if has_numeric:
            for m in TEXTREF_RE.finditer(pure):
                x = int(m.group(1))
                if x < lo or x > hi:
                    blocking.append(
                        f"{name}: 文字引用「第{x}章」越界（合法范围 {lo}–{hi}）"
                    )

        # ---- 2/3. \ref 类：跨章 / 悬空 ----
        for rm in REF_RE.finditer(txt):
            key = rm.group(1)
            owner = label_owner.get(key)
            if owner is None:
                warnings.append(f"{name}: \\ref{{{key}}} 全书未定义（悬空，编译会 ??）")
            elif ch is not None and owner != ch:
                blocking.append(
                    f"{name}: \\ref{{{key}}} 指向第 {owner} 章的 label（跨章引用，"
                    "pdf-maker 红线禁止；应改为纯文本「第~N~章」）"
                )

    # ---- 汇总 ----
    print("\n结果：")
    if warnings:
        print(f"  警告({len(warnings)}，不阻断):")
        for w in warnings[:20]:
            print(f"    - {w}")
    if blocking:
        print(f"  阻断({len(blocking)}，必须修正):")
        for b in blocking:
            print(f"    - {b}")
        print(f"\n[FAIL] 存在 {len(blocking)} 项阻断级引用问题，exit 1。修正后重跑。")
        return 1
    print("  [OK] 文字引用章号均在范围内，且无跨章 \\ref（exit 0）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
