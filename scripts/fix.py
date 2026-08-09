# -*- coding: utf-8 -*-
"""fix.py - 单章 TeX 预处理。

用途
----
把作者手写的章节源文件（标准 `第N章/第N章.tex`，兼容旧扁平 `第N章.tex`；附录 `附录X/附录X.tex`）转换为可直接交给
xelatex 编译的成品，并读取 `assets/templates/_tmp.tex` 模板生成单章独立编译所需的 `_tmp.tex`（preamble 唯一真源）。

它会批量修复几类常见、且“编译期才暴露”的中文 LaTeX 坑，避免临时手工改源码。

检查/处理项
-----------
1. URL 规范化：把 ``\\url{...}`` 改写为 ``\\href{raw-url}{display-text}``，
   并对显示文本里的 LaTeX 特殊字符做转义（见 § URL 约定）。
2. 图片宽度上限：给每个 ``tikzpicture`` 套 ``adjustbox{max width=\\textwidth}``，
   只缩放超宽图，正常图保持原样。
3. 写入英文名中间文件 ``chN.tex``（避免中文文件名在部分工具链下乱码）。
4. 生成 ``_tmp.tex``：读取 ``assets/templates/_tmp.tex`` 模板（单章编译
   preamble 的唯一真源，含参考文献降级、中文 URL 支持、代码块环境、防溢出等
   补丁），将其中的 ``\\input{CHAPTER_TEX}`` 占位行替换为实际章节中间文件名后写出。

中间文件与成品统一写在「源文件所在目录」，因此章目录始终自包含。

路径解析规则（重要）
--------------------
按以下顺序查找章节源文件，第一个命中即用：

    1. <当前工作目录>/第N章/第N章.tex     ← 标准子目录布局（推荐）
    2. <当前工作目录>/第N章.tex           ← 旧扁平布局
    3. <脚本所在目录>/第N章/第N章.tex     ← 脚本被复制进项目时的兜底
    4. <脚本所在目录>/第N章.tex

因此只需从书稿项目根目录用 skill 的实际安装路径调用即可（如
``python /path/to/skill/scripts/fix.py 3``，skill 装在哪都行），也可 ``cd 第3章`` 后执行同一命令，无需把脚本复制到项目里。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「写正文之后、xelatex 之前」调用，每章必跑（不可替代）。
用法：
    python fix.py [CH_NUM]          # 默认处理第 1 章
    python fix.py 3                 # 处理第 3 章
    python fix.py 附录A             # 处理附录 A

退出码：0 成功；源文件缺失、模板缺失或模板损坏时非零退出。
"""
import re
import sys
from pathlib import Path
from urllib.parse import unquote

# 强制 UTF-8 输出（Windows 控制台 GBK 回退 bug 修复）
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

HERE = Path(__file__).parent
ARG = sys.argv[1] if len(sys.argv) > 1 else "1"

# 占位行：模板里唯一会被替换成真实章节文件名的地方
PLACEHOLDER = "CHAPTER_TEX"


def resolve_source(arg: str):
    """定位章节 / 附录源文件。

    返回 (源文件路径, 中间文件名)。找不到时抛 SystemExit 并列出全部尝试路径。
    """
    if arg.startswith("附录"):
        stem, mid_name = arg, f"{arg}_ch.tex"
    else:
        stem, mid_name = f"第{arg}章", f"ch{arg}.tex"

    tried = []
    for base in (Path.cwd(), HERE):
        for cand in (base / stem / f"{stem}.tex", base / f"{stem}.tex"):
            tried.append(cand)
            if cand.exists():
                return cand, mid_name

    lines = "\n".join(f"    {p}" for p in dict.fromkeys(tried))
    raise SystemExit(
        f"[fix.py] 找不到 {stem}.tex，已尝试以下位置：\n{lines}\n"
        f"    提示：在项目根目录执行（推荐），或 cd 进章目录后再执行。"
    )


SRC, MID_NAME = resolve_source(ARG)
DST = SRC.parent / MID_NAME
TMP = SRC.parent / "_tmp.tex"


def url_to_href(text: str) -> str:
    """将 \\url{...} 改写为 \\href{raw}{display-escaped}。

    - URL 保持原始（不预 percent-encode，交由 hyperref 处理）。
    - 显示文本里的 LaTeX 特殊字符必须转义，否则会进入 math mode 报错。
    """
    def repl(m):
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
    """给每个 tikzpicture 套 adjustbox 宽度上限。

    只对超宽图缩放，正常图不动；这是“图片不超出版心”的结构性保证。
    """
    out = []
    i = 0
    BT = r"\begin{tikzpicture}"
    ET = r"\end{tikzpicture}"
    while True:
        b = text.find(BT, i)
        if b == -1:
            out.append(text[i:])
            break
        e = text.find(ET, b)
        if e == -1:
            out.append(text[i:])
            break
        e_end = e + len(ET)
        out.append(text[i:b])
        out.append(r"\begin{adjustbox}{max width=\textwidth}" + "\n")
        out.append(text[b:e_end])
        out.append(r"\end{adjustbox}" + "\n")
        i = e_end
    return "".join(out)


def find_template() -> Path | None:
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
    return None


def main() -> int:
    # ---- 1. URL 规范化 ----
    text = url_to_href(SRC.read_text(encoding="utf-8"))

    # ---- 2. 图片宽度上限 ----
    text = wrap_tikz(text)

    # ---- 3. 写出英文名中间文件 ----
    DST.write_text(text, encoding="utf-8")

    # ---- 4. 生成单章编译入口 _tmp.tex ----
    # 单章编译 preamble 的唯一真源是 assets/templates/_tmp.tex（与整书 main.tex 同步关键补丁）。
    # 这里只读取模板，把 \input{CHAPTER_TEX} 占位行替换为实际中间文件名，避免 preamble 双源漂移。
    tpl = find_template()
    if tpl is None:
        raise SystemExit(
            "[fix.py] 找不到 assets/templates/_tmp.tex；请保持 skill 目录结构完整"
            "（scripts/ 与 assets/ 同级），或在项目根放一份 assets/templates/_tmp.tex。"
        )
    tpl_text = tpl.read_text(encoding="utf-8")

    # 只替换 \input{占位符} 这一处，注释中出现的占位符字样不受影响
    target = "\\input{" + PLACEHOLDER + "}"
    if target not in tpl_text:
        raise SystemExit(
            f"[fix.py] 模板 {tpl} 缺少占位行 {target}，无法生成单章编译入口。"
        )
    tpl_text = tpl_text.replace(target, "\\input{" + DST.name + "}")
    TMP.write_text(tpl_text, encoding="utf-8")

    print(f"[fix.py] 源: {SRC} -> 中间文件: {DST.name} ({DST.stat().st_size} bytes)")
    print(f"[fix.py] 单章编译入口: {TMP} ({TMP.stat().st_size} bytes)")
    print("[fix.py] 下一步: xelatex -halt-on-error -interaction=nonstopmode _tmp.tex")
    return 0


if __name__ == "__main__":
    sys.exit(main())
