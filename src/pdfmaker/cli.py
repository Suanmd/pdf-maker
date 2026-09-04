# -*- coding: utf-8 -*-
"""cli —— pdfmaker 命令行入口：子命令分发。

每个子命令对应 ``pdfmaker.commands`` 下的一个模块，模块自身暴露
``main(argv=None)`` 并负责 argparse 解析。两种等价调用方式：

    python -m pdfmaker build .
    pdfmaker build .            # 安装后（pip install）可用的控制台脚本

也可直接用 ``python -m pdfmaker.commands.<name>`` 运行单个模块。
"""

import sys

import pdfmaker.core.config as cfg
from pdfmaker import __version__
from pdfmaker.commands import (
    balance,
    build,
    chapter,
    check,
    cleanup,
    compile,
    fix,
    labels,
    lint,
    overflow,
    reader,
    scaffold,
    track,
    verify,
    xref,
)

# 子命令名 -> 模块（模块提供 main(argv)）
_SUBCOMMANDS = {
    "fix": fix,
    "check": check,
    "balance": balance,
    "lint": lint,
    "compile": compile,
    "overflow": overflow,
    "xref": xref,
    "verify": verify,
    "build": build,
    "chapter": chapter,
    "cleanup": cleanup,
    "labels": labels,
    "reader": reader,
    "track": track,
    "scaffold": scaffold,
}

_HELP = """pdfmaker v{ver} — 中文 LaTeX 报告工程化工具

用法:
  python -m pdfmaker <子命令> [参数...]

子命令:
  fix        单章预处理（URL 规范化 + 图宽上限 + 生成 chN.tex/_tmp.tex）
  check      章节内容结构统计 + 编译前风险预检
  balance    章节结构与引用均衡性检查（阻断/建议分明）
  lint       单章快速预检（check+balance 合并，仅提示不阻断）
  compile    单章编译一体化（自动定位 xelatex → 编译两遍 → overflow 体检）
  overflow   编译日志体检（Overfull / 缺失字符 / 重复 label / 断链 / Fatal）
  xref       跨章文字引用与 \\ref 安全性校验（合并前预检）
  verify     联网验活全部 URL（exit 0/1/2，带重试与截断检测）
  build      整书合并（labels → xref → 规范化 → xelatex×2 → 体检）
  chapter    单章全流程 SOP 一键编排（reader → fix → check → balance → verify → xelatex×2 → overflow → cleanup → track）
  cleanup    单章编译后清理（落盘成品 PDF + 归档中间文件）
  labels     跨章重复 \\label 去重
  reader     素材强制阅读三阶段校验（index/chunk/verify/ingest/toc）
  track      章节 ↔ 素材阅读状态追踪（materials.json）
  scaffold   书稿骨架生成：整书初始化（main.tex + 章节占位）或单章从素材生成合规富骨架

常用示例:
  python -m pdfmaker fix 4              # 处理第 4 章
  python -m pdfmaker build .            # 合并整书，产出 main.pdf
  python -m pdfmaker verify .           # 验活整书全部 URL
  python -m pdfmaker scaffold my-book   # 初始化一本书稿项目
  python -m pdfmaker --help             # 本帮助
  python -m pdfmaker <子命令> --help     # 子命令帮助
"""


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv or argv[0] in ("-h", "--help", "help"):
        print(_HELP.format(ver=__version__))
        return 0
    if argv[0] in ("-V", "--version", "version"):
        print(f"pdfmaker {__version__}")
        return 0

    name = argv[0]
    mod = _SUBCOMMANDS.get(name)
    if mod is None:
        print(f"[pdfmaker] 未知子命令: {name}\n")
        print(_HELP.format(ver=__version__))
        return 2

    # 自动加载项目级配置（.pdfmaker.toml），使所有命令（含编排器）运行时继承项目设置。
    # 环境变量优先级最高，其次 toml，最后默认值；找不到配置文件时静默降级。
    cfg.load_project_config()
    cfg.apply_project_config()

    # 把剩余参数交给子命令模块自行解析（含 reader/track 的二级子命令）。
    # 顶层守卫：SystemExit（argparse 参数错误 / 各命令主动报错）原样透传；
    # 其余未预期异常统一收敛为「清晰错误信息 + 退出码 1」，避免向用户抛原始 traceback。
    try:
        return mod.main(argv[1:])
    except SystemExit:
        raise
    except Exception as e:  # noqa: BLE001 — 顶层兜底，必须收敛所有意外崩溃
        print(
            f"[pdfmaker] 未预期的异常（{type(e).__name__}）: {e}\n"
            f"    请带上本信息反馈；如可复现，附上复现步骤。",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    sys.exit(main())
