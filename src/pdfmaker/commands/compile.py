# -*- coding: utf-8 -*-
"""compile —— 单章编译与日志体检（SOP 第 6/7 步的一体化封装）。

手工 SOP 曾要求作者 ``cd 第N章/`` 后手敲两遍 ``xelatex _tmp.tex`` 再跑 ``overflow``
——三个痛点：xelatex 不在 PATH 时直接 127（工具内部的 ``find_xelatex()`` 探测结果
帮不到手敲的 shell）；xelatex 两遍全量输出动辄数万字节，淹没终端；步骤分散易漏。

本命令把「定位 xelatex → 编译两遍 → 日志体检」收口为一步：

    python -m pdfmaker compile 4

- xelatex 定位与编排器 chapter / build 完全一致（--xelatex > .pdfmaker.toml >
  环境变量 PDFMAKER_XELATEX > PATH / 平台常见路径探测），无需手工 export PATH；
- 默认静默编译（quiet），失败时自动回显输出末尾 40 行；``--verbose`` 恢复全量透传；
- 编译通过后自动对 ``_tmp.log`` 跑 overflow 体检（可用 ``--no-overflow`` 跳过）。

前提：已跑过 ``fix N``（章目录内存在 ``_tmp.tex``）；缺失时给出提示而非崩溃。

退出码
------
0 编译两遍成功且日志体检通过（或按要求跳过体检）；
2 找不到 _tmp.tex / xelatex；1 编译失败或体检未过。
"""

import argparse
import sys
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.commands import overflow
from pdfmaker.commands.build import find_xelatex
from pdfmaker.core import paths, setup_utf8, xelatex as xel

setup_utf8()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker compile",
        description="单章编译一体化：定位 xelatex → _tmp.tex 编译两遍 → overflow 日志体检",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker compile 4              # 编译第 4 章（自动定位 xelatex）\n"
            "  python -m pdfmaker compile 4 --verbose    # 全量回显 xelatex 输出\n"
            "  python -m pdfmaker compile 4 --no-overflow  # 只编译，不体检日志\n\n"
            "前提：已跑过 `python -m pdfmaker fix 4`（章目录内存在 _tmp.tex）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    parser.add_argument("--xelatex", default=None,
                        help="xelatex 可执行文件路径（覆盖 .toml / 环境变量 / 运行时探测）")
    parser.add_argument("--verbose", action="store_true",
                        help="全量回显 xelatex 输出（默认静默，仅失败时回显末尾 40 行）")
    parser.add_argument("--no-overflow", action="store_true",
                        help="跳过编译后的 overflow 日志体检（不推荐）")
    args = parser.parse_args(argv)

    # 与 fix 同一套章节源解析：标准布局 第N章/第N章.tex，扁平布局 第N章.tex
    try:
        src = paths.resolve_source(args.chapter, "pdfmaker compile")
    except SystemExit:
        return 2
    chdir = src.parent
    tmp = chdir / "_tmp.tex"
    if not tmp.exists():
        print(f"[compile] 找不到 {tmp}；请先运行 `python -m pdfmaker fix {args.chapter}` "
              f"生成单章编译入口。", file=sys.stderr)
        return 2

    xelatex = args.xelatex or cfg.XELATEX_BIN or find_xelatex()
    if not xelatex:
        print("[compile] 未找到 xelatex（--xelatex / .pdfmaker.toml xelatex / "
              "PATH 探测均失败）。", file=sys.stderr)
        return 2

    quiet = not args.verbose
    for i in range(2):
        print(f"[compile] xelatex 第 {i + 1}/2 遍（{xelatex}）…")
        rc = xel.compile(
            xelatex, "-halt-on-error", "-interaction=nonstopmode", "_tmp.tex",
            cwd=str(chdir), quiet=quiet,
        )
        if rc != 0:
            print(f"[compile] xelatex 第 {i + 1} 遍失败（rc={rc}），中止。", file=sys.stderr)
            return 1

    pdf = chdir / "_tmp.pdf"
    if not pdf.exists():
        print(f"[compile] 两遍编译结束但未生成 {pdf}，请检查 _tmp.log。", file=sys.stderr)
        return 1
    print(f"[compile] 编译成功: {pdf} ({pdf.stat().st_size} bytes)")

    if args.no_overflow:
        print("[compile] 已跳过 overflow 日志体检（--no-overflow）。")
        return 0
    return overflow.main([str(chdir / "_tmp.log")])


if __name__ == "__main__":
    sys.exit(main())
