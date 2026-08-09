# -*- coding: utf-8 -*-
"""find_urls.py - 候选可信源 URL 兜底测试。

用途
----
当 verify_urls.py 发现某 URL 不可达、需要在章节里替换时，用本脚本快速探测一批
「候选权威源」是否当前可达，挑出能用的填回章节源文件。

检查项
------
- 读取候选 URL 列表（优先读当前工作目录下的 `candidate_urls.txt`，每行一个；
  不存在则使用内置通用占位示例，请按需替换为与本主题相关的权威域名）。
- 逐个发起 HTTP 请求，输出可达状态。

路径解析规则（重要）
--------------------
候选文件按以下顺序查找，第一个存在即用：

    1. <当前工作目录>/candidate_urls.txt   ← 推荐（在章目录跑）
    2. <脚本所在目录>/candidate_urls.txt
    3. 若显式传入相对/绝对路径，则按该路径优先，找不到再回退脚本目录。

因此只需从书稿项目根目录用 skill 的实际安装路径调用（如 ``python /path/to/skill/scripts/find_urls.py``，skill 装在哪都行），也可 ``cd 第N章`` 后执行同一命令。

是否调用 / 何时调用
------------------
仅在 verify_urls.py 报告失败、且需要找替代源时手动调用，不是每章必跑。
用法：
    python find_urls.py
    python find_urls.py candidate_urls.txt

退出码：始终保持 0（探测性质，不阻断流程）。
"""
import sys
import time
import ssl
import urllib.request
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except (AttributeError, OSError):
    pass

CTX = ssl.create_default_context()
CTX.check_hostname = False
CTX.verify_mode = ssl.CERT_NONE

# 内置占位示例：请替换为与你的主题相关的权威域名（或在 candidate_urls.txt 中维护）。
BUILTIN = [
    "https://example.com/",
]

HERE = Path(__file__).parent
CWD = Path.cwd()
ARG = sys.argv[1] if len(sys.argv) > 1 else None


def resolve_candidate(arg):
    """定位候选 URL 文件：CWD 优先，脚本目录兜底。"""
    if arg:
        p = Path(arg)
        cands = [p] if p.is_absolute() else [CWD / arg, HERE / arg]
        tried = []
        for c in cands:
            tried.append(c)
            if c.exists():
                return c
        lines = "\n".join(f"    {x}" for x in dict.fromkeys(tried))
        raise SystemExit(f"[find_urls.py] 找不到候选文件: {arg}，已尝试：\n{lines}")
    # 无参数：先在 CWD 找，再回退脚本目录
    for c in (CWD / "candidate_urls.txt", HERE / "candidate_urls.txt"):
        if c.exists():
            return c
    return CWD / "candidate_urls.txt"  # 不存在则后续走 BUILTIN


candidate_file = resolve_candidate(ARG)

if candidate_file.exists():
    CANDIDATES = [
        line.strip()
        for line in candidate_file.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
else:
    CANDIDATES = BUILTIN


def probe(url: str) -> bool:
    for _ in range(2):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            resp = urllib.request.urlopen(req, context=CTX, timeout=10)
            print(f"OK {resp.status}: {url[:80]}")
            return True
        except Exception as e:  # noqa: BLE001
            if _ == 1:
                print(f"FAIL: {url[:60]} -> {str(e)[:50]}")
            else:
                time.sleep(0.5)
    return False


print(f"[find_urls.py] 探测 {len(CANDIDATES)} 个候选源")
for url in CANDIDATES:
    probe(url)
