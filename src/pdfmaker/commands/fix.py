# -*- coding: utf-8 -*-
"""fix —— 单章 TeX 预处理（章节源 → 可编译成品）。

把作者手写的章节源文件（标准布局 第N章/第N章.tex，兼容旧扁平 第N章.tex；
附录 附录X/附录X.tex）转换为可直接交给 xelatex 编译的成品，并读取包内模板
_tmp.tex 生成单章独立编译入口。

处理项
------
1. 规范化：统一调用 ``pdfmaker.core.normalize_text()``（= url_to_href + wrap_tikz
   + fix_glyphs + relax_long_texttt）。其中 wrap_tikz 给每个 tikzpicture 套
   adjustbox{max width=\\textwidth}，只缩放超宽图，正常图保持原样（幂等）。
   该规范化逻辑与整书合并路径 build 共用，是「单一规范化真源」，
   确保单章与合并两条流水线完全一致。
2. 写出英文名中间文件 chN.tex（避免中文文件名在部分工具链下乱码）。
3. 生成 _tmp.tex：读取包内模板 _tmp.tex（preamble 唯一真源），将其中的
   {{SHARED_PREAMBLE}} 替换为共用补丁片段（_preamble_shared.tex），再将
   \\input{CHAPTER_TEX} 占位行替换为实际章节中间文件名后写出。

退出码
------
0 成功；源文件缺失、模板缺失或模板损坏时非零退出。
"""

import argparse
import sys
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.core.normalize import normalize_text
from pdfmaker.core.paths import (
    find_tmp_template,
    mid_name_for,
    resolve_shared_preamble,
    resolve_source,
    setup_utf8,
)
from pdfmaker.core.watchdog import ScanTimeoutError, scan_watchdog

setup_utf8()

# 占位行：模板里唯一会被替换成真实章节文件名的地方
PLACEHOLDER = "CHAPTER_TEX"


def _cwd_hint() -> None:
    """若当前目录疑似 scripts/ 工具目录，提示用户 cd 到书稿项目根再执行。"""
    if Path.cwd().name == "scripts":
        print(
            "[fix] 提示：当前似乎在脚本/工具目录运行，很可能找不到章节源文件。\n"
            "    推荐：先 cd 到书稿项目根目录（含 第N章/ 子目录），再执行\n"
            "           python -m pdfmaker fix 4\n"
            "    或 cd 进 第N章/ 目录后执行同一命令。",
            file=sys.stderr,
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker fix",
        description="单章 TeX 预处理：URL 规范化 + 图宽上限 + 生成 chN.tex/_tmp.tex",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker fix 4           # 处理第 4 章（在项目根目录执行）\n"
            "  python -m pdfmaker fix 附录A        # 处理附录 A\n"
            "  cd 第4章 && python -m pdfmaker fix 4  # 也可 cd 进章目录执行\n\n"
            "章节源文件约定: 第N章/第N章.tex（或旧扁平 第N章.tex）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args(argv)

    # 扫描看门狗：normalize_text 的正则若指数回溯会永久空转，超时按阻断处理（exit 1）
    try:
        with scan_watchdog(cfg.SCAN_TIMEOUT, "fix"):
            return _run(args)
    except ScanTimeoutError:
        print(
            f"[fix] 规范化超过 {cfg.SCAN_TIMEOUT:g}s 时限（疑似正则回溯或病态输入），"
            f"exit 1 阻断。请检查章节源码中的未闭合定界符，"
            f"或经 PDFMAKER_SCAN_TIMEOUT / .pdfmaker.toml 的 scan_timeout 放宽时限。",
            file=sys.stderr,
        )
        return 1


def _run(args) -> int:
    """fix 的规范化与模板生成主体（在 main 的看门狗时限内运行）。"""
    _cwd_hint()

    src = resolve_source(args.chapter, "pdfmaker fix")
    # 单一规范化真源：URL → href + TikZ 图宽上限 + 字形修复（与 build 合并路径完全一致）
    text = normalize_text(src.read_text(encoding="utf-8"))

    mid_name = mid_name_for(args.chapter)
    dst = src.parent / mid_name
    dst.write_text(text, encoding="utf-8")

    tpl = find_tmp_template()
    if not tpl or not Path(tpl).exists():
        raise SystemExit(
            "[fix] 找不到 _tmp.tex 模板；请保持包安装完整（模板位于 pdfmaker.templates）。"
        )
    tpl_text = Path(tpl).read_text(encoding="utf-8")
    # 解析共用补丁片段占位符（消除 _tmp.tex / main.tex 双源漂移）；缺失则原样返回，兼容旧模板。
    tpl_text = resolve_shared_preamble(tpl_text)
    target = "\\input{" + PLACEHOLDER + "}"
    if target not in tpl_text:
        raise SystemExit(
            f"[fix] 模板 {tpl} 缺少占位行 {target}，无法生成单章编译入口。"
        )
    tpl_text = tpl_text.replace(target, "\\input{" + dst.name + "}")
    tmp = src.parent / "_tmp.tex"
    tmp.write_text(tpl_text, encoding="utf-8")

    print(f"[fix] 源: {src} -> 中间文件: {dst.name} ({dst.stat().st_size} bytes)")
    print(f"[fix] 单章编译入口: {tmp} ({tmp.stat().st_size} bytes)")
    print(f"[fix] 下一步: python -m pdfmaker compile {args.chapter}"
          "（自动定位 xelatex，编译两遍 + 日志体检）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
