# -*- coding: utf-8 -*-
"""cleanup.py - 单章编译完成后清理临时文件。

用途
----
单章编译通过、并已确认 PDF 无误后，把成品 PDF 落盘并删除中间产物，
保持章节目录干净（只留源文件、成品 PDF 与常驻脚本）。

处理项（顺序敏感）
------------------
1. 先把 ``_tmp.pdf`` 复制为 ``第N章.pdf``（必须在删 ``_tmp.*`` 之前，
   否则会误删成品 PDF）。
2. 删除中间文件：``chN.tex``、``find_urls.py``（一次性工具）、``_tmp.*``。

保留项
------
``第N章.tex``、``第N章.pdf``、以及本 skill 的常驻脚本
（fix.py / verify_urls.py / check.py / check_balance.py / cleanup.py 等）。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「xelatex 两遍 + 视觉确认之后」调用，每章必跑。
用法：
    python cleanup.py [CH_NUM]     # 默认第 1 章
    python cleanup.py 3

退出码：始终为 0。
"""
import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

HERE = Path(__file__).parent
CH_NUM = int(sys.argv[1]) if len(sys.argv) > 1 else 1

# 1. 先复制成品 PDF（顺序敏感：必须在清 _tmp.* 之前）
tmp_pdf = HERE / "_tmp.pdf"
target_pdf = HERE / f"第{CH_NUM}章.pdf"
if tmp_pdf.exists():
    target_pdf.write_bytes(tmp_pdf.read_bytes())
    print(f"[cleanup.py] Copied: _tmp.pdf -> {target_pdf.name}")
else:
    print(f"[cleanup.py] 警告：未找到 {tmp_pdf.name}，跳过复制")

# 2. 删除中间文件 / 一次性工具
kill_files = [f"ch{CH_NUM}.tex", "find_urls.py"]
intermediate_globs = [
    "_tmp.aux", "_tmp.log", "_tmp.out", "_tmp.toc",
    "_tmp.synctex.gz", "_tmp.tex", "_tmp.pdf",
]
for name in kill_files:
    f = HERE / name
    if f.exists():
        try:
            f.unlink()
            print(f"[cleanup.py] Removed: {f.name}")
        except OSError as e:
            print(f"[cleanup.py] Skip: {f.name} ({e})")

for pat in intermediate_globs:
    for f in HERE.glob(pat):
        try:
            f.unlink()
            print(f"[cleanup.py] Removed: {f.name}")
        except OSError as e:
            print(f"[cleanup.py] Skip: {f.name} ({e})")
