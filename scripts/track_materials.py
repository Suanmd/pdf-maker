# -*- coding: utf-8 -*-
"""track_materials.py - 章节 ↔ 素材阅读状态追踪（跨会话持久化）。

用途
----
reader.py 负责「读单个素材文件」。本脚本负责「章节 → 多个素材」的映射与跨会话
持久化：让「某章素材是否已完整读完」成为可验证、跨会话的状态，而不是靠记忆。

子命令
------
    python track_materials.py init <project_dir>            # 初始化 materials.json
    python track_materials.py show <project_dir>            # 显示当前状态
    python track_materials.py check <project_dir> <ch>      # 检查某章已读状态
    python track_materials.py update <proj> <ch> <size> <lines> <N>  # verify 后回调
    python track_materials.py auto-init <proj> <ch>         # init + check 组合
    python track_materials.py bib-audit <project_dir>       # 引用质量审计

章节 → 素材映射
--------------
默认不内置任何项目特定的映射（旧版写死的映射已移除）。请在本脚本同目录维护一份
``materials.map.json``（``{"第1章": ["path/to/src1", ...], ...}``），或在 init 后
直接编辑 ``materials.json`` 的 ``chapters[<ch>].source_files`` 字段。

是否调用 / 何时调用
------------------
由「素材阅读 SOP」调用：写某章前 init（若未建），读完后 update 标记 verified。
bib-audit 在整书合并前作为引用质量参考调用（不阻断）。
"""
import sys
import json
import argparse
from pathlib import Path
from datetime import datetime, timezone, timedelta
import re

from common import setup_utf8

setup_utf8()

# 时区（用于 verified_at 时间戳，可按需调整）
TZ = timezone(timedelta(hours=8))


def iso_now() -> str:
    return datetime.now(TZ).strftime("%Y-%m-%dT%H:%M:%S+08:00")


def human_size(n: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if n < 1024:
            return f"{n:.0f} {unit}" if unit == "B" else f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} TB"


def materials_path(project_dir: str) -> Path:
    return Path(project_dir) / "materials.json"


def map_path() -> Path:
    return Path(__file__).parent / "materials.map.json"


def find_search_root() -> Path:
    """素材根目录的候选位置（可在此扩展，或放一份 materials.map.json）。"""
    candidates = [
        Path("materials"),
        Path("sources"),
        Path("corpus"),
        Path("data/raw"),
    ]
    for c in candidates:
        if c.exists():
            return c
    return Path("materials")


def load_chapter_map() -> dict:
    mp = map_path()
    if mp.exists():
        try:
            return json.loads(mp.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def discover_sources(root: Path) -> dict:
    """发现素材文件：默认匹配 *-content.txt 与 report.md。"""
    sources = {}
    if not root.exists():
        return sources
    for pat in ("*-content.txt", "report.md"):
        for f in sorted(root.rglob(pat)):
            sources[f.name] = str(f)
    return sources


def cmd_init(project_dir: str) -> None:
    mp = materials_path(project_dir)
    root = find_search_root()
    if mp.exists():
        st = json.loads(mp.read_text(encoding="utf-8"))
    else:
        st = {
            "version": 1,
            "project": Path(project_dir).name,
            "created_at": iso_now(),
            "chapters": {},
        }
    sources = discover_sources(root)
    user_map = load_chapter_map()
    for ch, files in user_map.items():
        if ch not in st["chapters"]:
            st["chapters"][ch] = {
                "source_files": files,
                "verified": None,
                "size_bytes": 0,
                "total_lines": 0,
                "chunks_read_count": 0,
                "status": "pending",
            }
    st["updated_at"] = iso_now()
    mp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INIT] wrote {mp}")
    print(f"[SOURCES DISCOVERED] {len(sources)}")
    for fn, path in sources.items():
        print(f"  {fn} -> {path}")
    if not user_map:
        print("\n提示：未找到 materials.map.json，chapters 为空。")
        print("请在脚本同目录创建 materials.map.json 定义 章节→素材 映射，")


