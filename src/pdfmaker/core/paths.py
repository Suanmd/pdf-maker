# -*- coding: utf-8 -*-
"""core.paths —— 路径定位、控制台编码与模板定位。

本模块是所有命令共用的「定位真源」：章节源文件（第N章/第N章.tex 等）与
包内 LaTeX 模板（_tmp.tex / main.tex / _preamble_shared.tex）的解析规则
只在这里实现一次，各命令不得再写副本。
"""

import re
import sys
from pathlib import Path

# __file__ 位于 src/pdfmaker/core/paths.py，上溯四级即仓库根（pdf-maker/）。
# 仅作解析章节源文件的兜底基准目录；正常路径（CWD）命中时不会用到。
REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent

# 共用补丁片段占位符：_tmp.tex / main.tex 模板里出现一次，由 fix / scaffold 在生成时
# 替换为 templates/_preamble_shared.tex 的内容（中文 URL 支持 / 参考文献降级 /
# codeblock 环境 / 防溢出）。这是消除「双源漂移」的关键约定。
SHARED_PREAMBLE_PLACEHOLDER = "{{SHARED_PREAMBLE}}"


def setup_utf8() -> None:
    """强制 stdout/stderr 使用 UTF-8 输出。

    兼容默认编码非 UTF-8 的控制台 / 重定向环境；macOS / Linux 终端下为幂等
    no-op。流无 reconfigure（如 StringIO）或流已关闭时静默降级，不影响主流程。
    """
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass


def stem_of(arg: str) -> str:
    """把命令行参数归一为章节目录/文件名 stem：附录X 原样，其余补「第…章」。"""
    return arg if arg.startswith("附录") else f"第{arg}章"


def resolve_source(arg: str, tool: str = "pdfmaker") -> Path:
    """定位章节 / 附录源文件（CWD 优先，仓库根兜底）。

    参数
    ----
    arg : 章节定位符，可以是
          - 数字 N → 解析为 第N章
          - "附录X" → 解析为 附录X
          - 直接 .tex 路径 → 若文件存在则原样返回（verify 支持传入路径）
    tool : 报错时显示的命令名（便于用户定位是哪一步失败）。

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
        for cand in (base / stem / f"{stem}.tex", base / f"{stem}.tex"):
            tried.append(cand)
            if cand.exists():
                return cand.resolve()
    lines = "\n".join(f"    {c}" for c in dict.fromkeys(tried))
    raise SystemExit(
        f"[{tool}] 找不到 {stem}.tex，已尝试以下位置：\n{lines}\n"
        f"    提示：请在书稿项目根目录执行，或 cd 进章目录后再执行。"
    )


def looks_like_project_root(d: Path) -> bool:
    """判断目录是否像书稿项目根：含 main.tex / materials.json / 既有章节结构之一。

    用于「创建新章目录/文件」前的守卫：在错误 CWD（如上级目录、素材仓库）下
    自动生成 第N章/ 骨架，会污染无关目录且事后难以察觉（真实事故来源）。
    """
    d = Path(d)
    if (d / "main.tex").exists() or (d / "materials.json").exists():
        return True
    if any(d.glob("第*章")) or any(d.glob("第*章.tex")):
        return True
    if any(d.glob("附录*")):
        return True
    return False


def find_material_nearby(name: str, base: Path | None = None) -> Path | None:
    """在 base（默认 CWD）的一级子目录里按文件名探测素材（``*/<name>`` 与 ``*/*/<name>``）。

    用于「裸文件名找不到」时给出「你是不是想在那个子目录项目里跑？」的诊断提示。
    返回唯一命中路径；零命中或多命中（歧义，不敢猜）均返回 None。
    """
    base = Path(base) if base is not None else Path.cwd()
    hits = [h for h in sorted(base.glob(f"*/{name}")) if h.is_file()]
    hits += [h for h in sorted(base.glob(f"*/*/{name}")) if h.is_file()]
    uniq = list(dict.fromkeys(hits))
    return uniq[0] if len(uniq) == 1 else None


def mid_name_for(arg: str) -> str:
    """返回章节中间文件名，与 fix 的生成规则完全一致：数字 N → chN.tex；附录X → 附录X_ch.tex。"""
    return f"{arg}_ch.tex" if arg.startswith("附录") else f"ch{arg}.tex"


def resolve_material(arg: str, chapter: str | None = None, base: Path | None = None) -> Path:
    """定位素材文件：依次尝试给定路径、章节文件夹、项目根。

    素材存放约定：多章书稿（标准布局）素材放在**章节文件夹**内
    （``第N章/素材-第N章.md``），与章节源文件同级；扁平单章项目素材在项目根。
    本函数让 ``--material 素材-第N章.md`` 裸文件名在两种约定下都能解析。

    参数
    ----
    arg : 素材路径（绝对或相对 CWD）。
    chapter : 章节号（数字 N 或 附录X）；给出时额外尝试 ``<base>/<第N章>/<文件名>``。
    base : 项目根目录（默认 CWD）。

    返回
    ----
    命中的素材 Path；找不到时原样返回 arg（由下游 reader / scaffold 给出缺失报错），
    本函数只做定位增强、不阻断。
    """
    p = Path(arg)
    if p.exists() or p.is_absolute():
        return p
    # base 缺省（CWD）时用相对候选路径，保持「相对进、相对出」，
    # 使 track 记录到 materials.json 的路径可移植；显式给 base 时按其拼接。
    prefix = base if base is not None else Path(".")
    if chapter is not None:
        cand = prefix / stem_of(chapter) / p.name  # 多章约定：素材在章节文件夹
        if cand.exists():
            return cand
    cand = prefix / p.name  # 扁平/旧约定：素材在项目根
    if cand.exists():
        return cand
    return p


def workdir_for(arg: str) -> Path:
    """定位章节工作目录（即 _tmp.pdf 所在目录），cleanup 用。

    依次尝试：<CWD>/<stem> → <CWD> → <repo>/<stem> → <repo>；
    优先返回含 _tmp.pdf 的目录；否则返回首个存在的目录；兜底返回 <CWD>/<stem>。
    """
    stem = stem_of(arg)
    cands = [Path.cwd() / stem, Path.cwd(), REPO_ROOT / stem, REPO_ROOT]
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
    """定位单章编译 preamble 模板 _tmp.tex（fix 生成 _tmp.tex 的唯一真源）。"""
    p = _template_from_package("_tmp.tex")
    if p is not None:
        return p
    raise SystemExit(
        "[pdfmaker] 找不到 _tmp.tex 模板（包数据 pdfmaker.templates 缺失）。"
    )


def find_main_template() -> Path:
    """定位整书主控模板 main.tex（scaffold 初始化书稿用）。"""
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
    """将模板文本里独立成行的 ``{{SHARED_PREAMBLE}}`` 替换为 _preamble_shared.tex 的内容。

    关键约束：只替换「整行恰好是占位符」（允许首尾空白）的行，不替换出现在
    注释 / 散文里的占位符提及——否则多行片段会被注入注释行中部，首行继承 %
    而后续行裸奔，直接炸掉编译（Missing \\begin{document}）。
    占位符缺失（无独立行）则原样返回（兼容旧模板）；片段缺失会抛 SystemExit。
    """
    lines = text.split("\n")
    if not any(line.strip() == SHARED_PREAMBLE_PLACEHOLDER for line in lines):
        return text
    shared = find_preamble_shared().read_text(encoding="utf-8")
    out = [
        shared.rstrip("\n") if line.strip() == SHARED_PREAMBLE_PLACEHOLDER else line
        for line in lines
    ]
    return "\n".join(out)
