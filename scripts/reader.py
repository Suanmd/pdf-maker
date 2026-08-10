# -*- coding: utf-8 -*-
"""reader.py - 素材强制阅读的「三阶段」校验工具。

用途
----
在动笔写一个章节之前，确保对应素材已被「逐块完整通读」，而不是只读前几行、
grep 摘要或凭记忆下笔。本工具负责「读单个素材文件」的全流程校验。

子命令
------
    python reader.py index  <file>             # 总览 + 初始化阅读状态
    python reader.py chunk  <file> N [--reset] # 读第 N 个 chunk（0-based）
    python reader.py verify <file>             # 校验 5 字段，全过才算读完
    python reader.py toc    <file>             # 仅打印标题树（不计 chunk）

阅读状态文件
------------
``<file>.reader-state-{hash8}.json``（与目标文件同目录）。

校验 5 字段（缺一不可，verify 才算读完）
---------------------------------------
1. chunks_read 连续无缺口（覆盖所有规划 chunk）
2. 最后一个 chunk 到达 EOF
3. 行被完整覆盖（由 1+2 推出）
4. 文件字节数与初始记录一致（未被中途改动）
5. 至少读过 1 个 chunk

是否调用 / 何时调用
------------------
由「素材阅读 SOP」在写任意章节之前调用：先 index，再逐 chunk 读完，最后 verify。
track_materials.py 负责「章节 → 多素材」的映射与跨会话持久化；本工具负责单文件。
"""
import sys
import json
import hashlib
import re
import argparse
from pathlib import Path

from common import setup_utf8

setup_utf8()

# 容量参数：单 chunk 行数上限与单 read 字节上限
CHUNK_SIZE_CN = 200
CHUNK_SIZE_EN = 320
MAX_BYTES_PER_READ = 30000

SECTION_PATTERNS = [
    (re.compile(r"^\s*---\s*$"), "---"),
    (re.compile(r"^\s*###\s+(.+)$"), "###"),
    (re.compile(r"^\s*##\s+(.+)$"), "##"),
    (re.compile(r"^\s*#\s+(.+)$"), "#"),
]


def detect_kind(text_sample: str) -> str:
    if not text_sample:
        return "en"
    cn = sum(1 for c in text_sample if "\u4e00" <= c <= "\u9fff")
    return "cn" if cn / len(text_sample) > 0.3 else "en"


def state_path(file: str) -> Path:
    p = Path(file)
    h = hashlib.md5(str(p.absolute()).encode("utf-8")).hexdigest()[:8]
    return p.parent / f".reader-state-{h}.json"


def load_state(file: str) -> dict:
    sp = state_path(file)
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "chunks_read": [], "total_chunks": 0, "file": "", "total_lines": 0,
        "size_bytes": 0, "kind": "cn", "chunk_size": CHUNK_SIZE_CN,
    }