def cmd_show(project_dir: str) -> None:
    mp = materials_path(project_dir)
    if not mp.exists():
        print(f"NO materials.json at {mp}. Run init first.")
        sys.exit(1)
    st = json.loads(mp.read_text(encoding="utf-8"))
    print(f"=== materials.json @ {mp} ===")
    print(f"project: {st.get('project', '?')}  |  created: {st.get('created_at', '?')}  |  updated: {st.get('updated_at', '?')}")
    print()
    for ch, info in st["chapters"].items():
        status = info.get("status", "?")
        verified = info.get("verified") or "—"
        size = info.get("size_bytes", 0)
        lines = info.get("total_lines", 0)
        chunks = info.get("chunks_read_count", 0)
        print(f"  [{status:>10}] {ch}: verified={verified}  size={human_size(size)}  lines={lines}  chunks={chunks}")
        for src in info.get("source_files", []):
            print(f"        src: {src}")


def cmd_check(project_dir: str, chapter: str) -> int:
    mp = materials_path(project_dir)
    if not mp.exists():
        print(f"❌ NO materials.json at {mp}")
        return 1
    st = json.loads(mp.read_text(encoding="utf-8"))
    if chapter not in st["chapters"]:
        print(f"❌ chapter '{chapter}' not in materials.json")
        return 1
    info = st["chapters"][chapter]
    if info.get("status") == "verified" and info.get("verified"):
        print(f"✅ {chapter} is verified:")
        print(f"   verified_at: {info['verified']}")
        print(f"   size: {human_size(info.get('size_bytes', 0))}")
        print(f"   lines: {info.get('total_lines', 0)}")
        print(f"   chunks: {info.get('chunks_read_count', 0)}")
        srcs = info.get("resolved_files", info["source_files"])
        print(f"📖 完整读完 {srcs[0] if srcs else info['source_files'][0]} "
              f"({human_size(info.get('size_bytes', 0))} / {info.get('total_lines', 0)} 行 / {info.get('chunks_read_count', 0)} chunks) verify ✅")
        return 0
    print(f"❌ {chapter} NOT verified yet.")
    print(f"   status: {info.get('status')}")
    print(f"   source_files: {info.get('source_files')}")
    print(f"   next: 跑素材阅读 SOP 逐 chunk 通读")
    return 2


def cmd_update(project_dir, chapter, size_bytes, total_lines, chunks_count):
    mp = materials_path(project_dir)
    if not mp.exists():
        print("❌ materials.json not found")
        return 1
    st = json.loads(mp.read_text(encoding="utf-8"))
    if chapter not in st["chapters"]:
        print(f"❌ chapter '{chapter}' not found")
        return 1
    st["chapters"][chapter].update({
        "verified": iso_now(),
        "size_bytes": int(size_bytes),
        "total_lines": int(total_lines),
        "chunks_read_count": int(chunks_count),
        "status": "verified",
    })
    st["updated_at"] = iso_now()
    mp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[UPDATED] {chapter} -> verified at {st['chapters'][chapter]['verified']}")
    return 0


def cmd_auto_init(project_dir: str, chapter: str) -> int:
    mp = materials_path(project_dir)
    if not mp.exists():
        cmd_init(project_dir)
        print()
    return cmd_check(project_dir, chapter)


def _ch_name_to_num(name: str):
    if name.startswith("第") and "章" in name:
        n = name[1:name.index("章")]
        try:
            return int(n)
        except ValueError:
            return None
    if name.startswith("附录"):
        return name.replace("附录", "")
    return None


# 引用质量审计用的「权威源」启发式域名（示例，可按领域替换）
AUTHORITY_HINTS = [
    "dx.doi.org", "doi.org", "arxiv.org", "plato.stanford.edu",
    "nature.com", "science.org", "onlinelibrary.wiley.com",
]

WIKI_HINTS = ["wikipedia.org", "wiki"]


