# -*- coding: utf-8 -*-
"""集中配置：把散落在各命令里的「魔法常量」收口到一处，统一环境变量覆盖入口。

设计原则
--------
- 所有可调项给出合理默认值，**与旧实现逐一对齐**，保证重构前后行为完全一致。
- 任何值都可通过环境变量覆盖（前缀 ``PDFMAKER_``），便于 CI / 受限网络环境调参。
- 纯标准库，零依赖；被 ``commands/*`` 以 ``import pdfmaker.core.config as cfg``
  并引用 ``cfg.X`` 复用（动态访问，保证运行时 toml / 环境变量覆盖生效）。

把常量从命令模块里抽出来，是为了消解「缺乏配置抽象」：过去同一类参数
（超时、并发、重试、阈值、分块大小）散落在 verify / balance / reader 三处，
改一处易漏另一处。集中后，默认值只此一份，覆盖口径也只此一份。
"""

import os
import sys
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    val = os.environ.get(name)
    if not val:
        return list(default)
    return [u.strip() for u in val.split(",") if u.strip()]


# ---- verify：网络验活参数 ----
URL_TIMEOUT = _env_float("PDFMAKER_URL_TIMEOUT", 30.0)      # 单 URL 超时（秒）
URL_WORKERS = _env_int("PDFMAKER_URL_WORKERS", 8)           # 并发线程数
PROBE_TIMEOUT = _env_float("PDFMAKER_PROBE_TIMEOUT", 6.0)   # 连通性探针超时
MAX_RETRIES = _env_int("PDFMAKER_URL_RETRIES", 3)            # 单 URL 重试次数
BACKOFF = _env_float("PDFMAKER_BACKOFF", 2.0)                # 退避基数（秒）
USER_AGENT = os.environ.get(
    "PDFMAKER_USER_AGENT", "Mozilla/5.0 (pdf-maker verify) compatible"
)
PROBE_HOSTS = _env_list(
    "PDFMAKER_PROBE_HOSTS",
    ["https://example.com", "https://archive.org", "https://www.w3.org"],
)

# ---- verify：HTTP 状态码分类 ----
HARD_DEAD = frozenset({404, 410})                 # 页面明确不存在，必须替换
SOFT_BLOCKED = frozenset({401, 403, 429})         # 鉴权/反爬/限流：地址有效但访问受限 → 仍算 LIVE
# 请求方式/细节被服务端拒绝（400/405/406/407）：服务端已响应、主机在线、地址有效，
# 仅是我们的探测请求方式（GET/Range）不符合其要求，绝不因此误判死链。
METHOD_REJECTED = frozenset({400, 405, 406, 407})
SERVER_ERROR = frozenset({500, 502, 503, 504, 408, 425})  # 服务端瞬时错误/超时 → 按瞬断重试

# ---- balance：均衡阈值（建议级，不阻断） ----
MIN_CHARS = 300      # 单个 subsection 的非空可见字符下限
MIN_TABLES = 4       # 表格数建议下限
MIN_IMAGES = 1       # 配图数建议下限（每章至少 1 张）
# 每章参考文献数量下限（建议级告警，不阻断）。
# 注意：**仅下限、无上限**——本工具要求每章至少 6 条 LIVE 引用，但引用数量不设上限
# （用户明确移除所有关于引用/LIVE 引用的上限设置）。代码层面不存在任何 max_refs 常量。
MIN_REFS = _env_int("PDFMAKER_MIN_REFS", 6)  # 每章参考文献数下限（无上限）

# ---- check：整章字数硬门禁（可阻断，exit 1） ----
# 注意与 MIN_CHARS 区分：MIN_CHARS 是「单个 subsection 可见字符」建议下限（balance 用），
# 本项是「整章正文」字数的硬门禁下限（check 用）。项目若要求如 4000 字/章，
# 设环境变量 PDFMAKER_CHAPTER_MIN_CHARS=4000 即可，无需改代码。
CHAPTER_MIN_CHARS = _env_int("PDFMAKER_CHAPTER_MIN_CHARS", 2000)  # 整章正文字数下限
# 字数上限（可阻断，exit 1）：0 表示「不限制」（延续「引用/字数不设上限」的宽松哲学，
# 也避免误伤技术章天然超长的可见字符数）。项目若要求上限（如 6000 中文字对应的可见上限），
# 设 PDFMAKER_CHAPTER_MAX_CHARS 或 .pdfmaker.toml 的 chapter_max_chars 即可。
CHAPTER_MAX_CHARS = _env_int("PDFMAKER_CHAPTER_MAX_CHARS", 0)  # 整章正文字数上限（0=不限）

# ---- cleanup：_tmp_old/ 归档份数上限 ----
# 每次 SOP 运行会把中间产物归档进 _tmp_old/，长期累积成磁盘垃圾。保留每个被归档
# 基线名（_tmp / chN / ...）最近 N 份，超出删除最旧者。0 表示不清理（保留全部）。
TMP_OLD_KEEP = _env_int("PDFMAKER_TMP_OLD_KEEP", 10)

