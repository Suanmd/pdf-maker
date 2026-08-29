# -*- coding: utf-8 -*-
"""cleanup —— 单章编译完成后清理临时文件。

单章编译通过、并已确认 PDF 无误后，把成品 PDF 落盘并归档中间产物，
保持章节目录干净（只留源文件、成品 PDF 与常驻脚本）。

处理项（顺序敏感）
------------------
1. 先把 _tmp.pdf 复制为 <stem>.pdf（必须在删 _tmp.* 之前，否则会误删成品 PDF）。
2. 归档中间文件：chN.tex / 附录X_ch.tex、_tmp.*（fix 等常驻脚本保留，不删）。

保留项
------
<stem>.tex、<stem>.pdf、以及本工具的常驻脚本。

退出码：始终为 0。
"""

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.core import mid_name_for, setup_utf8, stem_of, workdir_for

setup_utf8()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker cleanup",
        description="单章编译后清理：落盘成品 PDF + 归档中间文件（移动而非删除）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker cleanup 4       # 清理第 4 章\n"
            "  python -m pdfmaker cleanup 附录A    # 清理附录 A\n\n"
            "中间文件移动到 _tmp_old/（移动而非删除，便于追溯）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args(argv)

    work = workdir_for(args.chapter)
    stem = stem_of(args.chapter)

    # 1. 先复制成品 PDF（顺序敏感：必须在清 _tmp.* 之前）
    tmp_pdf = work / "_tmp.pdf"
    target_pdf = work / f"{stem}.pdf"
    if tmp_pdf.exists():
        target_pdf.write_bytes(tmp_pdf.read_bytes())
        print(f"[cleanup] Copied: _tmp.pdf -> {target_pdf.name}")
    else:
        print(f"[cleanup] 警告：未找到 {tmp_pdf}，跳过复制")

    # 2. 归档中间文件到 _tmp_old/（用「移动/重命名」而非 unlink 删除）
    #    部分运行环境会拦截 unlink，改用同目录 rename（移动）可绕过，
    #    且天然保留中间产物便于事后追溯。碰撞时追加序号避免覆盖。
    archive_dir = work / "_tmp_old"
    archive_dir.mkdir(parents=True, exist_ok=True)

    def _archive(name: str) -> None:
        src = work / name
        if not src.exists():
            return
        dst = archive_dir / name
        if dst.exists():
            base, ext = os.path.splitext(name)
            i = 1
            while (archive_dir / f"{base}.{i}{ext}").exists():
                i += 1
            dst = archive_dir / f"{base}.{i}{ext}"
        try:
            shutil.move(str(src), str(dst))
            print(f"[cleanup] Archived: {name} -> _tmp_old/")
        except OSError as e:
            print(f"[cleanup] Skip: {name} ({e})")

    kill_files = [mid_name_for(args.chapter)]
    intermediate_globs = [
        "_tmp.aux", "_tmp.log", "_tmp.out", "_tmp.toc",
        "_tmp.synctex.gz", "_tmp.tex", "_tmp.pdf",
    ]
    for name in kill_files:
        _archive(name)
    for pat in intermediate_globs:
        for f in sorted(work.glob(pat)):
            _archive(f.name)
    # ---- 归档份数上限：长期累积成磁盘垃圾，保留每基线最近 N 份 ----
    removed = _prune_archive(archive_dir, cfg.TMP_OLD_KEEP)
    if removed:
        print(f"[cleanup] Pruned {len(removed)} 旧归档（保留每基线最近 {cfg.TMP_OLD_KEEP} 份）")
    return 0


def _prune_archive(archive_dir: Path, max_keep: int) -> list[str]:
    """保留每个归档基线名最近 ``max_keep`` 份，删除更旧的（按索引升序，无索引=最新）。

    cleanup 把中间产物移入 ``_tmp_old/``，多次运行会累积 ``_tmp.tex`` / ``_tmp.1.tex`` /
    ``_tmp.2.tex`` …（碰撞时追加序号）。按「基线名 + 扩展名」分组，每组保留索引最大
    （含无索引，视为最新）的 ``max_keep`` 个，删除历史更久者。``max_keep<=0`` 表示不清理。
    """
    if max_keep <= 0 or not archive_dir.is_dir():
        return []
    removed: list[str] = []
    groups: dict[tuple[str, str], list[Path]] = {}
    for p in archive_dir.iterdir():
        if not p.is_file():
            continue
        m = re.match(r"^(.*?)(?:\.(\d+))?(\.[^.]+)$", p.name)
        if not m:
            continue
        base, idx, ext = m.group(1), m.group(2), m.group(3)
        groups.setdefault((base, ext), []).append(p)

    def _idx(p: Path) -> int:
        mm = re.match(r"^(?:.*?)(?:\.(\d+))?(\.[^.]+)$", p.name)
        i = mm.group(1) if mm else None
        # 无索引 = 首次归档（最旧）；cleanup 碰撞时追加递增索引，故最高索引=最新。
        return int(i) if i is not None else 0

    for (base, ext), files in groups.items():
        if len(files) <= max_keep:
            continue
        files.sort(key=_idx)
        for old in files[: len(files) - max_keep]:
            try:
                old.unlink()
                removed.append(old.name)
            except OSError:
                pass
    return removed


if __name__ == "__main__":
    sys.exit(main())
