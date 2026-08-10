# -*- coding: utf-8 -*-
"""
verify_urls.py — 联网验活（强制 SOP 步骤）

对单章源文件中的全部 URL（\\url{...} 与 \\href{http...}{...}）做**联网可达性检测**，
确保成书链接真实有效、无虚构 / 失效链接。这是发布级 PDF 的强制关卡：成书里出现一个
死链或胡编的链接都会摧毁可信度，故必须在每章交付前跑通。

用途：验证章节内所有 URL 真实可访问。
检查项：
  - 本地格式校验：URL 必须以 http(s):// 开头、纯 ASCII、无空白、可解析；
    含中文/空格/非法字符的原始 URL 直接判为格式缺陷（FORMAT）。
  - 联网验活：对每个 URL 发请求（GET + Range 限量），直连 2xx/3xx 即 LIVE；
    直连失败（网络错误 / 4xx / 5xx）再查 web.archive.org 快照，有快照记
    ARCHIVE（疑似真实但当前不可达，告警不阻断）；既直连失败又无快照记 DEAD。
是否调用：强制。单章 SOP 必跑；离线也须跑（会显式告警 exit 2）。
调用时机：fix.py / check / check_balance 之后，xelatex 编译之前（或之后均可，
          因为它只读源文件里的 URL，不依赖编译产物）。

退出码（SOP 据此决策）：
  0  全部 URL 验活通过（LIVE 或 ARCHIVE），可继续。
  1  存在 DEAD（失效/虚构）或 FORMAT（格式缺陷）链接 —— 必须修正后重跑。
  2  网络不可达（连通性探针失败）—— 预警：URL 未验活，须联网环境重跑，
     禁止把本章当作「URL 已验证」；若同时有 FORMAT 也会一并列出。

用法：
  python verify_urls.py N
  python verify_urls.py <chapter.tex 路径>
"""
import argparse
import json
import os
import re
import socket
import sys
import urllib.error
import urllib.request
import concurrent.futures
from pathlib import Path
from urllib.parse import urlsplit, quote

from common import setup_utf8, resolve_source

setup_utf8()

# ---- 可调参数（环境变量覆盖） ----
PER_URL_TIMEOUT = float(os.environ.get("PDFMAKER_URL_TIMEOUT", "30"))
WORKERS = int(os.environ.get("PDFMAKER_URL_WORKERS", "8"))
PROBE_TIMEOUT = 6.0
UA = "Mozilla/5.0 (pdf-maker verify_urls) compatible"

PROBE_HOSTS = [
    "https://example.com",
    "https://archive.org",
    "https://www.w3.org",
]

URL_RE = re.compile(r"\\url\{([^{}]+)\}|\\href\{([^{}]+)\}\{")
VERB_RE = re.compile(r"\\verb(.).*?\1", re.DOTALL)


def extract_urls(tex: str) -> list[str]:
    tex = VERB_RE.sub("", tex)  # 去掉 \verb|...| 逐字内容，避免误计
    out = []
    for m in URL_RE.finditer(tex):
        u = (m.group(1) or m.group(2)).strip()
        if u:
            out.append(u)
    return out


def format_ok(url: str) -> bool:
    """本地格式校验：ASCII、无空白、合法 scheme/host。"""
    if not url:
        return False
    if any(ord(c) > 127 for c in url):   # 含中文/非 ASCII
        return False
    if any(c.isspace() for c in url):     # 含空白
        return False
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return False
    if not parts.netloc:
        return False
    return True


def probe_network() -> bool:
    """快速连通性探针；全部失败视为离线。"""
    for h in PROBE_HOSTS:
        try:
            req = urllib.request.Request(h, headers={"User-Agent": UA}, method="GET")
            with urllib.request.urlopen(req, timeout=PROBE_TIMEOUT) as r:
                if r.status < 500:
                    return True
        except Exception:
            continue
    return False


def archive_has(url: str) -> tuple[bool, str]:
    """查 web.archive.org 是否有快照。返回 (有?, 快照URL)。"""
    api = "https://archive.org/wayback/available?url=" + quote(url, safe="")
    try:
        req = urllib.request.Request(api, headers={"User-Agent": UA}, method="GET")
        with urllib.request.urlopen(req, timeout=PER_URL_TIMEOUT) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            return True, snap.get("url", "")
    except Exception:
        pass
    return False, ""


