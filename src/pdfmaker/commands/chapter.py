# -*- coding: utf-8 -*-
"""chapter —— 单章全流程 SOP 一键编排器。

把逐章写作的全部质量关卡串成一条「遇阻断即停」的流水线，免去手工逐步跑、
容易漏步或忘设环境变量之苦：

    reader ingest（可选，--material 指定素材笔记）
      → fix（URL 规范化 + 图宽上限 + 生成 chN.tex/_tmp.tex）
      → check（样式门禁阻断；字数为告警级不阻断）
      → 骨架守卫（章文件仍是未撰写骨架时阻断，防止把占位内容编成 PDF）
      → balance（结构/引用均衡，阻断级可阻断）
      → xref --self-only（跨章引用早期自检，非阻断）
      → verify（联网验活，exit 1 阻断；exit 2 离线仅警告继续）
      → xelatex ×2（在章目录内编译）
      → overflow（编译日志体检，阻断即停）
      → cleanup（落盘成品 PDF + 归档中间文件）
      → track update（登记章节已验证状态；章节未登记时自动 init）

所有阈值（字数下限 / 配图下限 / 验活探针主机 / xelatex 路径等）均继承项目
``.pdfmaker.toml`` 或环境变量，无需每步手动 export。

退出码
------
0 全流程通过并交付；非 0 任一步阻断（样式违规 / 骨架未撰写 / 引用不闭合 /
死链 / 编译失败 / 日志体检未过；字数不足仅告警不阻断）。
失败时中间产物保留以便排查。
"""

import argparse
import sys
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.commands import (
    balance,
    check,
    cleanup,
    fix,
    overflow,
    reader,
    scaffold,
    track,
    verify,
    xref,
)
from pdfmaker.commands.build import find_xelatex
from pdfmaker.core import paths, setup_utf8, xelatex as xel


def _step(name: str, fn, *args, block: bool = True) -> bool:
    """运行一个 SOP 步骤；block=True 时非 0 视为阻断并中止。

    返回 True 表示通过（或仅警告），False 表示阻断失败。
    """
    print(f"\n=== [{name}] ===")
    try:
        rc = fn(*args)
    except SystemExit as e:
        rc = e.code if isinstance(e.code, int) else 1
    if rc == 0:
        print(f"=== [{name}] OK ===")
        return True
    if not block:
        print(f"=== [{name}] 退出 {rc}（仅警告，继续）===")
        return True
    print(f"=== [{name}] 失败（退出 {rc}），流程中止 ===")
    return False


