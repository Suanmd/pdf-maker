# -*- coding: utf-8 -*-
"""build —— 整书合并编排器（整书合并唯一入口）。

在 _build/ 内把每个章节源文件经 normalize_text()（与单章 fix 同一函数）规范化后
编译，确保单章与合并两条流水线的 URL / TikZ / 字形 / 拆词处理完全一致，再统一出 main.pdf。

流程
----
0. 前置预检（非阻断）：前置整宽表格缺 \\noindent 提醒（_build 副本自动补）/
   前置部分（摘要/序言/术语表）存在性 + 空壳（存在但正文为空）/ main.tex 与共享补丁源漂移。
1. labels.main()    ：跨章 \\label 去重（有跨章引用则中止）。
2. xref.main()      ：合并前静态预检（越界「第N章」文字引用 / 跨章 \\ref），阻断则中止。
3. 规范化每个章节源 → _build/ 下的归一副本（URL → href + TikZ adjustbox + 字形修复 + 拆词）。
4. 重写 main.tex 的 \\input 指向归一副本（图形路径改指 ../figures）。
5. xelatex 两遍（在 _build/ 内）。
6. overflow.main() _build/main.log（硬卡口）。
7. 通过后复制 _build/main.pdf → 根 main.pdf，并清理 _build/；末尾把本轮全部
   非阻断告警汇总重列一遍（预检 WARN 散落在编译长输出之前，exit 0 时极易被淹没）。

退出码
------
0 合并成功且体检通过；非 0 任一步失败（labels 跨章引用 / xref 阻断 /
编译错误 / 溢出未清）。失败时 _build/ 保留以便排查。
"""

import argparse
import glob
import os
import re
import shutil
import stat
import sys
import time
from pathlib import Path
from shutil import which

import pdfmaker.core.config as cfg
from pdfmaker.commands import labels, overflow, verify, xref
from pdfmaker.commands.scaffold import is_untouched_placeholder
from pdfmaker.core import (
    find_preamble_shared,
    fix_glyphs,
    inject_frontmatter_noindent,
    normalize_text,
    scan_empty_frontmatter,
    scan_frontmatter_tables,
    scan_missing_frontmatter,
    scan_preamble_drift,
    setup_utf8,
    xelatex as xel,
)

setup_utf8()

BUILD_DIR = "_build"
CHAPTER_RE = re.compile(r"\\input\{([^}]+)\}")


