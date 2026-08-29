# -*- coding: utf-8 -*-
"""lint —— 单章快速预检（编译前边写边查，不阻断）。

把 check（字数门禁关闭）与 balance（结构/引用均衡）合并成一次「边写边查」快速体检，
把所有潜在阻断项（TikZ 坏节点 / 未转义 & / 孤儿引用 / 截断 URL / 缺图缺表 / 欠篇幅）
一次性列出，便于作者在 xelatex 之前修掉。与 SOP 的区别：lint 永远 exit 0（仅提示），
不中止写作流程——作者可反复 ``python -m pdfmaker lint N`` 自查。

退出码：0（纯提示，不阻断）。
"""

import argparse
import sys

from pdfmaker.core import resolve_source, setup_utf8

setup_utf8()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker lint",
        description="单章快速预检（check + balance 合并，仅提示不阻断）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker lint 4    # 第 4 章边写边查\n"
            "  python -m pdfmaker lint 附录A # 附录 A\n\n"
            "永远 exit 0（提示级），不阻断写作；正式交付仍走 chapter SOP。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args(argv)

    # 确认源文件存在（顺带触发 resolve_source 的路径校验）
    try:
        resolve_source(args.chapter, "pdfmaker lint")
    except SystemExit:
        return 2

    # 复用 check / balance，但 lint 一律不阻断：
    # - check 关闭字数门禁（--no-gate），仅展示字数与风险预检；
    # - balance 的阻断项照常打印，但我们忽略其 exit 码，统一返回 0。
    from pdfmaker.commands import balance, check

    print("\n========== [lint] check（字数门禁已关闭） ==========")
    check.main([args.chapter, "--no-gate"])
    print("\n========== [lint] balance（阻断项仅提示不中止） ==========")
    balance.main([args.chapter])

    print("\n[lint] 以上为提示级预检，exit 0。正式交付请跑 `python -m pdfmaker chapter N`。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