def ensure_chapter_skeleton(chapter: str, material: str | None,
                            force_scaffold: bool, cwd: str,
                            flat: bool = False, force_cwd: bool = False) -> bool:
    """章文件缺失时按素材自动生成合规骨架（接进标准 SOP）。

    触发条件：章号为数字 + 章文件不存在 +（提供了 ``--material`` 或显式
    ``--scaffold``）。这样标准 SOP 命令 ``python -m pdfmaker chapter N
    --material <素材.md>`` 在章文件缺失时**默认**就从合规富骨架起稿，从源头杜绝
    「从空白手敲」导致的三线表/codeblock 样式漂移——无需记忆 ``--scaffold`` 显式开关。

    布局：标准（``第N章/第N章.tex``）与扁平（``第N章.tex`` 在项目根）两种都算
    「已存在」，任一存在即跳过。生成时默认标准布局；``flat=True``（--flat）或
    项目根已存在其他扁平章节时，跟随扁平布局。

    CWD 守卫：需要「创建」新骨架而 cwd 不像书稿项目根（无 main.tex /
    materials.json / 既有章节结构）时，拒绝在错误位置生成游离章目录
    （真实事故来源：在书稿的上级目录跑 chapter，骨架落到了错误位置），
    并给出诊断提示；``force_cwd=True``（--force-cwd）显式豁免（如全新扁平项目）。

    返回 True 表示本次新生成了骨架；False 表示跳过（文件已存在或无需生成）。
    非破坏性：文件已存在一律跳过，绝不覆盖用户已有成果。
    """
    if not chapter.isdigit():
        return False
    stem = paths.stem_of(chapter)
    # 两种布局都算「已存在」：标准（第N章/第N章.tex）与扁平（第N章.tex）
    existing = None
    for cand in (Path(cwd) / stem / f"{stem}.tex", Path(cwd) / f"{stem}.tex"):
        if cand.exists():
            existing = cand
            break
    if existing is not None:
        # 例外：整书初始化（scaffold --chapters N）落下的是「未命名章标题」占位骨架，
        # 不含任何作者劳动；提供素材时允许被素材驱动的富骨架再生一次
        # （否则素材骨架这个能力在「先 scaffold 整书」的标准流程下永远用不上）。
        if material and scaffold.is_untouched_placeholder(
                existing.read_text(encoding="utf-8")):
            print("\n=== [scaffold] 章文件仍是占位骨架，按素材再生富骨架 ===")
            flat_existing = existing.parent == Path(cwd)
            scaffold.write_chapter(int(chapter), material=material, root=cwd,
                                   force=True, flat=flat_existing)
            return True
        return False
    if not (material or force_scaffold):
        # 既没素材也没显式标志：不自动生成，保留原行为（交由 resolve_source 报错提示）
        return False
    # ---- CWD 守卫：创建新骨架前，确认 cwd 像书稿项目根 ----
    if not force_cwd and not paths.looks_like_project_root(Path(cwd)):
        hint = ""
        if material:
            near = paths.find_material_nearby(Path(material).name, Path(cwd))
            if near is not None:
                hint = (f"\n    线索：在 {near} 找到了素材文件——"
                        f"你可能想在 {near.parent.parent} 下执行本命令。")
        print(
            f"[chapter] 拒绝在 {cwd} 创建章骨架：该目录不像书稿项目根"
            f"（无 main.tex / materials.json / 既有章节结构）。\n"
            f"    请 cd 到书稿项目根后重跑；若确要在当前目录新建（如全新项目），"
            f"加 --force-cwd 显式豁免。{hint}",
            file=sys.stderr,
        )
        raise SystemExit(2)
    # 未显式 --flat 时，若项目根已有其他扁平章节（第M章.tex），跟随扁平布局
    if not flat:
        flat = any(Path(cwd).glob("第*章.tex"))
    print("\n=== [scaffold] 章文件缺失，自动生成合规骨架 ===")
    scaffold.write_chapter(int(chapter), material=material, root=cwd, force=False,
                           flat=flat)
    return True


