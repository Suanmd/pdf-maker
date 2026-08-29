# -*- coding: utf-8 -*-
"""track —— 章节 ↔ 素材阅读状态追踪（跨会话持久化）。

``reader`` 命令负责「读单个素材文件」；本命令负责「章节 → 已读状态」的映射与
跨会话持久化：让「某章素材是否已完整读完」成为可验证、可跨会话恢复的状态，
而不是靠记忆。

子命令
------
    python -m pdfmaker track init       <project_dir>              # 初始化 materials.json
    python -m pdfmaker track show       <project_dir>              # 显示当前状态
    python -m pdfmaker track check      <project_dir> <ch>         # 检查某章已读状态
    python -m pdfmaker track update     <proj> <ch> <size> <lines> <N>  # verify 后回调
    python -m pdfmaker track auto-init  <proj> <ch>                # init + check 组合
    python -m pdfmaker track bib-audit  <project_dir>              # 引用质量审计

设计约束
--------
本工具 **不内置、也不要求建立任何「章节→素材」映射文件**——那是项目特定数据，
不应随包分发，也不该写死在代码里。素材就是你手头的 ``*.md`` 文件：直接用
``reader`` 指向它读取即可（``reader ingest`` 一键通读）。本命令只负责把
「某章素材是否已完整读完」作为跨会话状态持久化到项目本地的 ``materials.json``：
``init`` 会依据书稿自身的 ``第N章/`` ``附录X/`` 目录自动建立章节条目，读完后用
``update`` 标记 verified。素材放在哪、叫什么名，包一概不做假定。

退出码
------
    init/show/auto-init/update : 0（异常时非 0）
    check  : 已 verified 返回 0，未 verified 返回 2，缺文件/缺章节返回 1
    bib-audit : 全部过线返回 0，存在警告返回 1
"""

import sys
import json
import argparse
import hashlib
import re
from pathlib import Path
from datetime import datetime, timezone, timedelta

from pdfmaker.core.paths import setup_utf8
import pdfmaker.core.config as cfg
from pdfmaker.core.chapters import chapter_sort_key

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


def find_search_root(project_dir: str) -> Path:
    """素材发现的根目录：整个书稿项目根目录（不预设任何子目录结构）。

    真正「布局无关」——素材放在项目下任何位置、叫任何名字都会被 discover_sources
    扫到。这里只作为 init 提示用，不约束 reader 的读取路径。
    """
    return Path(project_dir)


def enumerate_chapters(project_dir: str) -> list[str]:
    """依据书稿自身的章节目录（第N章 / 附录X）列举章节名。

    仅使用本工具自己的书籍结构约定，绝不假定任何素材布局或命名。
    """
    base = Path(project_dir)
    names = []
    for d in sorted(base.iterdir(), key=chapter_sort_key):
        if not d.is_dir():
            continue
        if re.fullmatch(r"第\d+章", d.name) or re.fullmatch(r"附录[A-Za-z0-9]+", d.name):
            names.append(d.name)
    return names


def discover_sources(root: Path) -> dict:
    """在项目根目录下尽力发现素材文件（仅作提示，不预设任何命名/目录约定）。

    接受任意 `.md` / `.txt` 文件——目录、文件名、层级都随用户项目而定。
    """
    sources: dict[str, str] = {}
    if not root.exists():
        return sources
    for f in sorted(root.rglob("*")):
        if f.is_file() and f.suffix.lower() in (".md", ".txt"):
            sources[f.name] = str(f)
    return sources


def cmd_init(project_dir: str) -> int:
    mp = materials_path(project_dir)
    root = find_search_root(project_dir)
    if mp.exists():
        st = json.loads(mp.read_text(encoding="utf-8"))
    else:
        st = {
            "version": 1,
            "project": Path(project_dir).name,
            "created_at": iso_now(),
            "chapters": {},
        }
    # 仅依据书稿自身的章节目录建立章节条目，不预设任何素材布局
    for ch in enumerate_chapters(project_dir):
        if ch not in st["chapters"]:
            st["chapters"][ch] = {
                "source_files": [],
                "verified": None,
                "size_bytes": 0,
                "total_lines": 0,
                "chunks_read_count": 0,
                "status": "pending",
            }
    sources = discover_sources(root)
    st["updated_at"] = iso_now()
    mp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[INIT] wrote {mp}")
    print(f"[CHAPTERS] {len(st['chapters'])}")
    print(f"[SOURCES DISCOVERED] {len(sources)}")
    for fn, path in sources.items():
        print(f"  {fn} -> {path}")
    if not sources:
        print("\n提示：当前项目下未发现 .md/.txt 素材文件。")
        print("素材无需固定布局——直接用 reader 指向你手头的任意 .md 文件即可，读完跑 update 登记章节。")
    return 0


