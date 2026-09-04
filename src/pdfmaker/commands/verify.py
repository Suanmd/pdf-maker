# -*- coding: utf-8 -*-
"""verify —— 联网验活（强制 SOP 步骤）。

对章节源文件中的全部 URL（\\url{...} 与 \\href{http...}{...}）做**联网可达性检测**，
确保成书链接真实有效、无虚构 / 失效链接。这是发布级 PDF 的强制关卡：成书里出现一个
死链或胡编的链接都会摧毁可信度，故必须在每章交付前跑通。

检查项
------
- 本地格式校验：必须是纯 ASCII、无空白、http(s):// 开头的合法 URL。
- 截断检测：URL 含 Unicode 省略号「…」、3+ 连续点（非 :// 部分）或空白，判为残破链接。
- 联网验活（带重试与退避）：直连 2xx/3xx → LIVE；硬失效（404/410） → DEAD；
  鉴权/反爬/限流类（401/403/429） → 仍算 LIVE（地址有效，只是访问受限/限流，绝不误杀）；
  请求方式被拒（400/405/406/407） → 仍算 LIVE（服务端已响应、地址有效，绝不误杀）；
  超时/服务端错（5xx/408/425） → 自动重试；
  法律不可用（451） → 转查 archive.org 快照，有则 ARCHIVE 否则 DEAD；
  其余网络抖动 / 重试耗尽 → 查 archive，有快照 ARCHIVE，否则 TRANSIENT（按未验活，exit 2）。
- 软 404 内容指纹：页面返回 200 但内容指示「不存在/搜索/兜底」 → SUSPECT
  （warning 级，须人工确认，不阻断）。
- 豁免主机名单：``PDFMAKER_VERIFY_ALLOW_HOSTS`` / ``.pdfmaker.toml`` 的
  ``verify_allow_hosts`` 列出的主机（内网、SSO 鉴权后可见）跳过联网探测，标记
  EXEMPT——按已验证处理、不计 DEAD、不阻断；豁免只免验活，不免格式/截断预检。
- 结果缓存：``--cache <path>`` 持久化验活结果（默认缓存目录：macOS 为
  ``~/Library/Caches/pdfmaker/verify_cache.json``，其他平台为 ``~/.cache/pdfmaker/verify_cache.json``，
  新鲜期内且非 TRANSIENT 直接复用、不再联网）；``--refresh`` 强制重验。

退出码
------
0  全部 URL 验活通过（LIVE / ARCHIVE / EXEMPT），可继续。
1  存在 DEAD（硬失效/虚构）或 FORMAT（格式缺陷/截断）链接 —— 必须修正后重跑。
2  网络不可达（连通性探针失败）或存在 TRANSIENT（重试后仍无法确认、无快照）
   —— 预警：URL 未验活，须联网环境重跑；若同时有 FORMAT/DEAD 也会一并列出。
"""

import argparse
import concurrent.futures
import json
import re
import socket
import ssl
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, urlparse, urlsplit

# 可调参数统一从 core.config 收口；用模块别名访问（而非 from ... import X），
# 确保运行时 toml / 环境变量覆盖能真正生效。
import pdfmaker.core.config as cfg
from pdfmaker.core import collect_chapters, resolve_source, setup_utf8

setup_utf8()

URL_RE = re.compile(r"\\url\{([^{}]+)\}|\\href\{([^{}]+)\}\{")
VERB_RE = re.compile(r"\\verb(.).*?\1", re.DOTALL)


def extract_urls(tex: str) -> list[str]:
    """从 TeX 源码抽取全部 URL（\\url 与 \\href 的第一参数），剔除 \\verb 逐字内容。"""
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
    for h in cfg.PROBE_HOSTS:
        try:
            req = urllib.request.Request(h, headers={"User-Agent": cfg.USER_AGENT}, method="GET")
            with urllib.request.urlopen(req, timeout=cfg.PROBE_TIMEOUT) as r:
                if r.status < 500:
                    return True
        except Exception:
            continue
    return False