def find_xelatex() -> str:
    """定位 xelatex：环境变量 > PATH > 平台常见安装路径（macOS 优先）。

    候选顺序：
    1. 环境变量 ``PDFMAKER_XELATEX``（显式指定，最高优先）；
    2. PATH 探测（``which xelatex``；MacTeX 安装后通常经 /etc/paths.d 已入 PATH）；
    3. macOS 固定路径：MacTeX/BasicTeX 的 ``/Library/TeX/texbin``、
       Homebrew 的 ``/opt/homebrew/bin``（Apple Silicon）与 ``/usr/local/bin``（Intel）；
    4. 手动安装的 TeX Live：``/usr/local/texlive/<year>/bin/<platform>/xelatex``
       （glob 探测，覆盖 macOS universal-darwin 与 Linux x86_64）；
    5. TinyTeX（``~/Library/TinyTeX/bin/*``）与用户级 TeX Live（``~/texlive/*/bin/*``），
       均为免 sudo 安装。

    兜底返回 ``"xelatex"``，交给 subprocess 报错。
    """
    env = os.environ.get("PDFMAKER_XELATEX")
    if env and Path(env).exists():
        return env
    if which("xelatex"):
        return "xelatex"
    candidates = [
        "/Library/TeX/texbin/xelatex",   # macOS MacTeX / BasicTeX 标准路径
        "/opt/homebrew/bin/xelatex",     # Homebrew（Apple Silicon）
        "/usr/local/bin/xelatex",        # Homebrew（Intel Mac）
        "/usr/bin/xelatex",              # Linux 系统包
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    # 手动安装的 TeX Live（任意年份 / 任意平台子目录）
    for c in sorted(glob.glob("/usr/local/texlive/*/bin/*/xelatex")):
        return c
    # TinyTeX（macOS 用户级免 sudo 发行版，~/Library/TinyTeX/bin/<platform>/）
    for c in sorted(glob.glob(str(Path.home() / "Library/TinyTeX/bin/*/xelatex"))):
        return c
    # 用户级 TeX Live（install-tl 装到 ~/texlive/<year>/bin/<platform>/，免 sudo）
    for c in sorted(glob.glob(str(Path.home() / "texlive/*/bin/*/xelatex"))):
        return c
    return "xelatex"  # 兜底，交给 subprocess 报错


def _remove_or_move_aside(path: Path) -> str | None:
    """删除目录；删不掉则改名为带时间戳的备份让路，并醒目告警。

    优先 rmtree；遇只读/环境删除守卫拦截时先尝试清除只读位再删；仍失败则改名为
    带时间戳的备份以让路，并醒目告警提示作者手动清理，避免「修复看似没生效」的
    误判。正常机器上 rmtree 直接成功、不留备份。

    返回一行告警摘要（发生让路/失败时），干净删除或目录不存在返回 None——
    供 main 汇入末尾的告警汇总块。
    """
    if not path.exists():
        return None
    try:
        shutil.rmtree(path)
    except OSError:
        # 第一次失败：尝试清除只读位后重试（只读文件会阻挡 rmtree）
        try:
            for _root, _dirs, _files in os.walk(path):
                for _f in _files:
                    _fp = os.path.join(_root, _f)
                    try:
                        os.chmod(_fp, stat.S_IWRITE)
                    except OSError:
                        pass
            shutil.rmtree(path)
            return None
        except OSError:
            pass
    else:
        return None
    # 仍失败：改名让路并醒目告警（不再静默）
    bak = path.with_name(f"{path.name}_bak{int(time.time())}")
    try:
        shutil.move(str(path), str(bak))
        print(
            f"\n[build][WARN] 无法删除 {path}（环境禁用删除 / 只读守卫），已改名 {bak} 让路。\n"
            f"          合并结束后请手动清理该备份目录，例如：rm -rf {bak}\n"
            f"          若之前误以为「修复未生效」，多半是旧 _build 残留——清掉备份再重跑即可。\n"
        )
        return f"旧目录 {path.name} 无法删除，已改名 {bak.name} 让路（请手动清理该备份）"
    except OSError:
        print(
            f"\n[build][WARN] 无法删除也无法改名 {path}，请手动清理后再重试合并。\n"
        )
        return f"旧目录 {path.name} 无法删除也无法改名，请手动清理后重试合并"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker build",
        description="整书合并编排器：规范化 + 编译 + 体检",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker build .              # 在当前书稿根合并\n"
            "  python -m pdfmaker build . --verify     # 合并前额外联网验活全书 URL\n"
            "  python -m pdfmaker build . --no-preflight  # 跳过 xref 预检\n\n"
            "前提：main.tex 已填好占位符与 \\input 章节列表。"
        ),
    )
    parser.add_argument("root", nargs="?", default=".",
                        help="书稿项目根目录，默认当前目录")
    parser.add_argument("--verify", action="store_true",
                        help="合并前额外运行 verify 验活全书 URL")
    parser.add_argument("--no-preflight", action="store_true",
                        help="跳过 xref 预检（不推荐）")
    parser.add_argument("--verbose", action="store_true",
                        help="全量回显 xelatex 输出（默认静默，仅失败时回显末尾 40 行）")
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[build] 根目录不存在：{root}")
        return 2

    # 非阻断告警汇总：预检 WARN 散落在 labels/xref/编译的长输出之前，exit 0 时
    # 极易被淹没。每处 WARN 在此登记一行摘要，合并成功后于末尾统一重列。
    warns: list[str] = []

    main_tex = root / "main.tex"
    if not main_tex.exists():
        print(f"[build] 找不到 {main_tex}，请先复制 pdfmaker 模板 main.tex 并填好占位符。")
        return 2
    if "{{CHAPTERS_LIST}}" in main_tex.read_text(encoding="utf-8"):
        print("[build] main.tex 仍含 {{CHAPTERS_LIST}} 占位符，请先替换为实际 \\input 列表。")
        return 2

    # ---- 0a. 前置部分整宽表格 \noindent 预检（合并后才暴露的 Overfull 根因） ----
    # 不再阻断：构建副本会自动在前置表格前补 \noindent（inject_frontmatter_noindent），
    # 源 main.tex 无需手动改动。此处仅作非阻断提醒，便于作者从源头保持一致。
    main_text_raw = main_tex.read_text(encoding="utf-8")
    fm_bad = scan_frontmatter_tables(main_text_raw)
    if fm_bad:
        lines_str = "、".join(str(n) for n in fm_bad)
        print(
            f"[build][提示] 前置部分（序言/术语表）第 {lines_str} 行的整宽表格未加 \\noindent：\n"
            f"          段落缩进（\\parindent，11pt 下 2em≈21.9pt）会与整宽表格叠加，触发恰好 21.9pt 的 Overfull。\n"
            f"          已自动在 _build 副本的对应表格前补 \\noindent（源文件不变），无需手动处理；\n"
            f"          若想从源头消除该提示，可在 main.tex 对应 \\begin{{tabularx/tabular/longtable}} 前加一行 \\noindent。"
        )

    # ---- 0b. 前置部分（摘要/序言/术语表）存在性预检 ----
    # 非阻断：提醒作者补全，避免静默出货一本没有前置部分的书。
    # 摘要为必选项（WARN）；序言/术语表按模板注释为可选（INFO）。
    fm_missing = scan_missing_frontmatter(main_text_raw)
    if fm_missing:
        if "摘要" in fm_missing:
            print(
                "[build][WARN] main.tex 未检测到「摘要」（\\chapter*{摘\\quad 要}）。成书将缺少摘要，"
                "建议补全前置部分（摘要/序言/术语表）后再合并。"
            )
            warns.append("main.tex 缺少「摘要」前置部分，成书将没有摘要页")
        opt = [x for x in fm_missing if x != "摘要"]
        if opt:
            print(
                f"[build][提示] 前置部分可选项缺失：{('、'.join(opt))}（序言/术语表可按需补全，不影响出货）。"
            )

    # ---- 0c. 前置部分「空壳」预检（存在但正文为空） ----
    # 与存在性预检互补：模板在摘要/序言处只留「% 在此输入……」注释，忘记填写时
    # 存在性预检放行、成书却带空白页（真实事故）。一律 WARN 非阻断：摘要为必选项，
    # 序言/术语表若不需要应整块删除——空的章节页没有存在意义。
    fm_empty = scan_empty_frontmatter(main_text_raw)
    if fm_empty:
        print(
            f"[build][WARN] 前置部分存在但正文为空：{('、'.join(fm_empty))}"
            "（只有模板占位注释，成书将出现空白页）。\n"
            "          请在 main.tex 对应 \\chapter*{...} 下补写正文；不需要的部分（如序言）请整块删除。"
        )
        warns.append(f"前置部分存在但正文为空：{('、'.join(fm_empty))}（成书将出现空白页）")

    # ---- 0d. 整书模板与共享补丁源漂移预检 ----
    # 非阻断：_preamble_shared.tex 是「中文 URL 支持 / 参考文献降级 / codeblock 环境 /
    # 表格字号 / 防溢出」五段补丁的唯一真源，单章模板 _tmp.tex 经 {{SHARED_PREAMBLE}} 内联；
    # 但整书模板 main.tex 可能是手写内联副本，若只改共享源而漏同步 main.tex，单章正常
    # 但整书缺补丁。提醒作者同步，避免单章/整书行为不一致。
    # 补丁源经包数据唯一定位（find_preamble_shared）；包数据缺失时静默跳过本项预检。
    shared_text = None
    try:
        shared_text = find_preamble_shared().read_text(encoding="utf-8")
    except SystemExit:
        pass
    if shared_text is not None:
        drift = scan_preamble_drift(main_text_raw, shared_text)
        if drift:
            print(
                f"[build][WARN] main.tex 与 _preamble_shared.tex 补丁漂移：{('、'.join(drift))}。"
                "请同步 _preamble_shared.tex（唯一真源）到 main.tex，避免单章/整书行为不一致。"
            )
            warns.append(f"main.tex 与共享补丁源漂移：{('、'.join(drift))}（单章/整书行为可能不一致）")

    # ---- 1. 跨章 label 去重 ----
    rc = labels.main([str(root)])
    if rc == 2:
        print("[build] labels 检测到跨章引用，已中止。请按提示手工处理后重跑。")
        return rc
    if rc != 0:
        print(f"[build] labels 返回非 0（{rc}），中止合并。")
        return rc

    # ---- 2. 合并前引用预检 ----
    if not args.no_preflight:
        rc = xref.main([str(root)])
        if rc != 0:
            print("[build] xref 阻断（越界文字引用 / 跨章 \\ref），修正后重跑。")
            return rc

    # ---- 2b. 可选：全书 URL 验活（对网络抖动更宽容） ----
    if args.verify:
        rc = verify.main([str(root)])
        if rc == 1:
            # 真实的失效/虚构/截断链接：必须修，否则成书即死链，阻断合并。
            print("[build] verify 发现失效/虚构/截断链接（exit 1），"
                  "必须替换为真实 LIVE 链接后重跑。中止合并。")
            return rc
        elif rc == 2:
            # 离线 / TRANSIENT（网络抖动）的可能性大，不阻断合并；
            # 作者已在单章 SOP 强制验活（exit 0），合并时仅作补充提醒。
            print("[build] verify 退出 2（离线或 TRANSIENT 未验活）："
                  "多为环境网络抖动，不阻断合并；交付前请用 `verify .` 复验至 exit 0。")
            warns.append("verify 退出 2（离线/未验活），交付前请用 verify . 复验至 exit 0")
        # rc == 0 → 全过，继续

    # ---- 3/4. 规范化章节 + 重写 main.tex ----
    build = root / BUILD_DIR
    aside_warn = _remove_or_move_aside(build)  # 旧 _build 先清掉（无法删则改名让路）
    if aside_warn:
        warns.append(aside_warn)
    build.mkdir(parents=True)

    # 对主控 main.tex 也施加 fix_glyphs（仅包裹正文裸用缺字字符，不碰 URL/TikZ
    # 宏），补齐「章节被规范化、main.tex 却绕过」的安全网缺口——否则 main.tex 里手写的
    # 裸 ×/% 等会 Missing character 且不被自动修复。
    main_text = fix_glyphs(main_tex.read_text(encoding="utf-8"))
    # 图形路径在 _build 内要指回根目录的 figures/
    main_text = main_text.replace("\\graphicspath{{figures/}}", "\\graphicspath{{../figures/}}")
    # 前置整宽表格自动补 \noindent（仅 _build 副本生效，源文件不变）：彻底消除
    # 「段落缩进 + 整宽表格」叠加导致的恰好 \parindent 的 Overfull，避免合并才暴露、白跑整书编译。
    main_text = inject_frontmatter_noindent(main_text)

    # 找出所有 \input{...}，把章节类输入规范化为 _build 内的归一副本
    seen: dict[str, str] = {}  # 原始 input 字符串 -> 新 input 字符串

    def resolve_input(content: str) -> Path | None:
        cands = [root / content, root / (content + ".tex")]
        for c in cands:
            if c.exists() and c.suffix == ".tex":
                return c
        return None

    for m in CHAPTER_RE.finditer(main_text):
        # 跳过注释行内的 \input{...}（如模板说明文字里的示例），只处理真实命令：
        # 行首到匹配位置之间存在未转义 % 即为注释。
        line_start = main_text.rfind("\n", 0, m.start()) + 1
        prefix = main_text[line_start:m.start()]
        if re.search(r"(?<!\\)%", prefix):
            continue
        raw = m.group(1)
        target = resolve_input(raw)
        if target is None:
            # 非章节输入（如不存在的相对引用），保留原样并告警
            print(f"[build] 警告：\\input{{{raw}}} 无法解析为 .tex，原样保留。")
            warns.append(f"\\input{{{raw}}} 无法解析为 .tex，已原样保留（成品可能缺内容）")
            continue
        # 仅对「章节/附录」源做规范化；其它 .tex（若有）也一并规范化以保证一致
        is_chapter = bool(re.search(r"(第\d+章|附录)", str(target)))
        if is_chapter:
            norm = normalize_text(target.read_text(encoding="utf-8"))
            # 非阻断提醒：整书不应带着未撰写的占位骨架出货（单章编排器有硬阻断，
            # build 仅 WARN——作者可能有意先合并看版式）。
            if is_untouched_placeholder(norm):
                print(f"[build][WARN] {target.name} 仍是未撰写的占位骨架（含「排版合规示例」节），"
                      f"建议撰写正文后再合并。")
                warns.append(f"{target.name} 仍是未撰写的占位骨架，建议撰写正文后再合并")
        else:
            norm = target.read_text(encoding="utf-8")
        sn = target.name  # _build 内用原始文件名，避免跨章重名冲突
        (build / sn).write_text(norm, encoding="utf-8")
        seen[raw] = sn
        print(f"[build] 规范化: {target.name} -> _build/{sn}  (is_chapter={is_chapter})")

    if not seen:
        print("[build] 未在 main.tex 中找到任何章节 \\input，无法合并。")
        shutil.rmtree(build)
        return 2

    for raw, sn in seen.items():
        main_text = main_text.replace(f"\\input{{{raw}}}", f"\\input{{{sn}}}")

    (build / "main.tex").write_text(main_text, encoding="utf-8")

    # ---- 5. xelatex 两遍 ----
    # 与单章编排器 chapter 对齐：优先采用 .pdfmaker.toml 的 xelatex 覆盖项
    # （经 apply_project_config 写入 cfg.XELATEX_BIN），其次运行时探测。
    xelatex = cfg.XELATEX_BIN or find_xelatex()
    for i in range(2):
        print(f"[build] xelatex 第 {i + 1}/2 遍（{xelatex}）…")
        rc = xel.compile(
            xelatex, "-halt-on-error", "-interaction=nonstopmode", "main.tex",
            cwd=str(build), quiet=not args.verbose,
        )
        if rc != 0:
            print(f"[build] xelatex 第 {i + 1} 遍失败（rc={rc}），停止合并。")
            return 1

    # ---- 6. 日志体检 ----
    rc = overflow.main([str(build / "main.log")])
    if rc != 0:
        print(f"[build] overflow 未通过（{rc}）。_build/ 已保留，请排查后重跑。")
        return rc

    # ---- 7. 落盘 + 清理 ----
    pdf = build / "main.pdf"
    if not pdf.exists():
        print("[build] 未生成 main.pdf，合并失败。_build/ 已保留。")
        return 1
    shutil.copy(str(pdf), str(root / "main.pdf"))
    print(f"[build] 已生成 {root / 'main.pdf'}")
    aside_warn = _remove_or_move_aside(build)
    if aside_warn:
        warns.append(aside_warn)
    print("[build] 合并完成 ✅（_build/ 已清理；若环境禁用删除则留作 _build_bak* 备份）")
    # 非阻断告警末尾汇总重列：保证「只读尾部输出 / 只信 exit code」的用户也能看到
    # 本轮携带的全部 WARN，避免带空白前置页等瑕疵静默出货。
    if warns:
        print(f"\n[build] ⚠️ 本轮合并携带 {len(warns)} 条告警（未阻断，出货前请过一遍）：")
        for w in warns:
            print(f"  - {w}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