def cmd_show(project_dir: str) -> int:
    """打印 materials.json 当前各章节追踪状态（show 子命令）。"""
    mp = materials_path(project_dir)
    if not mp.exists():
        print(f"NO materials.json at {mp}. Run init first.")
        return 1
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
    return 0


def cmd_check(project_dir: str, chapter: str) -> int:
    """检查某章是否已 verified：已验活返回 0，未验活/pending-verify 返回 2，缺文件返回 1。"""
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
        srcs = info.get("resolved_files", info.get("source_files", []))
        src_label = srcs[0] if srcs else "（未关联素材）"
        tail = f"，关联素材：{src_label}" if srcs else ""
        print(f"📖 章节正文 {human_size(info.get('size_bytes', 0))} / "
              f"{info.get('total_lines', 0)} 行 / {info.get('chunks_read_count', 0)} chunks 已登记 verify ✅{tail}")
        # #175：verified 后若源 .tex 被改坏，给出过期告警（不修改返回码，避免破坏 SOP）。
        stored = info.get("content_hash")
        if stored:
            cur = _hash_chapter_tex(project_dir, chapter)
            if cur is not None and cur != stored:
                print("⚠️ STALE：源 .tex 自 verified 后已变更，verified 状态可能已过期；"
                      "请重跑 `track stale` 确认，必要时重跑 check/verify/overflow 后 track update。")
        return 0
    if info.get("status") == "pending-verify":
        # 离线/TRANSIENT 的「待复验」态，区别于真未验(unverified)。
        print(f"⏳ {chapter} PENDING-VERIFY（离线/TRANSIENT，待联网复验至 verify exit 0）:")
        print(f"   status: {info.get('status')}")
        print(f"   size: {human_size(info.get('size_bytes', 0))}")
        print(f"   lines: {info.get('total_lines', 0)}")
        print(f"   chunks: {info.get('chunks_read_count', 0)}")
        print(f"   next: 联网后跑 `pdfmaker verify {chapter}` 至 exit 0，再重跑 track update")
        return 2
    print(f"❌ {chapter} NOT verified yet.")
    print(f"   status: {info.get('status')}")
    print(f"   source_files: {info.get('source_files')}")
    print(f"   next: 跑素材阅读 SOP 逐 chunk 通读")
    return 2


def cmd_update(project_dir: str, chapter: str, size_bytes: int, total_lines: int,
                chunks_count: int, verified: bool = True, pending: bool = False,
                material: "str | None" = None) -> int:
    mp = materials_path(project_dir)
    if not mp.exists():
        # materials.json 缺失：自动 init（按磁盘章节目录建条目），再登记本章
        print(f"[update] materials.json 未找到，先自动 init：{mp}")
        cmd_init(project_dir)
    if not mp.exists():
        print("❌ materials.json 仍缺失，无法登记")
        return 1
    st = json.loads(mp.read_text(encoding="utf-8"))
    if chapter not in st["chapters"]:
        # 兜底：章节未纳入 init 枚举（如全新章节）时补登，免去顺序依赖 papercut
        st["chapters"][chapter] = {
            "source_files": [], "verified": None,
            "size_bytes": 0, "total_lines": 0,
            "chunks_read_count": 0, "status": "pending",
        }
    st["chapters"][chapter].update({
        "size_bytes": int(size_bytes),
        "total_lines": int(total_lines),
        "chunks_read_count": int(chunks_count),
    })
    # 关联素材（若给出）：并入 source_files（去重），不覆盖既有记录，便于 track check 追溯
    if material:
        prev = st["chapters"][chapter].get("source_files") or []
        merged, seen = [], set()
        for s in prev + [material]:
            if s not in seen:
                seen.add(s)
                merged.append(s)
        st["chapters"][chapter]["source_files"] = merged
    if verified:
        st["chapters"][chapter].update({
            "verified": iso_now(),
            "status": "verified",
            "content_hash": _hash_chapter_tex(project_dir, chapter),  # #175：记录源指纹
        })
    elif pending:
        # 待联网复验（verify 退出 2：离线/TRANSIENT）。与「真未验/DEAD」
        # (unverified) 区分——不写 verified 时间戳、不谎报已验活，但也不粗暴标脏，
        # 避免「作者已核验、PDF 真实可交付」的章节被反复打回 unverified、与已交付章节状态不一致。
        st["chapters"][chapter].update({
            "verified": None,
            "status": "pending-verify",
            "content_hash": None,
        })
    else:
        # 真未验活（如 chapter --no-verify 显式跳过、或 verify 发现 DEAD/截断）：标记为
        # unverified，撤销任何旧的 verified 时间戳，避免 track check 给出错误的安全信号。
        st["chapters"][chapter].update({
            "verified": None,
            "status": "unverified",
            "content_hash": None,
        })
    st["updated_at"] = iso_now()
    mp.write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[UPDATED] {chapter} -> {st['chapters'][chapter]['status']}")
    return 0


