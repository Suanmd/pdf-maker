# -*- coding: utf-8 -*-
"""chapter —— 单章九步 SOP 一键编排器（Phase SOP 串联入口）。

把逐章写作的九步质量关卡串成一条「遇阻断即停」的流水线，免去手工逐步跑、
容易漏步或忘设环境变量之苦：

    reader ingest（可选，--material 指定素材笔记）
      → fix（URL 规范化 + 图宽上限 + 生成 chN.tex/_tmp.tex）
      → check（字数硬门禁，可阻断）
      → balance（结构/引用均衡，阻断级可阻断）
      → verify（联网验活，exit 1 阻断；exit 2 离线仅警告继续）
      → xelatex ×2（在章目录内编译）
      → overflow（编译日志体检，阻断即停）
      → cleanup（落盘成品 PDF + 归档中间文件）
      → track update（登记章节已验证状态；章节未登记时自动 init）

所有阈值（字数下限 / 配图下限 / 验活探针主机 / xelatex 路径等）均继承项目
``.pdfmaker.toml`` 或环境变量，无需每步手动 export。

退出码：0 全流程通过并交付；非 0 任一步阻断（字数不足 / 引用不闭合 / 死链 /
编译失败 / 日志体检未过）。失败时中间产物保留以便排查。
"""

import argparse
import sys
from pathlib import Path

from pdfmaker.core import paths, setup_utf8, xelatex as xel
import pdfmaker.core.config as cfg
from pdfmaker.commands import balance, check, cleanup, fix, overflow, track, verify, xref
from pdfmaker.commands import reader
from pdfmaker.commands import scaffold
from pdfmaker.commands.build import find_xelatex


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


