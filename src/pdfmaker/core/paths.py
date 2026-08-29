# -*- coding: utf-8 -*-
"""路径定位、控制台编码、章节源文件解析、模板定位。

本模块是所有命令共用的「定位真源」：章节源文件（第N章/第N章.tex 等）与
单章编译 preamble 模板（_tmp.tex）的解析规则只在这里实现一次。
"""

import re
import sys
from pathlib import Path

# __file__ 位于 src/pdfmaker/core/paths.py，上溯四级即仓库根（pdf-maker/）。
# 解析章节/定位 assets 模板的兜底基准目录；正常路径（CWD 或包内数据）命中时不会用到它。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 共用补丁片段占位符：_tmp.tex / main.tex 模板里出现一次，由 fix/scaffold 在生成时
# 替换为 templates/_preamble_shared.tex 的内容（中文 URL 支持 / 参考文献降级 /
# codeblock 环境 / 防溢出）。这是消除「双源漂移」的关键约定。
SHARED_PREAMBLE_PLACEHOLDER = "{{SHARED_PREAMBLE}}"


def setup_utf8() -> None:
    """强制 stdout/stderr 用 UTF-8（Windows 控制台默认编码兼容，try/except 包裹，幂等）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def stem_of(arg: str) -> str:
    """把命令行参数归一为章节目录/文件名 stem：附录X 原样，其余补「第…章」。"""
    return arg if arg.startswith("附录") else f"第{arg}章"


def resolve_source(arg: str, tool: str = "pdfmaker") -> Path:
    """定位章节 / 附录源文件（CWD 优先，脚本目录兜底）。

    参数
    ----
    arg  : 可以是
           - 数字 N           → 解析为 第N章
           - "附录X"          → 解析为 附录X
           - 直接 .tex 路径    → 若文件存在则原样返回（verify 支持传入路径）
    tool : 报错时显示的脚本名（便于用户定位是哪一步失败）。

    返回
    ----
    源文件 Path（绝对路径）。找不到时 raise SystemExit 并列出全部尝试路径。
    """
    p = Path(arg)
    if p.suffix == ".tex" and p.exists():
        return p.resolve()

    stem = stem_of(arg)
    tried = []
    for base in (Path.cwd(), REPO_ROOT):
        # __file__ 位于 src/pdfmaker/core/paths.py → 上溯三级到仓库根，再试 scripts 同级目录
        for cand in (base / stem / f"{stem}.tex", base / f"{stem}.tex"):
            tried.append(cand)
            if cand.exists():
                return cand.resolve()
    lines = "\n".join(f"    {c}" for c in dict.fromkeys(tried))
    raise SystemExit(
        f"[{tool}] 找不到 {stem}.tex，已尝试以下位置：\n{lines}\n"
        f"    提示：请在书稿项目根目录执行，或 cd 进章目录后再执行。"
    )


def mid_name_for(arg: str) -> str:
    """返回章节中间文件名，与 fix 的生成规则完全一致。

    数字 N → chN.tex；附录X → 附录X_ch.tex。
    """
    return f"{arg}_ch.tex" if arg.startswith("附录") else f"ch{arg}.tex"


def workdir_for(arg: str) -> Path:
    """定位章节工作目录（即 _tmp.pdf 所在目录），cleanup 用。

    依次尝试：<CWD>/<stem> → <CWD> → <repo>/<stem> → <repo>；
    优先返回含 _tmp.pdf 的目录；否则返回首个存在的目录；兜底返回 <CWD>/<stem>。
    """
    stem = stem_of(arg)
    repo = REPO_ROOT
    cands = [Path.cwd() / stem, Path.cwd(), repo / stem, repo]
    for d in cands:
        if (d / "_tmp.pdf").exists():
            return d
    for d in cands:
        if d.exists():
            return d
    return Path.cwd() / stem


def _template_from_package(name: str) -> Path | None:
    """从包内资源（pdfmaker.templates）读取模板；不可用时返回 None。"""
    try:
        from importlib.resources import files

        p = files("pdfmaker.templates").joinpath(name)
        if p.is_file():
            return Path(str(p))
    except Exception:
        pass
    return None


def find_tmp_template() -> Path:
    """定位单章编译 preamble 模板 _tmp.tex（fix.py 生成 _tmp.tex 的唯一真源）。

    模板经包内资源 pdfmaker.templates 定位（CWD 优先、包数据兜底），缺失即报错。
    """
    p = _template_from_package("_tmp.tex")
    if p is not None:
        return p
    raise SystemExit(
        "[pdfmaker] 找不到 _tmp.tex 模板（包数据 pdfmaker.templates 缺失）。"
    )


def find_main_template() -> Path:
    """定位整书主控模板 main.tex（scaffold 命令用于初始化书稿）。"""
    p = _template_from_package("main.tex")
    if p is not None:
        return p
    raise SystemExit(
        "[pdfmaker] 找不到 main.tex 模板（包数据 pdfmaker.templates 缺失）。"
    )


def find_preamble_shared() -> Path:
    """定位共用补丁片段 _preamble_shared.tex（{{SHARED_PREAMBLE}} 的唯一真源）。"""
    p = _template_from_package("_preamble_shared.tex")
    if p is not None:
        return p
    raise SystemExit(
        "[pdfmaker] 找不到 _preamble_shared.tex（共用补丁片段缺失，无法解析 {{SHARED_PREAMBLE}}）。"
    )


def resolve_shared_preamble(text: str) -> str:
    """将模板文本里的 ``{{SHARED_PREAMBLE}}`` 替换为 _preamble_shared.tex 的内容。

    占位符缺失则原样返回（兼容旧模板）；出现多次则全部替换。替换失败（片段缺失）
    会抛 SystemExit，由调用方转为非零退出。
    """
    if SHARED_PREAMBLE_PLACEHOLDER not in text:
        return text
    shared = find_preamble_shared().read_text(encoding="utf-8")
    return text.replace(SHARED_PREAMBLE_PLACEHOLDER, shared)
