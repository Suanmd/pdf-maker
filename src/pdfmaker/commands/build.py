# -*- coding: utf-8 -*-
"""build —— 整书合并编排器（Phase B 一键入口）。

整书合并的编排脚本：在 _build/ 内把每个章节源文件经 normalize_text()
（与单章 fix 同一函数）规范化后编译，确保单章与合并两条流水线的 URL / TikZ
处理完全一致，再统一出 main.pdf。

流程
----
1. labels.main()    ：跨章 \\label 去重（有跨章引用则中止）。
2. xref.main()      ：合并前静态预检（越界「第N章」文字引用 / 跨章 \\ref），阻断则中止。
3. 规范化每个章节源 → _build/ 下的归一副本（URL→href + TikZ adjustbox）。
4. 重写 main.tex 的 \\input 指向归一副本（图形路径改指 ../figures）。
5. xelatex 两遍（在 _build/ 内）。
6. overflow.main() _build/main.log（硬卡口）。
7. 通过后复制 _build/main.pdf → 根 main.pdf，并清理 _build/。

退出码：0 合并成功且体检通过；非 0 任一步失败（labels 跨章引用 / xref 阻断 /
编译错误 / 溢出未清）。失败时 _build/ 保留以便排查。
"""

import argparse
import os
import re
import shutil
import sys
import time
from pathlib import Path

from pdfmaker.commands import labels, overflow, verify, xref
from pdfmaker.core import (
    inject_frontmatter_noindent,
    normalize_text,
    scan_frontmatter_tables,
    scan_missing_frontmatter,
    scan_preamble_drift,
    setup_utf8,
    xelatex as xel,
)
from pdfmaker.core.normalize import fix_glyphs
import pdfmaker.core.config as cfg

setup_utf8()

BUILD_DIR = "_build"
CHAPTER_RE = re.compile(r"\\input\{([^}]+)\}")