# ---- check：整章字数计数口径 ----
# "cjk"    ：仅数中文（历史默认，忠实「中文字数」语义，但技术章被英文/公式低估）；
# "visible"：数非空可见字符（CJK+拉丁+数字+标点，与小节 char_count 一致），
#            技术书中英文混排更公平，避免「内容充实却因英文多被判过短」。
# 项目可经 .pdfmaker.toml 的 chapter_count_mode 或环境变量 PDFMAKER_CHAPTER_COUNT_MODE 切换。
CHAPTER_COUNT_MODE = os.environ.get("PDFMAKER_CHAPTER_COUNT_MODE", "cjk")

# ---- reader：素材强制阅读分块参数 ----
CHUNK_SIZE_CN = 200              # 中文素材单 chunk 行数
CHUNK_SIZE_EN = 320              # 英文素材单 chunk 行数
MAX_BYTES_PER_READ = 30000       # 英文素材单 read 字节上限

# ---- reader：阅读状态存放位置（移出内容目录，避免污染书稿项目） ----
# 旧版把 .reader-state-*.json 点文件散落在素材同目录（内容目录）；现统一收口到
# 全局缓存目录，可用 PDFMAKER_READER_STATE_DIR 覆盖（如团队共享缓存）。
READER_STATE_DIR = Path(
    os.environ.get(
        "PDFMAKER_READER_STATE_DIR",
        str(Path.home() / ".cache" / "pdfmaker" / "reader"),
    )
)

# ---- verify：URL 验活结果缓存（避免重复联网、支持离线复用上次已知结果） ----
VERIFY_CACHE_TTL_DAYS = _env_int("PDFMAKER_VERIFY_CACHE_TTL_DAYS", 7)  # 缓存新鲜度（天）
VERIFY_CACHE_DIR = Path(
    os.environ.get(
        "PDFMAKER_VERIFY_CACHE_DIR",
        str(Path.home() / ".cache" / "pdfmaker"),
    )
)
VERIFY_CACHE_FILE = "verify_cache.json"

# ---- xelatex 路径（build / chapter 编排用；环境变量 / toml 可覆盖，否则运行时探测） ----
XELATEX_BIN = os.environ.get("PDFMAKER_XELATEX")  # None 表示交由 find_xelatex() 探测

# ---- xelatex 单次编译超时 ----
# 默认 300s；可被 .pdfmaker.toml 的 xelatex_timeout 或环境变量 PDFMAKER_XELATEX_TIMEOUT 覆盖。
XELATEX_TIMEOUT = _env_float("PDFMAKER_XELATEX_TIMEOUT", 300.0)

# ---- track：引用质量审计启发式（可经 toml / 环境变量覆盖，默认已含主流学术域） ----
WIKI_HINTS = ["wikipedia.org", "wiki"]
AUTHORITY_HINTS = [
    "dx.doi.org", "doi.org", "arxiv.org", "plato.stanford.edu",
    "nature.com", "science.org", "onlinelibrary.wiley.com",
    "springer.com", "link.springer.com", "springeropen.com",
    "frontiersin.org", "ieee.org", "mdpi.com", "acm.org",
]

# ---- 项目级配置（.pdfmaker.toml，可选；环境变量优先级高于 toml，高于默认值） ----
# 设计：包本身零依赖；TOML 解析用标准库 tomllib（Python 3.11+，当前运行环境均满足）。
# 若 tomllib 不可用（极旧运行时），项目级配置静默降级为「仅环境变量 + 默认值」。
PROJECT_CONFIG: dict = {}

