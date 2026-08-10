# -*- coding: utf-8 -*-
"""common.py - pdf-maker 脚本共享工具（路径定位 / 编码 / 文本统计）。

用途
----
集中存放被多个脚本复用的纯函数，消除「每个脚本各写一份 resolve_source /
strip_blocks」导致的多份漂移补丁（历史版本正是因此越改越乱、指向不清）。

提供
----
- setup_utf8()      : Windows 控制台中文输出修复（try/except 包裹，幂等）。
- HERE              : 本脚本（common.py）所在目录，即 scripts/。
- resolve_source()  : 把 N / 附录X / 直接 .tex 路径 解析为章节源文件绝对路径。
- mid_name_for()    : 返回章节中间文件名（chN.tex / 附录X_ch.tex），与 fix.py 一致。
- workdir_for()     : 解析章节工作目录（含 _tmp.pdf 的目录），cleanup 用。
- strip_blocks()    : 去掉表格 / 图 / verbatim / verb 逐字块，正文字数统计用。
- chinese_count()   : 统计中文字数。

是否调用
--------
被 fix.py / check.py / check_balance.py / verify_urls.py / cleanup.py 显式 import。
reader.py / track_materials.py / check_overflow.py / fix_labels.py 仅复用 setup_utf8()。

退出码
------
本模块不直接退出进程；仅 resolve_source() 在找不到源文件时 raise SystemExit。
"""
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent


def setup_utf8() -> None:
    """强制 stdout/stderr 用 UTF-8（Windows 控制台 GBK 回退 bug 修复）。"""
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError):
        pass


def _stem_of(arg: str) -> str:
    """把命令行参数归一为章节目录/文件名 stem：附录X 原样，其余补「第…章」。"""
    return arg if arg.startswith("附录") else f"第{arg}章"


def resolve_source(arg: str, tool: str = "pdf-maker") -> Path:
    """定位章节 / 附录源文件（CWD 优先，脚本目录兜底）。

    参数
    ----
    arg  : 可以是
           - 数字 N           → 解析为 第N章
           - "附录X"          → 解析为 附录X
           - 直接 .tex 路径    → 若文件存在则原样返回（verify_urls 支持传入路径）
    tool : 报错时显示的脚本名（便于用户定位是哪一步失败）。

    返回
    ----
    源文件 Path（绝对路径）。找不到时 raise SystemExit 并列出全部尝试路径。

    说明：项目根目录执行时匹配 第N章/第N章.tex；cd 进章目录执行时匹配
    扁平 第N章.tex；两种调用姿势都支持。所有脚本共用本函数，保证定位规则唯一。
    """
    p = Path(arg)
    if p.suffix == ".tex" and p.exists():
        return p.resolve()

    stem = _stem_of(arg)
    tried = []
    for base in (Path.cwd(), HERE):
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
    """返回章节中间文件名，与 fix.py 的生成规则完全一致。

    数字 N → chN.tex；附录X → 附录X_ch.tex。
    """
    return f"{arg}_ch.tex" if arg.startswith("附录") else f"ch{arg}.tex"


def workdir_for(arg: str) -> Path:
    """定位章节工作目录（即 _tmp.pdf 所在目录），cleanup 用。

    依次尝试：<CWD>/<stem> → <CWD> → <scripts>/<stem> → <scripts>；
    优先返回含 _tmp.pdf 的目录；否则返回首个存在的目录；兜底返回 <CWD>/<stem>。
    """
    stem = _stem_of(arg)
    cands = [Path.cwd() / stem, Path.cwd(), HERE / stem, HERE]
    for d in cands:
        if (d / "_tmp.pdf").exists():
            return d
    for d in cands:
        if d.exists():
            return d
    return Path.cwd() / stem


_BLOCK_RE = re.compile(
    r"\\begin\{table\}.*?\\end\{table\}"
    r"|\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}"
    r"|\\begin\{verbatim\}.*?\\end\{verbatim\}"
    r"|\\verb([^a-zA-Z]).*?\1",
    flags=re.DOTALL,
)


def strip_blocks(text: str) -> str:
    """去掉表格 / 图 / verbatim / \\verb 逐字块，避免它们的内容混入正文字数。"""
    return _BLOCK_RE.sub("", text)


def chinese_count(text: str) -> int:
    """统计中文字符数（用于内容密度 / 小节字数评估）。"""
    return len(re.findall(r"[一-鿿]", text))


if __name__ == "__main__":
    # common.py 仅作库使用，直接运行给出提示。
    print("common.py 是 pdf-maker 的共享工具模块，请由其他脚本 import，不要单独运行。")