def archive_has(url: str, timeout: float | None = None) -> tuple[bool, str]:
    """查 web.archive.org 是否有快照。返回 (有?, 快照URL)。

    注意：timeout 默认 None，函数体内取 ``cfg.URL_TIMEOUT``。
    若默认写成 ``= cfg.URL_TIMEOUT``，会在模块导入时冻结——一旦项目用
    ``.pdfmaker.toml`` 的 ``url_timeout`` / 环境变量 ``PDFMAKER_URL_TIMEOUT`` 覆盖，
    覆盖值对 archive 兜底路径（_archive_or_dead 调用 archive_has 不传 timeout）
    完全不生效，与「运行时覆盖应处处生效」的约定矛盾。改为调用时解析 cfg 即可。
    """
    if timeout is None:
        timeout = cfg.URL_TIMEOUT
    api = "https://archive.org/wayback/available?url=" + quote(url, safe="")
    try:
        req = urllib.request.Request(api, headers={"User-Agent": cfg.USER_AGENT}, method="GET")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = json.loads(r.read().decode("utf-8", "replace"))
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available"):
            return True, snap.get("url", "")
    except Exception:
        pass
    return False, ""


def _probe_targets_reachable(urls: list[str], timeout: float | None = None) -> bool:
    """探针主机全不可达时，改测真实目标 URL 主机是否在线，避免误判离线（exit 2）。

    企业代理常允许目标学术站点但屏蔽 example/archive/w3 等探针主机；若默认探针全失败，
    改对前若干目标 URL 直接发一次短超时 GET，只要返回任意 HTTP 响应（含 4xx/5xx，
    说明主机在线）即视为在线，从而正常进入联网验活，而非误报「网络不可达」。
    """
    if timeout is None:
        timeout = min(cfg.PROBE_TIMEOUT, 5.0)
    for u in urls[:3]:
        try:
            req = urllib.request.Request(u, headers={"User-Agent": cfg.USER_AGENT}, method="GET")
            with urllib.request.urlopen(req, timeout=timeout) as r:
                _ = r.status
            return True
        except Exception:
            continue
    return False


def _classify_http(url: str, code: int) -> tuple[str, str] | None:
    """按 HTTP 状态码给出 (status, detail)；返回 None 表示「服务端瞬时错误，应重试」。

    规则：2xx/3xx → LIVE；404/410 → DEAD；5xx/408/425 → None（外层按瞬断重试，绝不判死）；
    401/403/429 → LIVE（鉴权/反爬/限流：地址有效但访问受限，绝不能误判死链）；
    400/405/406/407 → LIVE（服务端拒绝该请求方式但主机在线，地址有效，绝不误杀）；
    451 → 交由 archive 兜底（ARCHIVE 或 DEAD）；其余 → 交由 archive 兜底。
    """
    if code < 400:
        return ("LIVE", f"HTTP {code}")
    if code in cfg.HARD_DEAD:
        return ("DEAD", f"HTTP {code}（页面不存在，必须替换）")
    if code in cfg.SOFT_BLOCKED:
        return ("LIVE", f"HTTP {code}（地址有效，访问受限/限流，不判死链）")
    if code in cfg.METHOD_REJECTED:
        # 服务端已响应、主机在线、地址有效，仅拒绝我们的探测请求方式（如只接受 POST/HEAD），
        # 绝不因此误判死链。
        return ("LIVE", f"HTTP {code}（服务端拒绝该请求方式但主机在线，地址有效，不判死链）")
    if code in cfg.SERVER_ERROR:
        return None  # 服务端瞬时错误/超时：交由外层按瞬断重试，避免误杀真活链接
    return _archive_or_dead(url, code)


def _open_no_verify(url: str, timeout: float) -> int | None:
    """以「跳过证书校验」的上下文发起一次 GET，返回 HTTP 状态码；不可达返回 None。

    仅在直连因 TLS 校验失败（如 MITM 代理证书主机名不匹配）时作为兜底探测，
    用于区分「主机其实可达」与「主机真宕」。verify 仅做可达性判定，不改写任何 LaTeX。
    """
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            url, headers={"User-Agent": cfg.USER_AGENT, "Range": "bytes=0-1023"}, method="GET"
        )
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as r:
            return r.status
    except Exception:
        return None


