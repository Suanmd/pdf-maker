# -*- coding: utf-8 -*-
"""fix.py - 单章 TeX 预处理（章节源 → 可编译成品）。

用途
----
把作者手写的章节源文件（标准 第N章/第N章.tex，兼容旧扁平 第N章.tex；
附录 附录X/附录X.tex）转换为可直接交给 xelatex 编译的成品，并读取
assets/templates/_tmp.tex 模板生成单章独立编译所需的 _tmp.tex
（preamble 唯一真源）。

处理项
------
1. URL 规范化：把 \\url{...} 改写为 \\href{raw-url}{display-text}，并对显示文本里的
   LaTeX 特殊字符做转义（避免进入 math mode 报错）。
2. 图片宽度上限：给每个 tikzpicture 套 adjustbox{max width=\textwidth}，
   只缩放超宽图，正常图保持原样（幂等，已包裹不重复套）。
3. 写出英文名中间文件 chN.tex（避免中文文件名在部分工具链下乱码）。
4. 生成 _tmp.tex：读取 assets/templates/_tmp.tex 模板（preamble 唯一真源），
   将其中的 \\input{CHAPTER_TEX} 占位行替换为实际章节中间文件名后写出。

是否调用
--------
由单章编译 SOP 在「写正文之后、xelatex 之前」调用，每章必跑（不可替代）。

调用时机
--------
python fix.py [CH_NUM]        # 默认第 1 章
python fix.py 3               # 处理第 3 章
python fix.py 附录A           # 处理附录 A

路径解析规则
------------
统一由 common.resolve_source() 定位源文件：<CWD>/<stem>/<stem>.tex →
<CWD>/<stem>.tex → <scripts>/<stem>/<stem>.tex → <scripts>/<stem>.tex。
因此从书稿项目根目录用全路径调用即可（skill 装在哪都行），也可 cd 进章目录执行。

退出码：0 成功；源文件缺失、模板缺失或模板损坏时非零退出。
"""
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote

from common import HERE, setup_utf8, resolve_source, mid_name_for

setup_utf8()

# 占位行：模板里唯一会被替换成真实章节文件名的地方
PLACEHOLDER = "CHAPTER_TEX"


def url_to_href(text: str) -> str:
    """将 \\url{...} 改写为 \\href{raw}{display-escaped}。

    - URL 保持原始（不预 percent-encode，交由 hyperref 处理）。
    - 显示文本里的 LaTeX 特殊字符必须转义，否则会进入 math mode 报错。
    """

    def repl(m: re.Match) -> str:
        url = m.group(1)
        try:
            decoded = unquote(url)
        except Exception:
            decoded = url
        display = (
            decoded.replace("\\", r"\textbackslash{}")
            .replace("_", r"\_")
            .replace("&", r"\&")
            .replace("$", r"\$")
            .replace("#", r"\#")
            .replace("%", r"\%")
        )
        return r"\href{" + url + "}{" + display + "}"

    return re.sub(r"\\url\{([^{}]+)\}", repl, text)


def wrap_tikz(text: str) -> str:
    """给每个 tikzpicture 套 adjustbox 宽度上限（幂等：已包裹的不重复套）。

    只对「尚未被 adjustbox / resizebox 包裹」的 tikzpicture 套一层
    \\begin{adjustbox}{max width=\\textwidth}；已手工预缩放（如过宽 pipeline 图
    用 \\resizebox{\\textwidth}{!}{...}）或前次生成的 chN.tex 再次跑 fix.py，
    都不会产生双层嵌套包裹。max width 仅对超宽图缩放，正常图保持原样。
    """
    out = []
    i = 0
    bt = r"\begin{tikzpicture}"
    et = r"\end{tikzpicture}"
    while True:
        b = text.find(bt, i)
        if b == -1:
            out.append(text[i:])
            break
        e = text.find(et, b)
        if e == -1:
            out.append(text[i:])
            break
        e_end = e + len(et)
        seg = text[i:b]  # 本 tikz 之前、上一处理边界之后的片段
        # 若此前已存在未闭合的 adjustbox / resizebox（即本 tikz 已被包裹），跳过
        already_wrapped = (r"\begin{adjustbox}" in seg) or (r"\resizebox{" in seg)
        out.append(seg)
        if already_wrapped:
            out.append(text[b:e_end])  # 已包裹：原样保留，不重复套
        else:
            out.append(r"\begin{adjustbox}{max width=\textwidth}" + "\n")
            out.append(text[b:e_end])
            out.append(r"\end{adjustbox}" + "\n")
        i = e_end
    return "".join(out)


def find_template() -> Path:
    """向上查找 assets/templates/_tmp.tex（脚本目录与 CWD 两条路径都试）。"""
    for start in (HERE, Path.cwd()):
        d = start.resolve()
        for _ in range(6):
            cand = d / "assets" / "templates" / "_tmp.tex"
            if cand.exists():
                return cand
            if d.parent == d:
                break
            d = d.parent
    return Path()


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="fix.py",
        description="单章 TeX 预处理：URL 规范化 + 图宽上限 + 生成 chN.tex/_tmp.tex",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python fix.py 4           # 处理第 4 章（在项目根目录执行）\n"
            "  python fix.py 附录A        # 处理附录 A\n"
            "  cd 第4章 && python fix.py 4  # 也可 cd 进章目录执行\n\n"
            "章节源文件约定: 第N章/第N章.tex（或旧扁平 第N章.tex）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args()

    # 误在 skill 的 scripts/ 目录运行时的主动提示（CWD 解析不到章节）
    if Path.cwd().resolve() == HERE.resolve() or Path.cwd().name == "scripts":
        print(
            "[fix.py] 提示：当前似乎在 skill 的 scripts/ 目录运行，很可能找不到章节源文件。\n"
            "    推荐：先 cd 到书稿项目根目录（含 第N章/ 子目录），再执行\n"
            "           python \"<skill路径>/scripts/fix.py\" 4\n"
            "    或 cd 进 第N章/ 目录后执行同一命令。",
            file=sys.stderr,
        )

    src = resolve_source(args.chapter, "fix.py")
    text = url_to_href(src.read_text(encoding="utf-8"))
    text = wrap_tikz(text)

    mid_name = mid_name_for(args.chapter)
    dst = src.parent / mid_name
    dst.write_text(text, encoding="utf-8")

    tpl = find_template()
    if tpl == Path() or not tpl.exists():
        raise SystemExit(
            "[fix.py] 找不到 assets/templates/_tmp.tex；请保持 skill 目录结构完整"
            "（scripts/ 与 assets/ 同级），或在项目根放一份 assets/templates/_tmp.tex。"
        )
    tpl_text = tpl.read_text(encoding="utf-8")
    target = "\\input{" + PLACEHOLDER + "}"
    if target not in tpl_text:
        raise SystemExit(
            f"[fix.py] 模板 {tpl} 缺少占位行 {target}，无法生成单章编译入口。"
        )
    tpl_text = tpl_text.replace(target, "\\input{" + dst.name + "}")
    tmp = src.parent / "_tmp.tex"
    tmp.write_text(tpl_text, encoding="utf-8")

    print(f"[fix.py] 源: {src} -> 中间文件: {dst.name} ({dst.stat().st_size} bytes)")
    print(f"[fix.py] 单章编译入口: {tmp} ({tmp.stat().st_size} bytes)")
    print("[fix.py] 下一步: xelatex -halt-on-error -interaction=nonstopmode _tmp.tex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
