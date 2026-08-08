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
用法：
    python verify_urls.py [CH_NUM | 源文件路径]
    python verify_urls.py 3            # 校验 ./第3章.tex
    python verify_urls.py 第3章/第3章.tex

退出码：0 全部可达；非 0 存在失败 URL。
"""
import re
import sys
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


def main() -> int:
    HERE = Path(__file__).parent
    ARG = sys.argv[1] if len(sys.argv) > 1 else None

    if ARG and (ARG.isdigit() or ARG.lstrip("-").isdigit()):
        TEX_PATH = HERE / f"第{ARG}章.tex"
    elif ARG:
        TEX_PATH = Path(ARG)
    else:
        TEX_PATH = HERE / "第1章.tex"

    if not TEX_PATH.exists():
        raise SystemExit(f"[verify_urls.py] 找不到: {TEX_PATH}")

    CONTENT = TEX_PATH.read_text(encoding="utf-8")
    # 同时识别 \url{...} 与 \href{raw}{display} 中的原始 URL
    urls_raw = re.findall(r"\\url\{([^}]+)\}", CONTENT)
    urls_raw += re.findall(r"\\href\{([^}]+)\}\{", CONTENT)
    # 还原显示文本转义后的下划线
    urls = [u.strip().replace(r"\_", "_") for u in urls_raw]
    urls = list(dict.fromkeys(urls))  # 去重保序

    print(f"[verify_urls.py] 发现 {len(urls)} 个唯一 URL")

    CTX = ssl.create_default_context()
    CTX.check_hostname = False
    CTX.verify_mode = ssl.CERT_NONE

    ok, fail = 0, []
    for i, url in enumerate(urls):
        url = encode_nonascii(url)
        for attempt in range(3):
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                resp = urllib.request.urlopen(req, context=CTX, timeout=25)
                if resp.status == 200:
                    ok += 1
                    print(f"  [{i + 1}/{len(urls)}] OK {resp.status} {url[:80]}")
                    break
                if attempt == 1:
                    fail.append((url, f"status={resp.status}"))
                    print(f"  [{i + 1}/{len(urls)}] FAIL {resp.status} {url[:60]}")
            except Exception as e:  # noqa: BLE001 - 网络异常种类多，统一捕获
                if attempt == 1:
                    fail.append((url, str(e)[:60]))
                    print(f"  [{i + 1}/{len(urls)}] ERR {str(e)[:50]} {url[:60]}")
                time.sleep(1.5)

    print(f"\n结果: {ok}/{len(urls)} OK")
    if fail:
        print("\n失败 URL:")
        for url, err in fail:
            print(f"  {err}: {url[:100]}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
