# -*- coding: utf-8 -*-
"""check_overflow.py - xelatex 编译日志体检（体检之三，阻断级）。

用途
----
编译完成后，解析 xelatex 生成的 .log，汇总「会让成品出问题的」信号，
作为单章 / 整书交付前的最后一道卡口。

检查项（阻断级：存在即非零退出）
---------------------------------
- Overfull \\hbox        ：段落 / 显示公式 / 节点文字溢出页面宽度。
- Missing character     ：字体缺失（豆腐块 / 空白）。
- multiply-defined      ：同一 \\label 跨章重名，导致 \\ref 指向错误编号。
- undefined references  ：引用断链（??）。
- LaTeX Error / Fatal   ：编译致命错误。

非阻断（仅提示）：Underfull \\hbox（松散度警告，不强制）。

发现 Overfull 时会打印前若干条所在行（含 at lines X--Y），便于直接定位源码。

是否调用
--------
由单章编译 SOP 在「xelatex 两遍之后」调用；整书合并后同样调用一次。
属于硬卡口：存在阻断级信号必须先修源码再交付。

调用时机
--------
python check_overflow.py [LOGFILE]
python check_overflow.py _tmp.log
python check_overflow.py            # 自动寻找 _tmp.log / main.log / book.log

注意（Windows）：Python 不识别 Git Bash 风格的 /d/path/...，请传原生路径
（如 C:/path/to/_tmp.log，盘符依你的环境而定）或相对路径 _tmp.log；否则会报「找不到日志文件」。

退出码：0 阻断级信号全清；非 0 存在阻断级问题或找不到日志。
"""
import argparse
import re
import sys
from pathlib import Path

from common import setup_utf8

setup_utf8()

MAX_SHOWN = 8   # Overfull 明细最多打印几条


def _search_up(name: str) -> Path | None:
    """从 cwd 向上回溯（到盘符根），找名为 name 的日志文件。"""
    cur = Path.cwd()
    seen: set[Path] = set()
    for _ in range(12):
        cand = cur / name
        if cand.exists():
            return cand
        parent = cur.parent
        if parent == cur or parent in seen:
            break
        seen.add(parent)
        cur = parent
    return None


def find_log() -> Path | None:
    """在当前目录、脚本目录、脚本父目录，以及 cwd 祖先链中寻找常见日志文件名。"""
    here = Path(__file__).parent
    bases = [Path.cwd(), here, here.parent]
    cur = Path.cwd()
    for _ in range(12):
        cur = cur.parent
        if cur == cur.parent:
            break
        bases.append(cur)
    for cand in ("_tmp.log", "main.log", "book.log"):
        for base in bases:
            p = base / cand
            if p.exists():
                return p
    return None


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="check_overflow.py",
        description="xelatex 编译日志体检（Overfull / 缺失字符 / 重复 label / 断链 / Fatal）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python check_overflow.py _tmp.log   # 单章日志\n"
            "  python check_overflow.py main.log    # 整书日志\n"
            "  python check_overflow.py             # 自动寻找 _tmp.log / main.log"
        ),
    )
    parser.add_argument("log", nargs="?", help="编译日志路径（省略则自动寻找）")
    args = parser.parse_args()

    if args.log:
        log = Path(args.log)
        if not log.is_absolute():
            log = Path.cwd() / log
        if not log.exists():
            # 显式路径找不到 → 向上回溯找同名日志 / 常规 find_log（不向下 rglob，避免跨项目误匹配）
            alt = _search_up(Path(args.log).name) or find_log()
            if alt:
                log = alt
    else:
        log = find_log()
    if log is None or not log.exists():
        raise SystemExit(
            "[check_overflow.py] 找不到日志文件。请显式传入路径"
            "（如 python check_overflow.py _tmp.log），或先完成一次编译。"
        )

    txt = log.read_text(encoding="utf-8", errors="ignore")

    overfull = re.findall(r"Overfull \\(?:hbox|vbox)", txt)
    missing = re.findall(r"Missing character", txt)
    multidef = re.findall(r"multiply-defined", txt)
    undefref = re.findall(r"(?:undefined references?|Reference .* undefined)", txt)
    fatal = re.findall(r"(?:Fatal error|Emergency stop|LaTeX Error)", txt)
    underfull = re.findall(r"Underfull \\(?:hbox|vbox)", txt)

    print(f"日志：{log}")
    print(f"  Overfull \\hbox        : {len(overfull)}  {'<-- 阻断' if overfull else '(OK)'}")
    print(f"  Missing character     : {len(missing)}  {'<-- 阻断' if missing else '(OK)'}")
    print(f"  multiply-defined label: {len(multidef)}  {'<-- 阻断' if multidef else '(OK)'}")
    print(f"  undefined references  : {len(undefref)}  {'<-- 阻断' if undefref else '(OK)'}")
    print(f"  Fatal/Error           : {len(fatal)}  {'<-- 阻断' if fatal else '(OK)'}")
    print(f"  Underfull \\hbox       : {len(underfull)}  (仅警告，不阻断)")

    if overfull:
        # 逐行抓取：LaTeX 会把 "Overfull \hbox (Xpt too wide) in paragraph at lines A--B"
        # 打在同一行，这一行本身就含定位信息，直接展示即可。
        print("\n前几条 Overfull 位置（去重）：")
        seen: set[str] = set()
        for line in re.findall(r"^Overfull.*$", txt, flags=re.MULTILINE):
            snippet = line.strip()
            key = snippet[:60]
            if key in seen:
                continue
            seen.add(key)
            print(f"  - {snippet[:140]}")
            if len(seen) >= MAX_SHOWN:
                break
        if not seen:
            print("  （日志中未能提取到明细行，请直接搜索日志里的 Overfull）")

    if missing:
        chars = sorted(set(re.findall(r"Missing character: There is no (\S+)", txt)))
        if chars:
            print(f"\n缺失字符（去重，前 20 个）：{' '.join(chars[:20])}")

    blocking = bool(overfull or missing or multidef or undefref or fatal)
    if blocking:
        print("\n[FAIL] 存在阻断级问题，必须先修源码再交付。")
        return 1
    print("\n[OK] 阻断级信号全清（Underfull 若过多可顺手优化，不阻断）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