def save_state(file: str, st: dict) -> None:
    state_path(file).write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def die(msg: str) -> None:
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_index(file: str) -> None:
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    data = p.read_bytes()
    text = data.decode("utf-8", errors="replace")
    lines = text.splitlines()

    sections = []
    for i, line in enumerate(lines):
        for pattern, level in SECTION_PATTERNS:
            m = pattern.match(line)
            if m:
                title = m.group(1) if m.lastindex else ""
                sections.append({"line": i + 1, "level": level, "title": title[:80]})
                break

    urls = re.findall(r"https?://[^\s)\]\"<>]+", text)
    urls_unique = sorted(set(urls))

    sample = text[:5000]
    kind = detect_kind(sample)
    chunk_size = CHUNK_SIZE_CN if kind == "cn" else CHUNK_SIZE_EN

    if kind == "cn":
        chunks_planned = (len(lines) + chunk_size - 1) // chunk_size
    else:
        bytes_chunks = (len(data) + MAX_BYTES_PER_READ - 1) // MAX_BYTES_PER_READ
        line_chunks = (len(lines) + chunk_size - 1) // chunk_size
        chunks_planned = max(bytes_chunks, line_chunks)

    report = {
        "file": str(p.absolute()),
        "size_bytes": len(data),
        "total_lines": len(lines),
        "total_chars": len(text),
        "sections_count": len(sections),
        "urls_unique_count": len(urls_unique),
        "kind": kind,
        "chunk_size": chunk_size,
        "chunks_planned": chunks_planned,
        "first_section": sections[0] if sections else None,
        "last_section": sections[-1] if sections else None,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    st = {
        "chunks_read": [],
        "total_chunks": chunks_planned,
        "file": str(p.absolute()),
        "total_lines": len(lines),
        "size_bytes": len(data),
        "kind": kind,
        "chunk_size": chunk_size,
    }
    save_state(file, st)
    print(f"\n[STATE WRITTEN] {state_path(file)}", file=sys.stderr)
    print(f'[NEXT] python reader.py chunk "{file}" 0', file=sys.stderr)


def cmd_chunk(file: str, n: int, reset: bool = False) -> None:
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    st = load_state(file)
    if reset:
        st["chunks_read"] = []
    total_chunks = st.get("total_chunks", 0)
    if total_chunks == 0:
        die("state 未初始化。先跑 `reader.py index <file>`")
    if n < 0 or n >= total_chunks:
        die(f"chunk 索引 {n} 超出范围 [0, {total_chunks})")
    chunk_size = st.get("chunk_size", CHUNK_SIZE_CN)
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    start = n * chunk_size
    end = min(start + chunk_size, len(lines))

    print(f"=== CHUNK {n + 1}/{total_chunks} lines {start + 1}-{end} (of {len(lines)}) ===")
    print(f"=== FILE: {p.name} ===")
    print()
    print("\n".join(lines[start:end]))
    print()
    print(f"=== END CHUNK {n + 1}/{total_chunks} ===")

    if n not in st["chunks_read"]:
        st["chunks_read"].append(n)
        st["chunks_read"].sort()
        st["last_chunk_end_line"] = end
        save_state(file, st)
    print(f"[PROGRESS] {len(st['chunks_read'])}/{total_chunks} chunks read", file=sys.stderr)


def cmd_verify(file: str) -> int:
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    st = load_state(file)
    if st.get("total_chunks", 0) == 0:
        print("VERIFY: ❌ FAIL — state 未初始化。先跑 `reader.py index <file>`")
        return 1

    file_bytes = p.stat().st_size
    with p.open(encoding="utf-8", errors="replace") as f:
        file_lines = sum(1 for _ in f)

    total_chunks = st["total_chunks"]
    chunks_read = sorted(st["chunks_read"])
    expected = list(range(total_chunks))

    f1_continuous = chunks_read == expected
    f2_last = bool(total_chunks) and (chunks_read and chunks_read[-1] == total_chunks - 1)
    f3_lines = f1_continuous and f2_last
    f4_bytes = file_bytes == st.get("size_bytes")
    f5_any = len(chunks_read) > 0

    print(f"VERIFY REPORT: {file}")
    print(f"  size_bytes: file={file_bytes} state={st.get('size_bytes')} match={f4_bytes}")
    print(f"  total_lines: file={file_lines} (cover via {total_chunks} chunks)")
    print(f"  1. chunks_planned: {total_chunks}")
    print(f"  2. chunks_read: {len(chunks_read)} -> {'CONTINUOUS' if f1_continuous else 'GAPPED'}")
    print(f"  3. last_chunk_eof: {f2_last}")
    print(f"  4. lines_fully_covered: {f3_lines}")
    print(f"  5. bytes_match: {f4_bytes}")
    print(f"  (read at least 1 chunk: {f5_any})")
    print()

    overall = f1_continuous and f2_last and f3_lines and f4_bytes and f5_any
    if overall:
        print("✅ VERIFY: OK — 5 字段全过，阅读完整。")
        return 0
    missing = [i for i in expected if i not in chunks_read]
    print(f"❌ VERIFY: FAIL — 缺失 {len(missing)} 个 chunk")
    if missing:
        print(f"  MISSING: {missing}")
        print(f"  NEXT: python reader.py chunk \"{file}\" {missing[0]}")
    return 1


def cmd_toc(file: str) -> None:
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    text = p.read_text(encoding="utf-8")
    lines = text.splitlines()
    print(f"=== TABLE OF CONTENTS: {p.name} ===")
    print(f"=== 总行数: {len(lines)} ===")
    print()
    for i, line in enumerate(lines):
        for pattern, level in SECTION_PATTERNS:
            m = pattern.match(line)
            if m:
                title = m.group(1) if m.lastindex else ""
                if title:
                    print(f"  L{i + 1:5d}  {level}  {title[:60]}")
                else:
                    print(f"  L{i + 1:5d}  {level}")
                break


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="reader.py",
        description="素材强制阅读三阶段校验工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例（本项目）:\n"
            "  python reader.py index  \"<素材 report.md 路径>\"\n"
            "  python reader.py chunk  \"<素材 report.md 路径>\" 0\n"
            "  python reader.py chunk  \"<素材 report.md 路径>\" 1   # 逐块读完所有 chunk\n"
            "  python reader.py verify \"<素材 report.md 路径>\"     # 5 字段全过才算读完\n\n"
            "说明: <file> 必须是真实素材报告路径（如 .../deep-search/xxx/report.md）。\n"
            "      verify 前必须先 index + 逐 chunk 读完，缺一步 verify 会直接 FAIL。"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_index = sub.add_parser("index", help="总览 + 初始化阅读状态")
    p_index.add_argument("file")
    p_chunk = sub.add_parser("chunk", help="读第 N 个 chunk")
    p_chunk.add_argument("file")
    p_chunk.add_argument("n", type=int)
    p_chunk.add_argument("--reset", action="store_true")
    p_verify = sub.add_parser("verify", help="校验 5 字段")
    p_verify.add_argument("file")
    p_toc = sub.add_parser("toc", help="仅打印标题树")
    p_toc.add_argument("file")

    args = parser.parse_args()
    if args.cmd == "index":
        cmd_index(args.file)
    elif args.cmd == "chunk":
        cmd_chunk(args.file, args.n, args.reset)
    elif args.cmd == "verify":
        sys.exit(cmd_verify(args.file))
    elif args.cmd == "toc":
        cmd_toc(args.file)


if __name__ == "__main__":
    main()