def probe_one(url: str, retries: int | None = None,
              timeout: float | None = None) -> tuple[str, str, str]:
    """探测单个 URL，返回 (url, status, detail)。status ∈ LIVE/ARCHIVE/DEAD/TRANSIENT/SUSPECT。

    带重试与指数退避：网络抖动 / 5xx / 超时这类「疑似瞬断」会重试；
    404/410 这类硬失效直接判 DEAD；反爬类（4xx 非硬失效）转查 archive 兜底。

    TLS 校验失败（常见于 MITM 代理证书主机名不匹配）不再被误判为瞬断——
    改用「跳过证书校验」的上下文兜底重试一次：主机可达则按真实 HTTP 状态归类
    （活链照常 LIVE、404 仍判 DEAD），主机真宕则按瞬断重试。

    retries / timeout 默认 None，函数体内取 cfg.MAX_RETRIES / cfg.URL_TIMEOUT
    （运行时解析，保证 toml / 环境变量覆盖生效）。
    """
    if retries is None:
        retries = cfg.MAX_RETRIES
    if timeout is None:
        timeout = cfg.URL_TIMEOUT
    last_err = ""
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": cfg.USER_AGENT, "Range": "bytes=0-1023"}, method="GET"
            )
            with urllib.request.urlopen(req, timeout=timeout) as r:
                res = _classify_http(url, r.status)
                if res is not None:
                    status, detail = res
                    # 2xx 真实页面仍可能是「搜索/不存在/兜底」软 404。
                    # 读少量正文做内容指纹；命中强指示词则降级为 SUSPECT（warning，不阻断）。
                    if status == "LIVE":
                        body = _safe_read(r, 8192)
                        if _looks_soft404(body):
                            return (url, "SUSPECT",
                                    detail + " ⚠ 疑似软404(内容指纹, 须人工确认)")
                    return (url, status, detail)
                # None → 5xx，落入下方退避重试
        except urllib.error.HTTPError as e:
            res = _classify_http(url, e.code)
            if res is not None:
                status, detail = res
                if status == "LIVE":
                    body = _safe_read(e, 8192)
                    if _looks_soft404(body):
                        return (url, "SUSPECT",
                                detail + " ⚠ 疑似软404(内容指纹, 须人工确认)")
                return (url, status, detail)
            # None → 5xx，落入下方退避重试
        except urllib.error.URLError as e:
            # 注意：必须早于捕获 OSError 的分支——urllib.error.URLError 是 OSError 子类。
            reason = e.reason
            if isinstance(reason, ssl.SSLError):
                last_err = f"SSLError: {reason}"
                # TLS 校验失败：用跳过证书校验的上下文兜底重试，区分「代理拦截」与「真死链」
                status = _open_no_verify(url, timeout)
                if status is not None:
                    res = _classify_http(url, status)
                    if res is not None:
                        return (url, res[0], res[1])
                    # 兜底请求也拿到 5xx → 继续外层重试
                # 否则按瞬断重试
            else:
                last_err = f"{type(reason).__name__}: {reason}"
        except (socket.timeout, TimeoutError, ConnectionError, OSError) as e:
            last_err = f"{type(e).__name__}: {e}"
            # 瞬断：退避后重试
        if attempt < retries:
            time.sleep(cfg.BACKOFF * attempt)
    # 重试耗尽仍为瞬断 → archive 兜底，否则 TRANSIENT（按未验活）
    ok, snap = archive_has(url, timeout)
    if ok:
        return (url, "ARCHIVE", f"直连重试失败，archive.org 有快照：{snap}")
    return (url, "TRANSIENT", f"重试 {retries} 次仍网络异常（{last_err}），无存档，视为未验活")


def _archive_or_dead(url: str, code: int) -> tuple[str, str, str]:
    """反爬/鉴权/限流类 HTTP 状态码：查 archive 快照，有则 ARCHIVE，否则 DEAD。"""
    ok, snap = archive_has(url)
    if ok:
        return (url, "ARCHIVE", f"直连 HTTP {code}（疑似反爬），archive.org 有快照：{snap}")
    return (url, "DEAD", f"直连 HTTP {code}（反爬/失效，且无存档）")


def _looks_truncated(url: str) -> bool:
    """判断 URL 是否疑似被截断（Unicode 省略号 / 3+ 连续点 / 空白）。"""
    if "…" in url:
        return True
    if re.search(r"\.{3,}", url):
        return True
    if any(c.isspace() for c in url):
        return True
    return False


