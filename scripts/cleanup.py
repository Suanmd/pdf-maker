# -*- coding: utf-8 -*-
"""cleanup.py - 单章编译完成后清理临时文件。

用途
----
单章编译通过、并已确认 PDF 无误后，把成品 PDF 落盘并归档中间产物，
保持章节目录干净（只留源文件、成品 PDF 与常驻脚本）。

处理项（顺序敏感）
------------------
1. 先把 _tmp.pdf 复制为 <stem>.pdf（必须在删 _tmp.* 之前，否则会误删成品 PDF）。
2. 归档中间文件：chN.tex / 附录X_ch.tex、_tmp.*（fix.py 等常驻脚本保留，不删）。

保留项
------
<stem>.tex、<stem>.pdf、以及本 skill 的常驻脚本（scripts/ 下所有 .py）。

是否调用
--------
由单章编译 SOP 在「xelatex 两遍 + 视觉确认之后」调用，每章必跑。

调用时机
--------
python cleanup.py [CH_NUM]     # 默认第 1 章
python cleanup.py 3
python cleanup.py 附录A

路径解析规则
------------
统一由 common.workdir_for() 定位含 _tmp.pdf 的章工作目录（CWD 优先，脚本目录兜底）。
因此从书稿项目根目录用全路径调用即可（skill 装在哪都行），也可 cd 进章目录执行。

退出码：始终为 0。
"""
import argparse
import os
import shutil
import sys
from pathlib import Path

from common import setup_utf8, workdir_for, mid_name_for

setup_utf8()


def _stem_of(arg: str) -> str:
    return arg if arg.startswith("附录") else f"第{arg}章"


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="cleanup.py",
        description="单章编译后清理：落盘成品 PDF + 归档中间文件（移动而非删除）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python cleanup.py 4       # 清理第 4 章\n"
            "  python cleanup.py 附录A    # 清理附录 A\n\n"
            "中间文件移动到 _tmp_old/（移动而非删除，便于追溯）。"
        ),
    )
    parser.add_argument("chapter", nargs="?", default="1",
                        help="章节号（数字 N 或 附录X），默认第 1 章")
    args = parser.parse_args()

    work = workdir_for(args.chapter)
    stem = _stem_of(args.chapter)

    # 1. 先复制成品 PDF（顺序敏感：必须在清 _tmp.* 之前）
    tmp_pdf = work / "_tmp.pdf"
    target_pdf = work / f"{stem}.pdf"
    if tmp_pdf.exists():
        target_pdf.write_bytes(tmp_pdf.read_bytes())
        print(f"[cleanup.py] Copied: _tmp.pdf -> {target_pdf.name}")
    else:
        print(f"[cleanup.py] 警告：未找到 {tmp_pdf}，跳过复制")

    # 2. 归档中间文件到 _tmp_old/（用「移动/重命名」而非 unlink 删除）
    #    部分运行环境带 safe-delete 守卫，会拦截 unlink 并在其内部线程崩溃，
    #    导致 cleanup.py 以非零退出、临时文件残留。改用同目录 rename（移动），
    #    不触发删除守卫，且天然保留中间产物便于事后追溯。
    #    为避免覆盖旧归档再次触发删除，碰撞时追加序号（全程零 unlink）。
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
            print(f"[cleanup.py] Archived: {name} -> _tmp_old/")
        except OSError as e:
            print(f"[cleanup.py] Skip: {name} ({e})")

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
    return 0


if __name__ == "__main__":
    sys.exit(main())
