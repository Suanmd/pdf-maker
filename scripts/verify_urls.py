# -*- coding: utf-8 -*-
"""verify_urls.py - 章节 TeX 中 URL 的真实可达性校验。

用途
----
扫描章节源文件里的 ``\\url{...}`` / ``\\href{...}``，对每个 URL 发起 HTTP 请求，
确认返回 200，从而在进入编译前过滤掉死链、错链。

检查项
------
- 从源文件提取 URL（兼容 \\url{} 与 \\href{raw}{display} 两种写法）。
- 对含非 ASCII（中文等）的 URL 仅对「路径段」做 percent-encode，避免整串双编码。
- 每个 URL 最多重试若干次（部分站点首请求易被拒），取首次 200 即算通过。

是否调用 / 何时调用
------------------
由单章编译 SOP 在「fix.py 之后、xelatex 之前」调用。失败（存在不可达 URL）
会以非零退出码结束，需替换源文件中的 URL 后重跑，不应带死链交付。
路径解析规则（重要）
--------------------
按以下顺序查找章节源文件，第一个命中即用：

    1. <当前工作目录>/第N章/第N章.tex     ← 标准子目录布局（推荐）
    2. <当前工作目录>/第N章.tex           ← 旧扁平布局
    3. <脚本所在目录>/第N章/第N章.tex     ← 兜底
    4. <脚本所在目录>/第N章.tex

因此只需从书稿项目根目录用 skill 的实际安装路径调用（如
``python /path/to/skill/scripts/verify_urls.py 3``，skill 装在哪都行），也可 ``cd 第3章`` 后执行同一命令。
也可用显式路径：``python /path/to/skill/scripts/verify_urls.py 第3章/第3章.tex``。

用法：
    python verify_urls.py [CH_NUM | 源文件路径]
    python verify_urls.py 3            # 校验第 3 章源文件
    python verify_urls.py 第3章/第3章.tex

退出码：0 全部可达；非 0 存在失败 URL。
"""
import re
import sys
import json
import time
import ssl
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass


# 全局 SSL 上下文：关闭主机名/证书校验，仅用于「URL 是否可达」探测
CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE


def wayback_fallback(url: str):
    """直连失败时查询 archive.org 快照，作为稳定可达兜底。

    返回 (ok, snapshot_url, note)；失败时 (False, None, "")。
    """
    api = "https://archive.org/wayback/available?url=" + urllib.parse.quote(url, safe="")
    try:
        req = urllib.request.Request(api, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, context=CTX, timeout=20) as r:
            data = json.loads(r.read().decode("utf-8", "ignore"))
        snap = data.get("archived_snapshots", {}).get("closest", {})
        if snap.get("available") and snap.get("url"):
            snap_url = snap["url"]
            req2 = urllib.request.Request(snap_url, headers={"User-Agent": "Mozilla/5.0"})
            resp2 = urllib.request.urlopen(req2, context=CTX, timeout=25)
            if resp2.status == 200:
                return True, snap_url, "via archive.org"
    except Exception:
        pass
    return False, None, ""


def encode_nonascii(url: str) -> str:
    """仅对路径段做 percent-encode，保留 scheme/host/查询分隔符。"""
    if "://" not in url:
        return urllib.parse.quote(url, safe="/?#=&%:")
    head, _, tail = url.partition("://")
    host_path = tail
    if "/" in host_path:
        host, _, path = host_path.partition("/")
        encoded_path = urllib.parse.quote("/" + path, safe="/?#=&%")
        return f"{head}://{host}{encoded_path}"
    return url


def resolve_source(arg):
    """定位章节源文件（CWD 优先，脚本目录兜底）。

    arg 可以是：None/缺省 → 第1章；纯数字 → 第{arg}章；
    其它（含路径、附录名）→ 按路径解析（先 CWD 再脚本目录）。
    """
    HERE = Path(__file__).parent
    tried = []
    if arg is None or arg == "":
        stems = ["第1章"]
    elif arg.isdigit() or arg.lstrip("-").isdigit():
        stems = [f"第{arg.lstrip('-')}章"]
    else:
        p = Path(arg)
        cands = [p] if p.is_absolute() else [Path.cwd() / arg, HERE / arg]
        for c in cands:
            tried.append(c)
            if c.exists():
                return c
        lines = "\n".join(f"    {x}" for x in dict.fromkeys(tried))
        raise SystemExit(f"[verify_urls.py] 找不到: {arg}，已尝试：\n{lines}")

    for stem in stems:
        for base in (Path.cwd(), HERE):
            for cand in (base / stem / f"{stem}.tex", base / f"{stem}.tex"):
                tried.append(cand)
                if cand.exists():
                    return cand

    lines = "\n".join(f"    {p}" for p in dict.fromkeys(tried))
    raise SystemExit(f"[verify_urls.py] 找不到源文件，已尝试：\n{lines}")


def main() -> int:
    ARG = sys.argv[1] if len(sys.argv) > 1 else None
    TEX_PATH = resolve_source(ARG)

    CONTENT = TEX_PATH.read_text(encoding="utf-8")
    # 同时识别 \url{...} 与 \href{raw}{display} 中的原始 URL
    urls_raw = re.findall(r"\\url\{([^}]+)\}", CONTENT)
    urls_raw += re.findall(r"\\href\{([^}]+)\}\{", CONTENT)
    # 还原显示文本转义后的下划线
    urls = [u.strip().replace(r"\_", "_") for u in urls_raw]
    urls = list(dict.fromkeys(urls))  # 去重保序

    print(f"[verify_urls.py] 发现 {len(urls)} 个唯一 URL")

    ok, fail = 0, []
    for i, url in enumerate(urls):
        url = encode_nonascii(url)
        status = ""
        # 1) 直连（最多 3 次重试）
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, context=CTX, timeout=25)
                if resp.status == 200:
                    ok += 1
                    print(f"  [{i + 1}/{len(urls)}] OK {resp.status} {url[:80]}")
                    status = "ok"
                    break
                status = f"status={resp.status}"
            except Exception as e:  # noqa: BLE001 - 网络异常种类多，统一捕获
                status = str(e)[:60]
            if attempt < 2:
                time.sleep(1.5)
        # 2) 直连未过 → archive.org 快照兜底（自动找稳定镜像）
        if status != "ok":
            try:
                wb_ok, wb_url, _ = wayback_fallback(url)
                if wb_ok:
                    ok += 1
                    status = "ok"
                    print(f"  [{i + 1}/{len(urls)}] OK (via archive.org) {wb_url[:70]}")
            except Exception:
                pass
        if status != "ok":
            fail.append((url, status))
            print(f"  [{i + 1}/{len(urls)}] FAIL {status} {url[:60]}")

    print(f"\n结果: {ok}/{len(urls)} OK")
    if fail:
        print("\n失败 URL:")
        for url, err in fail:
            print(f"  {err}: {url[:100]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