def cmd_bib_audit(project_dir: str) -> int:
    mp = materials_path(project_dir)
    if not mp.exists():
        print(f"❌ materials.json not found: {mp}")
        return 1
    st = json.loads(mp.read_text(encoding="utf-8"))
    chapters = st.get("chapters", {})
    any_warn = False
    print("引用质量审计（建议：维基占比不过高、每章含若干权威源）")
    print()
    print(f"{'章节':<10} {'条目':<6} {'维基':<6} {'占比':<8} {'权威源':<8} 状态")
    print("-" * 60)
    for ch, info in sorted(chapters.items()):
        n = info.get("chapter_num")
        if n is None:
            n = _ch_name_to_num(ch)
        if n is None:
            print(f"{ch:<10} - 编号解析失败，跳过")
            continue
        if isinstance(n, int):
            tex = Path(project_dir) / f"第{n}章" / f"第{n}章.tex"
        else:
            tex = Path(project_dir) / f"附录{n}" / f"附录{n}.tex"
        if not tex.exists():
            print(f"{ch:<10} - {tex.name} 不存在，跳过")
            continue
        content = tex.read_text(encoding="utf-8")
        urls = re.findall(r"\\url\{([^}]+)\}", content)
        urls += re.findall(r"\\href\{([^}]+)\}\{", content)
        if not urls:
            print(f"{ch:<10} - 无 URL，跳过")
            continue
        wiki = sum(1 for u in urls if any(h in u for h in WIKI_HINTS))
        auth = sum(1 for u in urls if any(d in u for d in AUTHORITY_HINTS))
        pct = wiki / len(urls) * 100
        status = []
        if pct > 70:
            status.append(f"⚠️ 维基占 {pct:.0f}% > 70%")
            any_warn = True
        if auth < 3:
            status.append(f"⚠️ 权威源 {auth} < 3")
            any_warn = True
        if not status:
            status = ["✅ OK"]
        print(f"{ch:<10} {len(urls):<6} {wiki:<6} {pct:<7.0f}% {auth:<8} {' / '.join(status)}")
    print()
    if any_warn:
        print("⚠️  警告：以上章节建议补充权威源。")
        return 1
    print("✅ 所有章节过线")
    return 0


def main() -> None:
    p = argparse.ArgumentParser(
        prog="track_materials.py",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python track_materials.py init   \"<PROJECT_DIR>\"\n"
            "  python track_materials.py show   \"<PROJECT_DIR>\"\n"
            "  python track_materials.py check  \"<PROJECT_DIR>\" 第4章\n"
            "  python track_materials.py update \"<PROJECT_DIR>\" 第4章 123456 1000 5\n"
            "  python track_materials.py bib-audit \"<PROJECT_DIR>\"\n\n"
            "注意:\n"
            "  - <PROJECT_DIR> 为你的图书项目根目录（含 materials.json 与各 第N章/ 子目录），\n"
            "    不限定具体盘符或路径，按你的实际环境填写即可。\n"
            "  - check / update 必须同时传 <project_dir> 和 <chapter>（缺一不可）。\n"
            "  - update 的三个整数取自 reader.py verify 输出:\n"
            "      <size_bytes>   文件字节数   (verify 的 size_bytes)\n"
            "      <total_lines>  总行数\n"
            "      <chunks_count> 已读 chunk 数 (verify 的 chunks_read 数)"
        ),
    )
    sub = p.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init"); p_init.add_argument("project_dir", help="书稿项目根目录（含 materials.json）")
    p_show = sub.add_parser("show"); p_show.add_argument("project_dir", help="书稿项目根目录")
    p_check = sub.add_parser("check")
    p_check.add_argument("project_dir", help="书稿项目根目录")
    p_check.add_argument("chapter", help="章节名，如 第4章")
    p_update = sub.add_parser("update")
    p_update.add_argument("project_dir", help="书稿项目根目录")
    p_update.add_argument("chapter", help="章节名，如 第4章")
    p_update.add_argument("size_bytes", type=int, help="文件字节数（reader.py verify 的 size_bytes）")
    p_update.add_argument("total_lines", type=int, help="素材总行数")
    p_update.add_argument("chunks_count", type=int, help="已读 chunk 数（reader.py verify 的 chunks_read 数）")
    p_auto = sub.add_parser("auto-init")
    p_auto.add_argument("project_dir", help="书稿项目根目录")
    p_auto.add_argument("chapter", help="章节名，如 第4章")
    p_audit = sub.add_parser("bib-audit"); p_audit.add_argument("project_dir", help="书稿项目根目录")

    args = p.parse_args()
    if args.cmd == "init":
        cmd_init(args.project_dir)
    elif args.cmd == "show":
        cmd_show(args.project_dir)
    elif args.cmd == "check":
        sys.exit(cmd_check(args.project_dir, args.chapter))
    elif args.cmd == "update":
        sys.exit(cmd_update(args.project_dir, args.chapter, args.size_bytes, args.total_lines, args.chunks_count))
    elif args.cmd == "auto-init":
        sys.exit(cmd_auto_init(args.project_dir, args.chapter))
    elif args.cmd == "bib-audit":
        sys.exit(cmd_bib_audit(args.project_dir))


if __name__ == "__main__":
    main()