def cmd_auto_init(project_dir: str, chapter: str) -> int:
    """materials.json 缺失时先 init，再 check 该章（auto-init 子命令）。"""
    mp = materials_path(project_dir)
    if not mp.exists():
        cmd_init(project_dir)
        print()
    return cmd_check(project_dir, chapter)


def _chapter_tex_path(project_dir: str, chapter: str) -> "Path | None":
    """由 project_dir + 章节名解析章节 .tex 路径（兼容 第N章 / 附录X / 纯数字）。"""
    base = Path(project_dir)
    if chapter.startswith("附录"):
        ch_dir, stem = base / chapter, chapter
    elif chapter.startswith("第") and "章" in chapter:
        ch_dir, stem = base / chapter, chapter
    else:
        ch_dir, stem = base / f"第{chapter}章", f"第{chapter}章"
    return _resolve_chapter_tex(ch_dir, stem)


def _hash_chapter_tex(project_dir: str, chapter: str) -> "str | None":
    """计算章节 .tex 的 sha256（用于 verified 后检测源文件是否被改动，#175）。"""
    p = _chapter_tex_path(project_dir, chapter)
    if p is None or not p.exists():
        return None
    return hashlib.sha256(p.read_bytes()).hexdigest()


def cmd_stale(project_dir: str, chapter: str) -> int:
    """检测某章 verified 状态是否过期（源 .tex 自 verified 后被改动，#175）。

    防御「track 不回退」信任陷阱：章节标记 verified 后若被手动改坏，materials.json
    不会自动回退。本命令比对当前源文件 sha256 与 verified 时记录的指纹。

    退出码：0 新鲜（未变更）/ 1 过期（已变更或源缺失）/ 2 未 verified 或无指纹记录。
    """
    mp = materials_path(project_dir)
    if not mp.exists():
        print(f"❌ NO materials.json at {mp}")
        return 1
    st = json.loads(mp.read_text(encoding="utf-8"))
    if chapter not in st["chapters"]:
        print(f"❌ chapter '{chapter}' not in materials.json")
        return 1
    info = st["chapters"][chapter]
    if info.get("status") != "verified" or not info.get("verified"):
        print(f"⚠️ {chapter} 未 verified（状态 {info.get('status')}），无新鲜度可查")
        return 2
    stored = info.get("content_hash")
    if not stored:
        print(f"⚠️ {chapter} 已 verified 但无 content_hash（旧版 track 记录），无法判定新鲜度；"
              "请重跑 track update 刷新")
        return 2
    cur = _hash_chapter_tex(project_dir, chapter)
    if cur is None:
        print(f"❌ {chapter} 源 .tex 不存在，无法判定新鲜度")
        return 1
    if cur == stored:
        print(f"✅ {chapter} 源文件自 verified 后未变更（新鲜）")
        return 0
    print(f"⚠️ STALE：{chapter} 源 .tex 自 verified 后已变更，verified 状态可能已过期")
    print(f"    请重跑 check / verify / overflow 后重新 track update")
    return 1


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


def _resolve_chapter_tex(ch_dir: Path, stem: str) -> "Path | None":
    """定位章节 .tex：优先 <stem>.tex；否则在章目录内 glob 任意 *.tex（排除 _tmp.tex）。

    去除对「第n章/第n章.tex」命名的硬编码依赖，兼容其他命名约定。
    """
    preferred = ch_dir / f"{stem}.tex"
    if preferred.exists():
        return preferred
    cands = [p for p in sorted(ch_dir.glob("*.tex")) if p.name != "_tmp.tex"]
    return cands[0] if cands else None