def test_one(url: str) -> tuple[str, str, str]:
    """返回 (url, status, detail)。status ∈ LIVE/ARCHIVE/DEAD。"""
    try:
        req = urllib.request.Request(
            url, headers={"User-Agent": UA, "Range": "bytes=0-1023"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=PER_URL_TIMEOUT) as r:
            if r.status < 400:
                return (url, "LIVE", f"HTTP {r.status}")
    except urllib.error.HTTPError as e:
        code = e.code
        if code < 400:
            return (url, "LIVE", f"HTTP {code}")
        # 4xx/5xx：可能是反爬/已失效，转查 archive
    except Exception:
        pass
    # 直连失败 → 查 archive 兜底
    ok, snap = archive_has(url)
    if ok:
        return (url, "ARCHIVE", f"直连失败，archive.org 有快照：{snap}")
    return (url, "DEAD", "直连失败且无 archive 快照（疑似失效/虚构）")


def main() -> int:
    parser = argparse.ArgumentParser(
        prog="verify_urls.py",
        description="联网验活：逐 URL 检测可达性（exit 0/1/2）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码: 0 全过可继续 / 1 失效或虚构链接必须修 / 2 离线未验活须重跑。\n"
            "示例:\n"
            "  python verify_urls.py 4            # 验活第 4 章全部 URL\n"
            "  python verify_urls.py 第4章/第4章.tex  # 直接传 .tex 路径"
        ),
    )
    parser.add_argument("target", help="章节号 N（如 4）或直接传入的 .tex 路径")
    args = parser.parse_args()

    try:
        src = resolve_source(args.target, "verify_urls.py")
    except SystemExit:
        return 2

    tex = src.read_text(encoding="utf-8")
    urls = extract_urls(tex)
    # 去重保序
    seen: set[str] = set()
    uniq: list[str] = []
    for u in urls:
        if u not in seen:
            seen.add(u)
            uniq.append(u)

    print(f"[verify_urls] 源：{src}")
    if not uniq:
        print("  无 URL，跳过。")
        return 0

    # 本地格式校验（始终执行，不依赖网络）
    fmt_bad = [u for u in uniq if not format_ok(u)]

    # 连通性探针
    online = probe_network()
    results: list[tuple[str, str, str]] = []
    if online:
        print(f"  检测到网络可用，开始验活 {len(uniq)} 个 URL（并发 {WORKERS}，单 URL 超时 {PER_URL_TIMEOUT}s）…")
        with concurrent.futures.ThreadPoolExecutor(max_workers=WORKERS) as ex:
            results = list(ex.map(test_one, uniq))
    else:
        print("  ⚠️ 网络不可达（连通性探针失败）。URL 存活检测【未执行】。")

    # 汇总
    live = [r for r in results if r[1] == "LIVE"]
    arch = [r for r in results if r[1] == "ARCHIVE"]
    dead = [r for r in results if r[1] == "DEAD"]

    print("\n  结果明细：")
    for u in fmt_bad:
        print(f"    [FORMAT] {u}  （含中文/空格/非法字符，须改为纯 ASCII http(s) URL）")
    if online:
        for u, st, det in results:
            mark = {"LIVE": "✔", "ARCHIVE": "⚠", "DEAD": "✘"}[st]
            print(f"    [{mark} {st}] {u}  — {det}")

    print("\n  汇总：")
    print(f"    URL 总数     : {len(uniq)}")
    print(f"    格式缺陷     : {len(fmt_bad)}")
    if online:
        print(f"    验活通过(LIVE): {len(live)}")
        print(f"    存档兜底(ARCH): {len(arch)}")
        print(f"    失效/虚构(DEAD): {len(dead)}")

    if fmt_bad:
        print("\n  [FAIL] 存在格式缺陷 URL（FORMAT），必须先修正。")
        return 1
    if not online:
        print("\n  [WARN] 离线未验活（exit 2）：联网后必须重跑 verify_urls 拿到 exit 0，"
              "禁止把本章当作「URL 已验证」交付。")
        return 2
    if dead:
        print("\n  [FAIL] 存在失效/虚构链接（DEAD），必须替换为真实可访问 URL 后重跑。")
        return 1
    print("\n  [OK] 全部 URL 验活通过（LIVE + ARCHIVE）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
