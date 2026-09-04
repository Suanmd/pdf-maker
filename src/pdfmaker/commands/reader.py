# -*- coding: utf-8 -*-
"""reader —— 素材强制阅读的「三阶段」校验工具。

在动笔写一个章节之前，确保对应素材已被「逐块完整通读」，而不是只读前几行、
grep 摘要或凭记忆下笔。本工具负责「读单个素材文件」的全流程校验。

子命令
------
    python -m pdfmaker reader index  <file>             # 总览 + 初始化阅读状态
    python -m pdfmaker reader chunk  <file> N [--reset] # 读第 N 个 chunk（0-based）
    python -m pdfmaker reader verify <file>             # 校验 5 字段，全过才算读完
    python -m pdfmaker reader toc    <file>             # 仅打印标题树（不计 chunk）
    python -m pdfmaker reader ingest <file>             # 一键通读：index + 逐块读完 + verify
    python -m pdfmaker reader clean  [--global] [dir] [--apply]
                                                        # 清除阅读状态：全局缓存（默认）或遗留点文件

阅读状态文件
------------
统一存放于**全局缓存目录** ``READER_STATE_DIR``（macOS 默认 ``~/Library/Caches/pdfmaker/reader``，
其他平台默认 ``~/.cache/pdfmaker/reader``，可用环境变量 ``PDFMAKER_READER_STATE_DIR`` 覆盖），
命名为 ``reader-state-{hash8}.json``，**不再散落在内容目录**，避免污染书稿项目。
旧版遗留在内容目录的 ``.reader-state-*.json`` 点文件可用 ``reader clean <dir> --apply`` 清理。

校验 5 字段（缺一不可，verify 才算读完）
--------------------------------------
1. chunks_read 连续无缺口（覆盖所有规划 chunk）
2. 最后一个 chunk 到达 EOF
3. 行被完整覆盖（由 1+2 推出）
4. 文件字节数与初始记录一致（未被中途改动）
5. 至少读过 1 个 chunk
"""

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path

# 容量参数（单 chunk 行数上限 / 单 read 字节上限）统一从 config 收口；
# 用模块别名访问（而非 from ... import X），确保运行时 toml / 环境变量覆盖真正生效。
import pdfmaker.core.config as cfg
from pdfmaker.core.paths import setup_utf8

setup_utf8()

SECTION_PATTERNS = [
    (re.compile(r"^\s*---\s*$"), "---"),
    (re.compile(r"^\s*###\s+(.+)$"), "###"),
    (re.compile(r"^\s*##\s+(.+)$"), "##"),
    (re.compile(r"^\s*#\s+(.+)$"), "#"),
]


def detect_kind(text_sample: str) -> str:
    """判断素材语种：中文占比 >30% 返回 ``"cn"``，否则 ``"en"``（用于选分块策略）。"""
    if not text_sample:
        return "en"
    cn = sum(1 for c in text_sample if "一" <= c <= "鿿")
    return "cn" if cn / len(text_sample) > 0.3 else "en"


def state_path(file: str) -> Path:
    """阅读状态文件存放于全局缓存目录（READER_STATE_DIR），不再污染内容目录。

    文件名取素材绝对路径的 md5 前 8 位（与旧版一致，保证同一文件状态可复现），
    但前缀不带前导点，区别于旧版散落在内容目录的 ``.reader-state-*.json``。
    """
    p = Path(file).absolute()
    h = hashlib.md5(str(p).encode("utf-8")).hexdigest()[:8]
    cfg.READER_STATE_DIR.mkdir(parents=True, exist_ok=True)
    return cfg.READER_STATE_DIR / f"reader-state-{h}.json"