def find_xelatex() -> str:
    """定位 xelatex：优先 PATH，其次常见 TeX Live 路径，最后环境变量。"""
    env = os.environ.get("PDFMAKER_XELATEX")
    if env and Path(env).exists():
        return env
    from shutil import which

    if which("xelatex"):
        return "xelatex"
    candidates = [
        r"C:/texlive/2024/bin/windows/xelatex.exe",
        r"C:/texlive/2023/bin/windows/xelatex.exe",
        r"C:/Program Files/texlive/2024/bin/windows/xelatex.exe",
        r"C:/Program Files/MiKTeX/miktex/bin/x64/xelatex.exe",
        r"/usr/bin/xelatex",
        r"/Library/TeX/texbin/xelatex",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "xelatex"  # 兜底，交给 subprocess 报错


def _remove_or_move_aside(path: Path) -> None:
    """删除目录；优先 rmtree，遇只读/环境删除守卫拦截时先尝试清除只读位再删，

    仍失败则改名为带时间戳的备份以让路，并**醒目告警**提示作者手动清理，
    避免「修复看似没生效」的误判。正常机器上 rmtree 直接成功、不留备份。
    """
    if not path.exists():
        return
    try:
        shutil.rmtree(path)
    except OSError:
        # 第一次失败：尝试清除只读位后重试（Windows 常见只读文件阻挡 rmtree）
        try:
            import stat

            for _root, _dirs, _files in os.walk(path):
                for _f in _files:
                    _fp = os.path.join(_root, _f)
                    try:
                        os.chmod(_fp, stat.S_IWRITE)
                    except OSError:
                        pass
            shutil.rmtree(path)
            return
        except OSError:
            pass
    else:
        return
    # 仍失败：改名让路并醒目告警（不再静默）
    bak = path.with_name(f"{path.name}_bak{int(time.time())}")
    try:
        shutil.move(str(path), str(bak))
        print(
            f"\n[build][WARN] 无法删除 {path}（环境禁用删除 / 只读守卫），已改名 {bak} 让路。\n"
            f"          合并结束后请手动清理该备份目录，例如：rm -rf {bak}\n"
            f"          若之前误以为「修复未生效」，多半是旧 _build 残留——清掉备份再重跑即可。\n"
        )
    except OSError:
        print(
            f"\n[build][WARN] 无法删除也无法改名 {path}，请手动清理后再重试合并。\n"
        )


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
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    if not root.exists():
        print(f"[build] 根目录不存在：{root}")
        return 2
    main_tex = root / "main.tex"
    if not main_tex.exists():
        print(f"[build] 找不到 {main_tex}，请先复制 pdfmaker 模板 main.tex 并填好占位符。")
        return 2
    if "{{CHAPTERS_LIST}}" in main_tex.read_text(encoding="utf-8"):
        print("[build] main.tex 仍含 {{CHAPTERS_LIST}} 占位符，请先替换为实际 \\input 列表。")
        return 2

    # ---- 0. 前置部分整宽表格 \\noindent 预检（合并后才暴露的 Overfull 根因） ----
    # 不再阻断：构建副本会自动在前置表格前补 \\noindent（inject_frontmatter_noindent），
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
    # 非阻断：提醒作者补全，避免静默出货一本没有前置部分的书（用户曾踩此坑）。
    # 摘要为必选项（WARN）；序言/术语表按模板注释为可选（INFO）。
    fm_missing = scan_missing_frontmatter(main_text_raw)
    if fm_missing:
        if "摘要" in fm_missing:
            print(
                "[build][WARN] main.tex 未检测到「摘要」（\\chapter*{摘\\quad 要}）。成书将缺少摘要，"
                "建议补全前置部分（摘要/序言/术语表）后再合并。"
            )
        opt = [x for x in fm_missing if x != "摘要"]
        if opt:
            print(
                f"[build][提示] 前置部分可选项缺失：{('、'.join(opt))}（序言/术语表可按需补全，不影响出货）。"
            )

    # ---- 0c. 整书模板与共享补丁源漂移预检 ----
    # 非阻断：_preamble_shared.tex 是「中文 URL 支持 / 参考文献降级 / codeblock 环境 /
    # 防溢出」四段补丁的唯一真源，单章模板 _tmp.tex 经 {{SHARED_PREAMBLE}} 内联；
    # 但整书模板 main.tex 仍是手写内联副本，若只改共享源而漏同步 main.tex，单章正常
    # 但整书缺补丁。提醒作者同步，避免单章/整书行为不一致。
    _shared_path = Path(__file__).resolve().parent.parent / "templates" / "_preamble_shared.tex"
    if _shared_path.exists():
        shared_text = _shared_path.read_text(encoding="utf-8")
        drift = scan_preamble_drift(main_text_raw, shared_text)
        if drift:
            print(
                f"[build][WARN] main.tex 与 _preamble_shared.tex 补丁漂移：{('、'.join(drift))}。"
                "请同步 _preamble_shared.tex（唯一真源）到 main.tex，避免单章/整书行为不一致。"
            )

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
        # rc == 0 → 全过，继续

    # ---- 3/4. 规范化章节 + 重写 main.tex ----
    build = root / BUILD_DIR
    _remove_or_move_aside(build)  # 旧 _build 先清掉（无法删则改名让路）
    build.mkdir(parents=True)

    # 对主控 main.tex 也施加 fix_glyphs（仅包裹正文裸用缺字字符，不碰 URL/TikZ
    # 宏），补齐「章节被规范化、main.tex 却绕过」的安全网缺口——否则 main.tex 里手写的
    # 裸 ×/% 等会 Missing character 且不被自动修复。当前 main.tex 已用 $\times$/% 写法，
    # 此处为等价 no-op；未来作者在前置部分直接写裸符号也能自愈。
    main_text = fix_glyphs(main_tex.read_text(encoding="utf-8"))
    # 图形路径在 _build 内要指回根目录的 figures/
    main_text = main_text.replace("\\graphicspath{{figures/}}", "\\graphicspath{{../figures/}}")
    # 前置整宽表格自动补 \\noindent（仅 _build 副本生效，源文件不变）：彻底消除
    # 「段落缩进 + 整宽表格」叠加导致的恰好 \\parindent 的 Overfull，避免合并才暴露、白跑整书编译。
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
        raw = m.group(1)
        target = resolve_input(raw)
        if target is None:
            # 非章节输入（如不存在的相对引用），保留原样并告警
            print(f"[build] 警告：\\input{{{raw}}} 无法解析为 .tex，原样保留。")
            continue
        # 仅对「章节/附录」源做规范化；其它 .tex（若有）也一并规范化以保证一致
        is_chapter = bool(re.search(r"(第\d+章|附录)", str(target)))
        if is_chapter:
            norm = normalize_text(target.read_text(encoding="utf-8"))
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
    # 与单章编排器 chapter.py 对齐，优先采用 .pdfmaker.toml 的 xelatex 覆盖项
    # （经 apply_project_config 写入 cfg.XELATEX_BIN），其次运行时探测。旧实现仅调
    # find_xelatex()，会忽略 toml 指定的 xelatex 路径，与单章流水线行为不一致。
    xelatex = cfg.XELATEX_BIN or find_xelatex()
    for i in range(2):
        rc = xel.compile(
            xelatex, "-halt-on-error", "-interaction=nonstopmode", "main.tex", cwd=str(build)
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
    _remove_or_move_aside(build)
    print("[build] 合并完成 ✅（_build/ 已清理；若环境禁用删除则留作 _build_bak* 备份）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