def _safe_read(resp, limit: int = 8192) -> str:
    """从响应对象安全读取至多 limit 字节并解码为文本（失败返回空串）。

    用于软 404 内容指纹检测；任何异常（无 .read / 解码失败 / 截断）都降级为空串，
    不影响验活主流程。
    """
    try:
        return resp.read(limit).decode("utf-8", "replace")
    except Exception:
        return ""


# 软 404 内容指纹（保守强指示词）：页面返回 200 但实为「搜索/不存在/兜底」页，
# 这类地址虽 200 却不是作者想引用的真实资源。仅当命中强指示词才标 SUSPECT（warning
# 级，不阻断），避免误伤正常学术页面。
_SOFT404_INDICATORS = [
    "page not found", "404 not found", "couldn't find", "could not find",
    "did not match any documents", "no results found", "nothing found",
    "找不到页面", "页面不存在", "没有找到", "搜索结果", "未找到相关",
    "wikipedia does not have", "article does not exist", "did you mean",
]


def _looks_soft404(body: str) -> bool:
    """轻量软 404 指纹：页面 200 但内容指示「不存在/搜索/兜底」 → 可疑。

    仅命中强指示词才返回 True（warning 级，不阻断验活结论）。body 为空直接 False。
    """
    if not body:
        return False
    low = body.lower()
    return any(k in low for k in _SOFT404_INDICATORS)


# ---- 验活豁免主机（内网 / 鉴权后可见的合法链接） ----
def _host_of(url: str) -> str:
    """提取 URL 的主机名（小写、不含端口）；解析失败返回空串。"""
    try:
        return (urlparse(url).hostname or "").lower()
    except Exception:
        return ""


def host_allowed(url: str, allow_hosts: list[str] | None = None) -> bool:
    """判断 URL 的主机是否在验活豁免名单（精确匹配或子域名后缀匹配）。

    企业内网、SSO 鉴权后可见的链接对 verify 的匿名探测必然 401/403 或超时，
    但它们是作者真实可访问的合法引用；列入 ``cfg.VERIFY_ALLOW_HOSTS`` 的主机
    跳过联网探测，标记 EXEMPT（按已验证处理、不计 DEAD、不阻断）。
    """
    hosts = cfg.VERIFY_ALLOW_HOSTS if allow_hosts is None else allow_hosts
    if not hosts:
        return False
    h = _host_of(url)
    if not h:
        return False
    for a in hosts:
        a = a.strip().lower()
        if not a:
            continue
        if h == a or h.endswith("." + a):
            return True
    return False


# ---- URL 验活结果缓存 ----
# 避免对同一个 URL 反复联网（多章 × 数十条链接极慢且受网络抖动影响），
# 也支持离线复用「上次已知结果」。仅持久化确定结果（LIVE/ARCHIVE/DEAD），
# 不缓存 TRANSIENT，以免误抑制后续重试。

def _cache_path(override: str | None) -> Path:
    """解析缓存文件路径：--cache 显式指定优先，否则用平台默认缓存目录。"""
    return Path(override) if override else (cfg.VERIFY_CACHE_DIR / cfg.VERIFY_CACHE_FILE)


def load_cache(path: Path) -> dict:
    """读取验活缓存；文件缺失或损坏时返回空字典。"""
    try:
        if path.exists():
            return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        pass
    return {}