def cmd_bib_audit(project_dir: str) -> int:
    """引用质量审计：统计每章维基占比与权威源数量，超阈值告警（bib-audit 子命令）。"""
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
            ch_dir = Path(project_dir) / f"第{n}章"
            stem = f"第{n}章"
        else:
            ch_dir = Path(project_dir) / f"附录{n}"
            stem = f"附录{n}"
        tex = _resolve_chapter_tex(ch_dir, stem)
        if tex is None:
            print(f"{ch:<10} - 在 {ch_dir} 未找到章节 .tex，跳过")
            continue
        content = tex.read_text(encoding="utf-8")
        urls = re.findall(r"\\url\{([^}]+)\}", content)
        urls += re.findall(r"\\href\{([^}]+)\}\{", content)
        if not urls:
            print(f"{ch:<10} - 无 URL，跳过")
            continue
        wiki = sum(1 for u in urls if any(h in u for h in cfg.WIKI_HINTS))
        auth = sum(1 for u in urls if any(d in u for d in cfg.AUTHORITY_HINTS))
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker track",
        description="章节 ↔ 素材阅读状态追踪（跨会话持久化）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "示例:\n"
            "  python -m pdfmaker track init      \"<PROJECT_DIR>\"\n"
            "  python -m pdfmaker track show      \"<PROJECT_DIR>\"\n"
            "  python -m pdfmaker track check     \"<PROJECT_DIR>\" 第4章\n"
            "  python -m pdfmaker track update    \"<PROJECT_DIR>\" 第4章 123456 1000 5\n"
            "  python -m pdfmaker track bib-audit \"<PROJECT_DIR>\"\n\n"
            "注意:\n"
            "  - <PROJECT_DIR> 为你的图书项目根目录（含 materials.json 与各 第N章/ 子目录），\n"
            "    不限定具体盘符或路径，按你的实际环境填写即可。\n"
            "  - check / update 必须同时传 <project_dir> 和 <chapter>（缺一不可）。\n"
            "  - update 的三个整数由编排器（chapter）传入，反映「章节」自身而非素材:\n"
            "      <size_bytes>   章节 .tex 文件字节数\n"
            "      <total_lines>  章节 .tex 总行数\n"
            "      <chunks_count> 已读素材 chunk 数（无 --material / 未指定素材时为 0）\n"
            "  - 可选 --material <素材.md>：把该素材记入 source_files，便于 track check 追溯。\n"
            "  - --unverified：标记本章未验活（如 chapter --no-verify 跳过、或 verify 退出 2 离线时）。"
        ),
    )
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_init = sub.add_parser("init", help="初始化 materials.json")
    p_init.add_argument("project_dir", help="书稿项目根目录（含 materials.json）")
    p_show = sub.add_parser("show", help="显示当前状态")
    p_show.add_argument("project_dir", help="书稿项目根目录")
    p_check = sub.add_parser("check", help="检查某章已读状态")
    p_check.add_argument("project_dir", help="书稿项目根目录")
    p_check.add_argument("chapter", help="章节名，如 第4章")
    p_stale = sub.add_parser("stale", help="检测某章 verified 是否过期（源文件改坏，#175）")
    p_stale.add_argument("project_dir", help="书稿项目根目录")
    p_stale.add_argument("chapter", help="章节名，如 第4章")
    p_update = sub.add_parser("update", help="verify 后回调登记")
    p_update.add_argument("project_dir", help="书稿项目根目录")
    p_update.add_argument("chapter", help="章节名，如 第4章")
    p_update.add_argument("size_bytes", type=int, help="章节 .tex 文件字节数")
    p_update.add_argument("total_lines", type=int, help="章节 .tex 总行数")
    p_update.add_argument("chunks_count", type=int, help="已读素材 chunk 数（无 --material 时为 0）")
    p_update.add_argument("--material", default=None,
                          help="关联素材文件路径（写入 source_files，便于 track check 追溯）")
    p_update.add_argument("--unverified", action="store_true",
                          help="标记本章真未验活（如 chapter --no-verify 显式跳过、或 verify 发现 DEAD/截断链接）")
    p_update.add_argument("--pending-verify", action="store_true",
                          help="标记本章待联网复验（verify 退出 2：离线/TRANSIENT）。区别于 --unverified（真未验/死链），不污染已交付信号")
    p_auto = sub.add_parser("auto-init", help="init + check 组合")
    p_auto.add_argument("project_dir", help="书稿项目根目录")
    p_auto.add_argument("chapter", help="章节名，如 第4章")
    p_audit = sub.add_parser("bib-audit", help="引用质量审计")
    p_audit.add_argument("project_dir", help="书稿项目根目录")

    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cmd_init(args.project_dir)
    elif args.cmd == "show":
        return cmd_show(args.project_dir)
    elif args.cmd == "check":
        return cmd_check(args.project_dir, args.chapter)
    elif args.cmd == "stale":
        return cmd_stale(args.project_dir, args.chapter)
    elif args.cmd == "update":
        return cmd_update(args.project_dir, args.chapter, args.size_bytes,
                          args.total_lines, args.chunks_count,
                          verified=not (args.unverified or args.pending_verify),
                          pending=args.pending_verify, material=args.material)
    elif args.cmd == "auto-init":
        return cmd_auto_init(args.project_dir, args.chapter)
    elif args.cmd == "bib-audit":
        return cmd_bib_audit(args.project_dir)
    return 2


if __name__ == "__main__":
    sys.exit(main())