# (toml 键, 环境变量名, 模块全局名, 类型转换)
_OVERRIDE_SCALARS = [
    ("chapter_min_chars", "PDFMAKER_CHAPTER_MIN_CHARS", "CHAPTER_MIN_CHARS", int),
    ("chapter_max_chars", "PDFMAKER_CHAPTER_MAX_CHARS", "CHAPTER_MAX_CHARS", int),
    ("tmp_old_keep", "PDFMAKER_TMP_OLD_KEEP", "TMP_OLD_KEEP", int),
    ("min_chars", "PDFMAKER_MIN_CHARS", "MIN_CHARS", int),
    ("min_tables", "PDFMAKER_MIN_TABLES", "MIN_TABLES", int),
    ("min_images", "PDFMAKER_MIN_IMAGES", "MIN_IMAGES", int),
    ("min_refs", "PDFMAKER_MIN_REFS", "MIN_REFS", int),
    ("url_timeout", "PDFMAKER_URL_TIMEOUT", "URL_TIMEOUT", float),
    ("url_workers", "PDFMAKER_URL_WORKERS", "URL_WORKERS", int),
    ("probe_timeout", "PDFMAKER_PROBE_TIMEOUT", "PROBE_TIMEOUT", float),
    ("url_retries", "PDFMAKER_URL_RETRIES", "MAX_RETRIES", int),
    ("backoff", "PDFMAKER_BACKOFF", "BACKOFF", float),
    ("user_agent", "PDFMAKER_USER_AGENT", "USER_AGENT", str),
    ("verify_cache_ttl_days", "PDFMAKER_VERIFY_CACHE_TTL_DAYS", "VERIFY_CACHE_TTL_DAYS", int),
    ("chunk_size_cn", "PDFMAKER_CHUNK_SIZE_CN", "CHUNK_SIZE_CN", int),
    ("chunk_size_en", "PDFMAKER_CHUNK_SIZE_EN", "CHUNK_SIZE_EN", int),
    ("max_bytes_per_read", "PDFMAKER_MAX_BYTES_PER_READ", "MAX_BYTES_PER_READ", int),
    ("xelatex", "PDFMAKER_XELATEX", "XELATEX_BIN", str),
    ("xelatex_timeout", "PDFMAKER_XELATEX_TIMEOUT", "XELATEX_TIMEOUT", float),
]
_OVERRIDE_LISTS = [
    ("probe_hosts", "PDFMAKER_PROBE_HOSTS", "PROBE_HOSTS"),
    ("authority_hints", "PDFMAKER_AUTHORITY_HINTS", "AUTHORITY_HINTS"),
]
_OVERRIDE_PATHS = [
    ("reader_state_dir", "PDFMAKER_READER_STATE_DIR", "READER_STATE_DIR"),
    ("verify_cache_dir", "PDFMAKER_VERIFY_CACHE_DIR", "VERIFY_CACHE_DIR"),
]
_OVERRIDE_STRINGS = [
    ("chapter_count_mode", "PDFMAKER_CHAPTER_COUNT_MODE", "CHAPTER_COUNT_MODE"),
]


def _toml_load(path: "Path") -> dict:
    """解析 .pdfmaker.toml；支持 [pdfmaker] 段，也兼容平铺键。tomllib 缺失时返回 {}。"""
    try:
        import tomllib
    except ImportError:
        return {}
    try:
        with open(path, "rb") as f:
            data = tomllib.load(f)
    except Exception:
        return {}
    return dict(data.get("pdfmaker", data))


def load_project_config(start: "str | Path | None" = None) -> "Path | None":
    """向上回溯查找项目根目录的 .pdfmaker.toml，解析为 PROJECT_CONFIG。

    返回找到的配置文件路径；未找到返回 None（此时仅用环境变量 + 默认值）。
    调用方应随后调用 ``apply_project_config()`` 合并到模块全局常量。
    """
    base = Path(start) if start else Path.cwd()
    for d in [base, *base.parents]:
        cand = d / ".pdfmaker.toml"
        if cand.is_file():
            PROJECT_CONFIG.clear()
            PROJECT_CONFIG.update(_toml_load(cand))
            return cand
    PROJECT_CONFIG.clear()
    return None


def apply_project_config() -> None:
    """把 PROJECT_CONFIG 合并进模块全局常量（优先级：环境变量 > toml > 默认值）。

    在每次子命令启动早期调用一次即可；命令通过 ``import pdfmaker.core.config as cfg``
    并引用 ``cfg.X``，即可在运行时看到合并后的值。环境变量若已设置则跳过对应键，
    保证环境变量始终最高优先。
    """
    g = globals()
    applied: list[str] = []
    ignored: list[str] = []
    for toml_key, env_var, gname, caster in _OVERRIDE_SCALARS:
        if os.environ.get(env_var) is not None:
            continue  # 环境变量优先级最高，跳过
        if toml_key in PROJECT_CONFIG:
            try:
                g[gname] = caster(PROJECT_CONFIG[toml_key])
                applied.append(f"{toml_key}={g[gname]!r}")
            except (TypeError, ValueError):
                ignored.append(toml_key)
    for toml_key, env_var, gname in _OVERRIDE_LISTS:
        if os.environ.get(env_var) is not None:
            continue
        if toml_key in PROJECT_CONFIG:
            v = PROJECT_CONFIG[toml_key]
            if isinstance(v, str):
                v = [s.strip() for s in v.split(",") if s.strip()]
            if isinstance(v, (list, tuple)):
                g[gname] = list(v)
                applied.append(f"{toml_key}={g[gname]!r}")
    for toml_key, env_var, gname in _OVERRIDE_PATHS:
        if os.environ.get(env_var) is not None:
            continue
        if toml_key in PROJECT_CONFIG:
            try:
                g[gname] = Path(PROJECT_CONFIG[toml_key])
                applied.append(f"{toml_key}={g[gname]!r}")
            except Exception:
                ignored.append(toml_key)
    for toml_key, env_var, gname in _OVERRIDE_STRINGS:
        if os.environ.get(env_var) is not None:
            continue
        if toml_key in PROJECT_CONFIG:
            v = PROJECT_CONFIG[toml_key]
            if isinstance(v, str):
                g[gname] = v
                applied.append(f"{toml_key}={v!r}")
    if applied:
        print(f"[config] 已应用项目配置覆盖：{'; '.join(applied)}", file=sys.stderr)
    if ignored:
        print(f"[config] 注意：.pdfmaker.toml 含无法解析的键（已忽略）：{', '.join(ignored)}",
              file=sys.stderr)