def save_cache(path: Path, cache: dict) -> None:
    """写化验活缓存；任何 IO 异常静默降级（缓存失败不影响主流程）。"""
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception:
        pass


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="pdfmaker verify",
        description="联网验活：逐 URL 检测可达性（exit 0/1/2，带重试与截断检测）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "退出码: 0 全过可继续 / 1 失效或虚构/截断链接必须修 / 2 离线或未验活须重跑。\n"
            "示例:\n"
            "  python -m pdfmaker verify 4              # 验活第 4 章全部 URL\n"
            "  python -m pdfmaker verify 第4章/第4章.tex  # 直接传 .tex 路径\n"
            "  python -m pdfmaker verify .              # 验活整书全部章节 URL\n"
            "  python -m pdfmaker verify --retries 5 4  # 自定义重试次数\n"
            "  python -m pdfmaker verify --cache ~/Library/Caches/pdfmaker/verify_cache.json 4  # 自定义缓存路径\n"
            "  python -m pdfmaker verify --refresh 4    # 忽略缓存，强制重新验活"
        ),
    )
    parser.add_argument("target", help="章节号 N / .tex 路径 / 书稿根目录（'.' 验活全部章节）")
    parser.add_argument("--retries", type=int, default=cfg.MAX_RETRIES,
                        help=f"单 URL 重试次数（默认 {cfg.MAX_RETRIES}）")
    parser.add_argument("--timeout", type=float, default=cfg.URL_TIMEOUT,
                        help=f"单 URL 超时秒（默认 {cfg.URL_TIMEOUT}）")
    parser.add_argument("--cache", default=None,
                        help=f"验活结果缓存路径（默认 {cfg.VERIFY_CACHE_DIR / cfg.VERIFY_CACHE_FILE}）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存，强制重新联网验活全部 URL")
    args = parser.parse_args(argv)

    # ---- 解析 target：目录/'.' → 全部章节；否则单章 ----
    root = Path(args.target)
    if args.target in (".", "..") or (root.is_dir() and not root.resolve().name.endswith(".tex")):
        sources = collect_chapters(root.resolve())
        if not sources:
            print(f"[verify] 在 {root} 下未找到任何 第*章/附录*.tex")
            return 2
        print(f"[verify] 书稿模式：{len(sources)} 个章节将被验活")
    else:
        try:
            sources = [resolve_source(args.target, "pdfmaker verify")]
        except SystemExit:
            return 2

    # 合并所有源里的 URL（去重保序，记录来源章节便于定位）
    seen: set[str] = set()
    uniq: list[str] = []
    origin: dict[str, str] = {}
    for src in sources:
        tex = src.read_text(encoding="utf-8")
        for u in extract_urls(tex):
            if u not in seen:
                seen.add(u)
                uniq.append(u)
                origin[u] = src.name

    print(f"[verify] 源：{', '.join(s.name for s in sources)}")
    if not uniq:
        print("  无 URL，跳过。")
        return 0

    # ---- 本地格式 + 截断预检（始终执行，不依赖网络） ----
    fmt_bad: list[str] = []
    trunc_bad: list[str] = []
    for u in uniq:
        if not format_ok(u):
            fmt_bad.append(u)
        elif _looks_truncated(u):
            trunc_bad.append(u)

    # 豁免主机（内网/鉴权后可见）：跳过联网探测，直接按已验证（EXEMPT）计入结果。
    # 注意：豁免只免「验活」，不免格式/截断预检——残破链接即使在豁免主机也须修正。
    exempt = [
        u for u in uniq
        if u not in fmt_bad and u not in trunc_bad and host_allowed(u)
    ]
    if exempt:
        print(f"  ⛨ {len(exempt)} 个 URL 主机在豁免名单（cfg.VERIFY_ALLOW_HOSTS），"
              f"跳过联网探测，按已验证处理（EXEMPT）。")

    # 仅对格式合法、未截断、且不在豁免名单的 URL 发起联网检测
    testable = [
        u for u in uniq
        if u not in fmt_bad and u not in trunc_bad and u not in exempt
    ]

    # 连通性探针；默认探针主机全不可达时，回退探测真实目标主机是否在线
    online = probe_network()
    if not online and testable:
        if _probe_targets_reachable(testable):
            online = True
            print("  ⚠️ 默认探针主机不可达，但目标 URL 主机可连通，按在线处理。")
    results: list[tuple[str, str, str]] = []

    cache_path = _cache_path(args.cache)
    cache = {} if args.refresh else load_cache(cache_path)
    now = time.time()
    ttl = cfg.VERIFY_CACHE_TTL_DAYS * 86400

    if online:
        # 缓存命中（新鲜且非 TRANSIENT）直接复用，不再联网；记录原 ts 以便写回时保留
        cached_entries: dict[str, tuple[str, str, float]] = {}
        cached_res: list[tuple[str, str, str]] = []
        to_probe: list[str] = []
        for u in testable:
            c = cache.get(u)
            if (not args.refresh and c
                    and (now - c.get("ts", 0)) < ttl
                    and c.get("status") in ("LIVE", "ARCHIVE", "DEAD")):
                cached_entries[u] = (c["status"], c["detail"], c.get("ts", now))
                cached_res.append((u, c["status"], c["detail"]))
            else:
                to_probe.append(u)
        if cached_res:
            print(f"  ♻ 缓存命中 {len(cached_res)} 个 URL（跳过联网，--refresh 可强制重验）")
        if to_probe:
            print(f"  检测到网络可用，开始验活 {len(to_probe)} 个 URL（并发 {cfg.URL_WORKERS}，"
                  f"单 URL 超时 {cfg.URL_TIMEOUT}s，重试 {args.retries}）…")
            with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.URL_WORKERS) as ex:
                new_results = list(ex.map(lambda u: probe_one(u, args.retries, args.timeout), to_probe))
            # ---- 第二轮：对仍 TRANSIENT 的 URL 额外退避重试 ----
            # 沙箱网络（SSL EOF / 5xx / 超时）会瞬时抖动，同一 URL 在 LIVE/TRANSIENT 间
            # 反复横跳；单轮耗尽即判死会误杀真实可活的链接。故对 TRANSIENT 再做一轮
            # 退避重试（含短暂 sleep），显著降低环境抖动导致的误 TRANSIENT。
            trans_urls = [r[0] for r in new_results if r[1] == "TRANSIENT"]
            if trans_urls:
                print(f"  ⏳ {len(trans_urls)} 个 URL 首轮 TRANSIENT，退避后第二轮重试…")
                time.sleep(cfg.BACKOFF)
                with concurrent.futures.ThreadPoolExecutor(max_workers=cfg.URL_WORKERS) as ex:
                    retry = list(ex.map(lambda u: probe_one(u, max(args.retries, 2), args.timeout), trans_urls))
                remap = {u: (u, st, det) for u, st, det in retry}
                new_results = [remap.get(r[0], r) for r in new_results]
        else:
            new_results = []
        results = cached_res + new_results
        # 写回缓存（仅持久化确定结果，不缓存 TRANSIENT 以免误抑制重试）。
        # 关键：缓存命中项保留其「原 ts」，仅新探测结果用 now —— 否则每次复用都会把
        # TTL 续期到今天，死链可能在反复 verify 中被「永远新鲜」的缓存掩盖。
        for (u, st, det) in new_results:
            if st in ("LIVE", "ARCHIVE", "DEAD"):
                cache[u] = {"status": st, "detail": det, "ts": now}
        for u, (st, det, cts) in cached_entries.items():
            if st in ("LIVE", "ARCHIVE", "DEAD"):
                cache[u] = {"status": st, "detail": det, "ts": cts}
        save_cache(cache_path, cache)
    elif testable:
        # 离线：合并新鲜缓存中确定性结论（LIVE/ARCHIVE/DEAD），未缓存/过期项判 TRANSIENT。
        # 「能复用多少复用多少」，未缓存项单独标 TRANSIENT 并在明细中可见，
        # 让作者清楚哪些链接确实没验活。
        cached_res = [
            (u, cache[u]["status"], cache[u]["detail"])
            for u in testable
            if (c := cache.get(u)) and (now - c.get("ts", 0)) < ttl
            and c.get("status") in ("LIVE", "ARCHIVE", "DEAD")
        ]
        uncached = [
            u for u in testable
            if not ((c := cache.get(u)) and (now - c.get("ts", 0)) < ttl
                    and c.get("status") in ("LIVE", "ARCHIVE", "DEAD"))
        ]
        results = list(cached_res)
        for u in uncached:
            results.append((u, "TRANSIENT", "离线且无可复用缓存，视为未验活（须联网重验）"))
        if not uncached:
            print("  ⚠️ 网络不可达，但全部 URL 均有新鲜缓存，基于缓存结论判定。")
        elif cached_res:
            print(
                f"  ⚠️ 网络不可达，且 {len(uncached)} 个 URL 无新鲜缓存；"
                f"已复用 {len(cached_res)} 个缓存结论，未缓存项视为未验活（TRANSIENT）。"
            )
        else:
            print("  ⚠️ 网络不可达（连通性探针失败）。URL 存活检测【未执行】。")
    else:
        # testable 为空（全部 URL 因格式/截断/豁免被分流）：无需联网判定，结果留空，
        # 下方决策阶段会按 FORMAT/TRUNC/EXEMPT 处理，不会误判 exit 2。
        if not exempt:
            print("  ⚠️ 网络不可达（连通性探针失败）。所有 URL 均已因格式/截断被排除，无需联网判定。")

    # 豁免主机结果并入汇总（EXEMPT：按已验证处理，不计 DEAD、不阻断）。
    for u in exempt:
        results.append((u, "EXEMPT", "主机在验活豁免名单（内网/鉴权后可见），按已验证处理"))

    # ---- 汇总 ----
    live = [r for r in results if r[1] == "LIVE"]
    arch = [r for r in results if r[1] == "ARCHIVE"]
    dead = [r for r in results if r[1] == "DEAD"]
    trans = [r for r in results if r[1] == "TRANSIENT"]
    suspect = [r for r in results if r[1] == "SUSPECT"]
    exemp = [r for r in results if r[1] == "EXEMPT"]

    print("\n  结果明细：")
    for u in fmt_bad:
        print(f"    [FORMAT] {u}  （含中文/空格/非法字符，须改为纯 ASCII http(s) URL）")
    for u in trunc_bad:
        print(f"    [TRUNC]  {u}  （疑似被素材源截断，须换完整 LIVE 链接）")
    if results:
        for u, st, det in results:
            mark = {"LIVE": "✔", "ARCHIVE": "⚠", "DEAD": "✘",
                    "TRANSIENT": "?", "SUSPECT": "≈", "EXEMPT": "⛨"}.get(st, "?")
            where = f"  [{origin.get(u, '?')}]" if len(sources) > 1 else ""
            print(f"    [{mark} {st}] {u}  — {det}{where}")

    print("\n  汇总：")
    print(f"    URL 总数           : {len(uniq)}")
    print(f"    格式缺陷(FORMAT)   : {len(fmt_bad)}")
    print(f"    截断残破(TRUNC)    : {len(trunc_bad)}")
    if results:
        print(f"    验活通过(LIVE)     : {len(live)}")
        print(f"    存档兜底(ARCHIVE)  : {len(arch)}")
        if exemp:
            print(f"    豁免主机(EXEMPT)   : {len(exemp)}  （内网/鉴权后可见，按已验证处理）")
        print(f"    失效/虚构(DEAD)    : {len(dead)}")
        print(f"    未验活(TRANSIENT)  : {len(trans)}")
        print(f"    疑似软404(SUSPECT) : {len(suspect)}  （warning，须人工确认，不阻断）")

    # ---- 决策 ----
    if fmt_bad or trunc_bad:
        print("\n  [FAIL] 存在格式缺陷/截断 URL（FORMAT/TRUNC），必须先修正。")
        return 1
    if not results:
        print("\n  [WARN] 离线且无可复用缓存，URL 未验活（exit 2）：联网后重跑 verify 拿到 exit 0，"
              "禁止把本章当作「URL 已验证」交付。")
        return 2
    if dead:
        print("\n  [FAIL] 存在失效/虚构链接（DEAD），必须替换为真实可访问 URL 后重跑。")
        return 1
    if trans:
        print("\n  [WARN] 存在未验活链接（TRANSIENT，重试仍不通且无存档），联网后重跑。")
        return 2
    if suspect:
        # SUSPECT 为 warning 级：不阻断验活结论（exit 0），但明确提示作者人工确认，
        # 避免把「200 但实为搜索/不存在页」的地址当真活链接交付。
        print(f"\n  [WARN] {len(suspect)} 个 URL 疑似软404（内容指纹命中，须人工确认）："
              f"如确为失效链接请替换为真实 LIVE 地址；确认无误可忽略。不影响验活结论（exit 0）。")
    ok_parts = "LIVE + ARCHIVE" + (" + EXEMPT" if exemp else "")
    print("\n  [OK] 全部 URL 验活通过（" + ok_parts + "）"
          + ("（含须人工确认的 SUSPECT）" if suspect else "") + "。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