def _is_scaffold_skeleton(src: Path) -> bool:
    """判断章文件是否仍是 scaffold 生成的骨架（作者尚未撰写正文）。

    依据骨架独有的两处标记：头部生成注释 + 内嵌的「排版合规示例（撰写正文后
    务必删除）」示例节。用于在 check 字数门禁阻断时给出「这是预期，请开始写作」
    的引导文案，而非冷冰冰的 FAIL——骨架态被门禁挡住是标准流程的一环。
    """
    try:
        text = src.read_text(encoding="utf-8")
    except OSError:
        return False
    return ("本文件由 pdfmaker scaffold 生成" in text
            and "撰写正文后务必删除" in text)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker chapter",
        description="单章全流程 SOP 一键编排：reader → fix → check → balance → verify → xelatex×2 → overflow → cleanup → track",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker chapter 3                 # 走完第 3 章全流程\n"
            "  python -m pdfmaker chapter 3 --material 第3章/素材-第3章.md  # 先强制阅读素材\n"
            "  python -m pdfmaker chapter 3 --no-verify     # 跳过联网验活（离线时）\n"
            "  python -m pdfmaker chapter 3 --no-track      # 不更新 materials.json\n\n"
            "在项目根目录执行；阈值自动继承项目 .pdfmaker.toml / 环境变量。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    parser.add_argument("--material", default=None,
                        help="素材笔记 .md 路径；传入则先跑 reader ingest 强制阅读。"
                             "多章约定素材在章节文件夹（第N章/素材-第N章.md），"
                             "扁平单章在项目根；裸文件名两种约定自动解析")
    parser.add_argument("--project", default=None,
                        help="书稿项目根目录（默认取章目录的父目录）")
    parser.add_argument("--xelatex", default=None,
                        help="xelatex 可执行文件路径（覆盖 .toml / 环境变量 / 运行时探测）")
    parser.add_argument("--no-verify", action="store_true",
                        help="跳过联网验活（离线环境可用，交付前需另行 verify .）")
    parser.add_argument("--no-track", action="store_true",
                        help="不更新 materials.json 的章节验证状态")
    parser.add_argument("--scaffold", action="store_true",
                        help="（已默认开启）章文件缺失时，显式强制用 scaffold 按素材生成合规骨架；"
                             "实际上 `chapter N --material` 在章文件缺失时已自动起稿，此标志仅作兼容保留")
    parser.add_argument("--flat", action="store_true",
                        help="扁平布局：章文件缺失需自动起稿时写为 第N章.tex（不建 第N章/ 目录），"
                             "成品 PDF 落在一级目录。推荐单章写作使用；已存在的扁平章节无需此标志")
    parser.add_argument("--force-cwd", action="store_true",
                        help="豁免 CWD 守卫：允许在「不像书稿项目根」的目录创建章骨架"
                             "（默认拒绝，防止在错误目录生成游离文件）")
    args = parser.parse_args(argv)

    setup_utf8()
    # 自动加载项目级配置（与 cli 一致，确保直接 python -m pdfmaker.commands.chapter 也生效）
    cfg.load_project_config()
    cfg.apply_project_config()

    chapter = args.chapter

    # 素材路径解析：多章约定素材在章节文件夹（第N章/素材-第N章.md），扁平单章
    # 项目素材在项目根；裸文件名两种约定都能解析。解析一次，scaffold/reader/track
    # 三处共用同一路径（reader 状态按绝对路径 md5 键控，路径必须一致）。
    material = None
    if args.material:
        material = str(paths.resolve_material(args.material, chapter))
        # 解析后仍不存在：向一级子目录下探一次，给出「疑似 CWD 错误」的诊断提示，
        # 而不是裸报 FILE NOT FOUND 让作者自己猜（真实事故来源）。
        if not Path(material).exists():
            near = paths.find_material_nearby(Path(material).name)
            hint = (f"\n    线索：在 {near} 找到了同名素材——"
                    f"你可能想 cd 到 {near.parent.parent} 再执行本命令。") if near else ""
            print(f"[chapter] 素材不存在: {material}{hint}", file=sys.stderr)
            return 2

    # 章文件缺失时按素材自动生成合规骨架（治本，已接进标准 SOP，非破坏性）：
    # 无需 --scaffold 显式开关，`chapter N --material` 在章文件缺失时即自动起合规骨架，
    # 从源头杜绝「从空白手敲」导致的三线表/codeblock 样式漂移。已有文件一律跳过。
    # 占位骨架被再生的情况见 ensure_chapter_skeleton 文档。
    regenerated = ensure_chapter_skeleton(chapter, material, args.scaffold,
                                          str(Path.cwd()), flat=args.flat,
                                          force_cwd=args.force_cwd)

    try:
        src = paths.resolve_source(chapter, "pdfmaker chapter")
    except SystemExit:
        return 2
    chdir = src.parent
    # 项目根推断：标准布局下 chdir 是 第N章/（或 附录X/）目录，项目根为其父目录；
    # 扁平布局下章 .tex 直接在项目根，chdir 本身就是项目根（与 xref 的判定约定一致）。
    if args.project:
        project = Path(args.project)
    elif chdir.name.startswith(("第", "附录")):
        project = chdir.parent
    else:
        project = chdir
    stem = paths.stem_of(chapter)

    print(f"[chapter] 章节源: {src}")
    print(f"[chapter] 章目录: {chdir}")
    print(f"[chapter] 项目根: {project}")

    # ---- 1. 素材强制阅读（可选）；读取后从 reader 状态取真实 chunk 数，供 track 登记 ----
    chunks_count = 0
    if material:
        if not _step("reader ingest", reader.main, ["ingest", material]):
            return 1
        try:
            chunks_count = int(reader.load_state(material).get("total_chunks", 0))
        except Exception:
            chunks_count = 0

    # ---- 1.5 骨架刚生成（含占位骨架再生）→ 素材已读，提前退出 ----
    # fix/check 等后续步骤对骨架空转没有价值（check 字数门禁必 FAIL），
    # 直接给出「请撰写正文后重跑」的指引，把控制权交还作者。
    if regenerated:
        print("\n[chapter] 素材富骨架已就绪、素材已完成强制阅读。"
              "请按预生成的节结构与文献条目撰写正文（删除「排版合规示例」节），")
        print(f"          完成后重跑 `python -m pdfmaker chapter {chapter}"
              + (" --material " + material if material else "") + "` 继续全流程。")
        return 0

    # ---- 2. 预处理 ----
    if not _step("fix", fix.main, [chapter]):
        return 1

    # ---- 3. 结构校验（check + balance） ----
    # check 的字数门禁为告警级（不阻断）——字数是主观厚度代理，
    # 内容达标时不应强制返工注水。唯一保留阻断的场景是「章文件仍是未撰写的
    # scaffold 骨架」（占位文字显然不是成品，编出 PDF 没有意义），用独立检查实现。
    if not _step("check", check.main, [chapter]):
        return 1
    if _is_scaffold_skeleton(src):
        print("\n[chapter] 章文件仍是脚手架（尚未撰写正文）：骨架不应直接进入编译交付。")
        print("          请按骨架预生成的节结构与文献条目撰写正文"
              "（并删除「排版合规示例」节），")
        print(f"          完成后重跑 `python -m pdfmaker chapter {chapter}` 继续全流程。")
        print("          若确属合法短章/附录，请直接编辑正文后重跑——"
              "仅删除示例节即视为已开始撰写。")
        return 1

    # ---- 4. 结构/引用均衡 ----
    if not _step("balance", balance.main, [chapter]):
        return 1

    # ---- 4.5 跨章引用早期自检（非阻断） ----
    # 仅校验本章，避免盲写「第N章」越界 / 跨章 \ref，把合并期才暴露的红线问题提前到单章阶段。
    _step("xref(self)", xref.main, [chapter, "--self-only"], block=False)

    # ---- 5. 联网验活（exit 1 阻断；exit 2 离线仅警告继续） ----
    # 状态语义：verify 返回 0 → verified（已验活）；
    # 返回 2（离线/TRANSIENT） → pending-verify（待联网复验，不污染已交付信号）；
    # --no-verify 显式跳过 → unverified（真未验）。三者都绝不谎报「已验活」。
    verified_passed = False
    verify_pending = False
    if args.no_verify:
        print("\n=== [verify] 跳过（--no-verify）===")
    else:
        print("\n=== [verify] ===")
        rc = verify.main([chapter])
        if rc == 1:
            print("=== [verify] 失败（存在死链/截断链接），流程中止 ===")
            return 1
        elif rc == 2:
            print("=== [verify] 退出 2（离线/未验活），警告但继续；"
                  "将标记为 pending-verify（待联网复验至 exit 0）===")
            verify_pending = True
        else:
            print("=== [verify] OK ===")
            verified_passed = True

    # ---- 6. xelatex 两遍（先确认可执行文件存在，否则给出清晰错误而非崩溃） ----
    xelatex = args.xelatex or cfg.XELATEX_BIN or find_xelatex()
    if not xelatex:
        print("=== [xelatex] 未找到 xelatex（--xelatex / .pdfmaker.toml xelatex / "
              "PATH 探测均失败），流程中止 ===")
        return 2
    for i in range(2):
        print(f"\n=== [xelatex 第 {i + 1} 遍] ===")
        rc = xel.compile(
            xelatex, "-halt-on-error", "-interaction=nonstopmode", "_tmp.tex",
            cwd=str(chdir), quiet=True,
        )
        if rc != 0:
            print(f"=== [xelatex] 失败（第 {i + 1} 遍，rc={rc}），流程中止 ===")
            return 1

    # ---- 7. 编译日志体检（硬卡口） ----
    print("\n=== [overflow] ===")
    rc = overflow.main([str(chdir / "_tmp.log")])
    if rc != 0:
        print("=== [overflow] 未通过，流程中止（_tmp.log 已保留）===")
        return 1
    print("=== [overflow] OK ===")

    # ---- 8. 落盘成品 PDF + 归档中间文件 ----
    if not _step("cleanup", cleanup.main, [chapter]):
        return 1

    # ---- 9. 登记章节验证状态（未登记时自动 init） ----
    if not args.no_track:
        print("\n=== [track update] ===")
        # --auto 自动取数（章节 .tex 实测 size/lines + 素材 reader 状态的 chunks），
        # 编排器不再手算，与手工 SOP 的 `track update --auto` 同源。
        # 验证状态如实登记：verify 通过 → verified（不传标记）；
        # verify 退出 2 离线/TRANSIENT → pending-verify（待复验，不污染已交付信号）；
        # --no-verify 显式跳过 → unverified（真未验）。绝不谎报「已验活」。
        track_argv = ["update", str(project), stem, "--auto"]
        if material:
            track_argv += ["--material", material]
        if not verified_passed:
            # verify 退出 2（离线/TRANSIENT）记 pending-verify；
            # --no-verify 显式跳过记 unverified（真未验）。
            if verify_pending:
                track_argv.append("--pending-verify")
            else:
                track_argv.append("--unverified")
        rc = track.main(track_argv)
        if rc != 0:
            print("=== [track update] 失败，但成品 PDF 已交付；可稍后手动 track update ===")
        else:
            print("=== [track update] OK ===")

    print("\n[chapter] 全流程通过 ✅")
    return 0


if __name__ == "__main__":
    sys.exit(main())