def load_state(file: str) -> dict:
    """读取素材的阅读状态；缺失或损坏时返回一份空白初始状态。"""
    sp = state_path(file)
    if sp.exists():
        try:
            return json.loads(sp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {
        "chunks_read": [], "total_chunks": 0, "file": "", "total_lines": 0,
        "size_bytes": 0, "kind": "cn", "chunk_size": cfg.CHUNK_SIZE_CN,
    }


def save_state(file: str, st: dict) -> None:
    """把素材的阅读状态写回全局缓存目录。"""
    state_path(file).write_text(
        json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def die(msg: str) -> None:
    """打印错误并以 exit 1 终止（参数/文件类硬错误的统一出口）。"""
    print(f"ERROR: {msg}", file=sys.stderr)
    sys.exit(1)


def cmd_index(file: str) -> None:
    """总览素材文件（标题/URL/章节数）并初始化阅读状态（index 子命令）。"""
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
    chunk_size = cfg.CHUNK_SIZE_CN if kind == "cn" else cfg.CHUNK_SIZE_EN

    if kind == "cn":
        chunks_planned = (len(lines) + chunk_size - 1) // chunk_size
    else:
        bytes_chunks = (len(data) + cfg.MAX_BYTES_PER_READ - 1) // cfg.MAX_BYTES_PER_READ
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
    print(f'[NEXT] python -m pdfmaker reader chunk "{file}" 0', file=sys.stderr)


def cmd_chunk(file: str, n: int, reset: bool = False) -> None:
    """打印并登记第 N 个 chunk（0-based）为已读（chunk 子命令）。"""
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    st = load_state(file)
    if reset:
        st["chunks_read"] = []
    total_chunks = st.get("total_chunks", 0)
    if total_chunks == 0:
        die("state 未初始化。先跑 `reader index <file>`")
    if n < 0 or n >= total_chunks:
        die(f"chunk 索引 {n} 超出范围 [0, {total_chunks})")
    chunk_size = st.get("chunk_size", cfg.CHUNK_SIZE_CN)
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


def cmd_ingest(file: str, force: bool = False) -> int:
    """一键通读：index + 逐块读完所有 chunk + verify。返回 verify 的退出码。

    缓存短路：若既有阅读状态显示「该文件已完整读完且字节数未变」（状态按绝对
    路径 md5 键控、index 时记录 size_bytes），则跳过逐块重读直接 verify——
    章节编排器（chapter）与手工 SOP 会对同一素材重复 ingest，未变更时重读全文
    是纯噪音。``--force`` 强制重读。
    """
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")

    if not force:
        st = load_state(file)
        total = st.get("total_chunks", 0)
        if (total > 0
                and sorted(st.get("chunks_read", [])) == list(range(total))
                and st.get("size_bytes") == p.stat().st_size):
            print(f"[ingest] 素材自上次完整阅读后未变更（{p.stat().st_size} bytes / "
                  f"{total} chunks 已读），跳过逐块重读；`--force` 可强制重读。")
            return cmd_verify(file)

    cmd_index(file)
    st = load_state(file)
    total = st.get("total_chunks", 0)
    if total == 0:
        die("index 未规划出 chunk，无法 ingest")

    print(f"\n=== INGEST: 逐块通读 {total} 个 chunk ===", file=sys.stderr)
    for n in range(total):
        cmd_chunk(file, n)

    return cmd_verify(file)


def cmd_verify(file: str) -> int:
    """校验 5 字段（chunk 连续/末块到 EOF/行覆盖/字节一致/至少读 1 块），全过返回 0。"""
    p = Path(file)
    if not p.exists():
        die(f"FILE NOT FOUND: {file}")
    st = load_state(file)
    if st.get("total_chunks", 0) == 0:
        print("VERIFY: ❌ FAIL — state 未初始化。先跑 `reader index <file>`")
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
        print(f"  NEXT: python -m pdfmaker reader chunk \"{file}\" {missing[0]}")
    return 1


def cmd_clean(target: str | None, global_cache: bool, apply: bool) -> int:
    """清除 reader 阅读状态文件。

    - 默认 / ``--global`` / 未给 target：清理**全局缓存目录** ``READER_STATE_DIR``
      （新版本状态存放处），匹配 ``reader-state-*.json``（无前导点）。
    - 传入 ``<dir>``：扫描该目录（含子目录）里的遗留 ``.reader-state-*.json`` 点文件
      （旧版本散落在内容目录里的状态），用于清理老项目。

    默认仅试运行（列出待删文件不删除），加 ``--apply`` 才真正删除。
    """
    if global_cache or not target or target == ".":
        base = cfg.READER_STATE_DIR
        pattern = "reader-state-*.json"
        label = f"全局缓存目录 {base}"
        found = sorted(base.glob(pattern)) if base.exists() else []
    else:
        base = Path(target)
        if not base.exists():
            die(f"PATH NOT FOUND: {target}")
        pattern = ".reader-state-*.json"
        label = f"目录 {base}（遗留点文件）"
        found = sorted(base.rglob(pattern))

    if not found:
        print(f"[reader clean] 未发现匹配文件（{label}）")
        return 0

    total_bytes = 0
    for sp in found:
        sz = sp.stat().st_size
        total_bytes += sz
        if apply:
            sp.unlink()
            print(f"  [DELETE] {sp} ({sz} bytes)")
        else:
            print(f"  [DRY-RUN] {sp} ({sz} bytes)")
    verb = "已删除" if apply else "（试运行，未删除）"
    print(f"[reader clean] {verb} {len(found)} 个文件，约 {total_bytes} bytes。")
    if not apply:
        print("  加 --apply 真正删除。")
    return 0


def cmd_toc(file: str) -> None:
    """打印素材 Markdown 标题树（含层级与行号，不计入 chunk）。"""
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker reader",
        description="素材强制阅读三阶段校验工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker reader ingest \"<素材 .md 路径>\"     # 一键：index + 逐块通读 + verify\n"
            "  python -m pdfmaker reader index  \"<素材 .md 路径>\"\n"
            "  python -m pdfmaker reader chunk  \"<素材 .md 路径>\" 0\n"
            "  python -m pdfmaker reader verify \"<素材 .md 路径>\"\n\n"
            "说明: <file> 必须是你项目里任意真实的素材 .md 文件路径。"
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
    p_ingest = sub.add_parser("ingest", help="一键通读：index + 逐块读完 + verify（已读未变则缓存短路）")
    p_ingest.add_argument("file")
    p_ingest.add_argument("--force", action="store_true",
                          help="强制逐块重读（默认：素材自上次完整阅读后未变更则跳过重读）")
    p_toc = sub.add_parser("toc", help="仅打印标题树")
    p_toc.add_argument("file")
    p_clean = sub.add_parser("clean", help="清除阅读状态（全局缓存 / 遗留点文件）")
    p_clean.add_argument("target", nargs="?", default=None,
                         help="扫描目录（清理遗留 .reader-state-*.json 点文件）；省略则用全局缓存")
    p_clean.add_argument("--global", dest="global_cache", action="store_true",
                         help="清理全局 reader 状态缓存目录（未给 target 时的默认行为）")
    p_clean.add_argument("--apply", action="store_true",
                         help="真正删除（默认仅试运行，列出待删文件）")

    args = parser.parse_args(argv)
    if args.cmd == "index":
        cmd_index(args.file)
        return 0
    elif args.cmd == "chunk":
        cmd_chunk(args.file, args.n, args.reset)
        return 0
    elif args.cmd == "verify":
        return cmd_verify(args.file)
    elif args.cmd == "ingest":
        return cmd_ingest(args.file, force=args.force)
    elif args.cmd == "toc":
        cmd_toc(args.file)
        return 0
    elif args.cmd == "clean":
        return cmd_clean(args.target, args.global_cache, args.apply)
    return 2


if __name__ == "__main__":
    sys.exit(main())