def ensure_chapter_skeleton(chapter: str, material: "str | None",
                            force_scaffold: bool, cwd: str) -> bool:
    """章文件缺失时按素材自动生成合规骨架（#9 接进标准 SOP）。

    触发条件：章号为数字 + 目标 ``第N章/第N章.tex`` 不存在 +（提供了
    ``--material`` 或显式 ``--scaffold``）。这样标准 SOP 命令
    ``python -m pdfmaker chapter N --material <素材.md>`` 在章文件缺失时
    **默认**就从合规富骨架起稿，从源头杜绝"从空白手敲"导致的三线表/codeblock
    样式漂移——无需记忆 ``--scaffold`` 显式开关。

    返回 ``True`` 表示本次新生成了骨架；``False`` 表示跳过（文件已存在或无需生成）。
    非破坏性：文件已存在一律跳过，绝不覆盖用户已有成果。
    """
    if not chapter.isdigit():
        return False
    stem = paths.stem_of(chapter)
    cand = Path(cwd) / stem / f"{stem}.tex"
    if cand.exists():
        return False
    if not (material or force_scaffold):
        # 既没素材也没显式标志：不自动生成，保留原行为（交由 resolve_source 报错提示）
        return False
    print(f"\n=== [scaffold] 章文件缺失，自动生成合规骨架 ===")
    scaffold.write_chapter(int(chapter), material=material, root=cwd, force=False)
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker chapter",
        description="单章九步 SOP 一键编排：reader→fix→check→balance→verify→xelatex×2→overflow→cleanup→track",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker chapter 3                 # 走完第 3 章全流程\n"
            "  python -m pdfmaker chapter 3 --material 素材-第3章.md  # 先强制阅读素材\n"
            "  python -m pdfmaker chapter 3 --no-verify     # 跳过联网验活（离线时）\n"
            "  python -m pdfmaker chapter 3 --no-track      # 不更新 materials.json\n\n"
            "在项目根目录执行；阈值自动继承项目 .pdfmaker.toml / 环境变量。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    parser.add_argument("--material", default=None,
                        help="素材笔记 .md 路径；传入则先跑 reader ingest 强制阅读")
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
    args = parser.parse_args(argv)

    setup_utf8()
    # 自动加载项目级配置（与 cli 一致，确保直接 python -m pdfmaker.commands.chapter 也生效）
    cfg.load_project_config()
    cfg.apply_project_config()

    chapter = args.chapter

    # 0.5 章文件缺失时按素材自动生成合规骨架（#9 治本，已接进标准 SOP，非破坏性）
    # 无需 --scaffold 显式开关：`chapter N --material` 在章文件缺失时即自动起合规骨架，
    # 从源头杜绝"从空白手敲"导致的三线表/codeblock 样式漂移。已有文件一律跳过。
    ensure_chapter_skeleton(chapter, args.material, args.scaffold, str(Path.cwd()))

    try:
        src = paths.resolve_source(chapter, "pdfmaker chapter")
    except SystemExit:
        return 2
    chdir = src.parent
    project = Path(args.project) if args.project else chdir.parent
    stem = paths.stem_of(chapter)

    print(f"[chapter] 章节源: {src}")
    print(f"[chapter] 章目录: {chdir}")
    print(f"[chapter] 项目根: {project}")

    # 1. 素材强制阅读（可选）；读取后从 reader 状态取真实 chunk 数，供 track 登记
    chunks_count = 0
    if args.material:
        if not _step("reader ingest", reader.main, ["ingest", args.material]):
            return 1
        try:
            chunks_count = int(reader.load_state(args.material).get("total_chunks", 0))
        except Exception:
            chunks_count = 0

    # 2. 预处理
    if not _step("fix", fix.main, [chapter]):
        return 1

    # 3. 字数硬门禁
    if not _step("check", check.main, [chapter]):
        return 1

    # 4. 结构/引用均衡
    if not _step("balance", balance.main, [chapter]):
        return 1

    # 4.5 跨章引用早期自检（非阻断）：仅校验本章，避免盲写「第N章」越界 / 跨章 \ref，
    # 把合并期才暴露的红线问题提前到单章阶段。
    _step("xref(self)", xref.main, [chapter, "--self-only"], block=False)

    # 5. 联网验活（exit 1 阻断；exit 2 离线仅警告继续）。
    # 状态语义：verify 返回 0 → verified（已验活）；
    # 返回 2（离线/TRANSIENT）→ pending-verify（待联网复验，不污染已交付信号）；
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

    # 6. xelatex 两遍（先确认可执行文件存在，否则给出清晰错误而非崩溃）
    xelatex = args.xelatex or cfg.XELATEX_BIN or find_xelatex()
    if not xelatex:
        print("=== [xelatex] 未找到 xelatex（--xelatex / .pdfmaker.toml xelatex / "
              "PATH 探测均失败），流程中止 ===")
        return 2
    for i in range(2):
        print(f"\n=== [xelatex 第 {i + 1} 遍] ===")
        rc = xel.compile(
            xelatex, "-halt-on-error", "-interaction=nonstopmode", "_tmp.tex", cwd=str(chdir)
        )
        if rc != 0:
            print(f"=== [xelatex] 失败（第 {i + 1} 遍，rc={rc}），流程中止 ===")
            return 1

    # 7. 编译日志体检（硬卡口）
    print("\n=== [overflow] ===")
    rc = overflow.main([str(chdir / "_tmp.log")])
    if rc != 0:
        print("=== [overflow] 未通过，流程中止（_tmp.log 已保留）===")
        return 1
    print("=== [overflow] OK ===")

    # 8. 落盘成品 PDF + 归档中间文件
    if not _step("cleanup", cleanup.main, [chapter]):
        return 1

    # 9. 登记章节验证状态（未登记时自动 init）
    if not args.no_track:
        size = src.stat().st_size
        total_lines = src.read_text(encoding="utf-8").count("\n")
        print("\n=== [track update] ===")
        # 传真实 chunks_count；验证状态如实登记：verify 通过 → verified（不传标记）；
        # verify 退出 2 离线/TRANSIENT → pending-verify（待复验，不污染已交付信号）；
        # --no-verify 显式跳过 → unverified（真未验）。绝不谎报「已验活」。
        track_argv = ["update", str(project), stem, str(size), str(total_lines), str(chunks_count)]
        if args.material:
            track_argv += ["--material", args.material]
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
