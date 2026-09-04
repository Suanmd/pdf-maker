# -*- coding: utf-8 -*-
"""core.config —— 集中配置：所有可调常量的唯一真源。

设计原则
--------
- 所有可调项给出合理默认值，任何值都可通过环境变量（前缀 ``PDFMAKER_``）或
  项目级 ``.pdfmaker.toml`` 覆盖，便于 CI / 受限网络环境调参。
- 优先级：环境变量 > .pdfmaker.toml > 代码默认值。
- 纯标准库，零依赖。各命令以 ``import pdfmaker.core.config as cfg`` 并引用
  ``cfg.X`` 的方式**动态访问**（而非 ``from ... import X``），保证运行时
  toml / 环境变量覆盖真正生效。

把常量从命令模块里抽出来，是为了消解「缺乏配置抽象」：过去同一类参数
（超时、并发、重试、阈值、分块大小）散落在 verify / balance / reader 三处，
改一处易漏另一处。集中后，默认值只此一份，覆盖口径也只此一份。
"""

import os
import sys
from pathlib import Path


def _env_float(name: str, default: float) -> float:
    """读取浮点型环境变量；缺失或无法解析时返回默认值。"""
    try:
        return float(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_int(name: str, default: int) -> int:
    """读取整型环境变量；缺失或无法解析时返回默认值。"""
    try:
        return int(os.environ.get(name, default))
    except (TypeError, ValueError):
        return default


def _env_list(name: str, default: list[str]) -> list[str]:
    """读取逗号分隔的列表型环境变量；缺失或为空时返回默认值副本。"""
    val = os.environ.get(name)
    if not val:
        return list(default)
    return [u.strip() for u in val.split(",") if u.strip()]


# ---- verify：网络验活参数 ----
URL_TIMEOUT = _env_float("PDFMAKER_URL_TIMEOUT", 30.0)     # 单 URL 超时（秒）
URL_WORKERS = _env_int("PDFMAKER_URL_WORKERS", 8)          # 并发线程数
PROBE_TIMEOUT = _env_float("PDFMAKER_PROBE_TIMEOUT", 6.0)  # 连通性探针超时（秒）
MAX_RETRIES = _env_int("PDFMAKER_URL_RETRIES", 3)          # 单 URL 重试次数
BACKOFF = _env_float("PDFMAKER_BACKOFF", 2.0)              # 重试退避基数（秒）
USER_AGENT = os.environ.get(
    "PDFMAKER_USER_AGENT", "Mozilla/5.0 (pdf-maker verify) compatible"
)
PROBE_HOSTS = _env_list(
    "PDFMAKER_PROBE_HOSTS",
    ["https://example.com", "https://archive.org", "https://www.w3.org"],
)

# ---- verify：HTTP 状态码分类 ----
HARD_DEAD = frozenset({404, 410})                # 页面明确不存在，必须替换
SOFT_BLOCKED = frozenset({401, 403, 429})        # 鉴权/反爬/限流：地址有效但访问受限 → 仍算 LIVE
# 请求方式/细节被服务端拒绝（400/405/406/407）：服务端已响应、主机在线、地址有效，
# 仅是我们的探测请求方式（GET/Range）不符合其要求，绝不因此误判死链。
METHOD_REJECTED = frozenset({400, 405, 406, 407})
SERVER_ERROR = frozenset({500, 502, 503, 504, 408, 425})  # 服务端瞬时错误/超时 → 按瞬断重试

# ---- balance：均衡阈值（建议级，不阻断） ----
MIN_CHARS = 300      # 单个 section/subsection 的非空可见字符建议下限
MIN_TABLES = 2       # 每章表格数建议下限
MIN_IMAGES = 1       # 每章配图数建议下限
# 参考文献建议下限：默认 0 = 不设下限，按需引用。
# 哲学：引用是论证的需要而非章节配额；资料/代码无外部文献时完全不写，
# 严禁为凑数而造引用（零引用章是合法形态）。学术报告等确需指标考核时，
# 可经 PDFMAKER_MIN_REFS 或 .pdfmaker.toml 设为目标值（如 6）。
MIN_REFS = _env_int("PDFMAKER_MIN_REFS", 0)

# ---- check：整章字数门禁阈值（默认告警级；check --strict 才阻断） ----
# 与 MIN_CHARS 区分：MIN_CHARS 是「单个 section 可见字符」建议下限（balance 用），
# 本项是「整章正文」字数的硬门禁下限（check 用）。
CHAPTER_MIN_CHARS = _env_int("PDFMAKER_CHAPTER_MIN_CHARS", 2000)
# 字数上限：0 表示不限制（延续「引用/字数不设上限」的宽松哲学，也避免误伤
# 技术章天然超长的可见字符数）。
CHAPTER_MAX_CHARS = _env_int("PDFMAKER_CHAPTER_MAX_CHARS", 0)

# ---- check：整章字数计数口径 ----
# "cjk"    ：仅数中文（历史默认，忠实「中文字数」语义，但技术章被英文/公式低估）；
# "visible"：数非空可见字符（CJK+拉丁+数字+标点，与小节 char_count 口径一致），
#            技术书中英文混排更公平，避免「内容充实却因英文多被判过短」。
CHAPTER_COUNT_MODE = os.environ.get("PDFMAKER_CHAPTER_COUNT_MODE", "cjk")

# ---- check/lint：\texttt 不可断行长串（Overfull \hbox 风险）预警阈值 ----
# 等宽字体（Latin Modern Mono）禁用断词，且 / . _ : 等符号在文本模式不构成断点；
# 超过该长度（字形数）的 \texttt 长串落在行尾附近即可能 Overfull。默认 25 ≈
# 正文行宽（约 455pt）1/3 对应的等宽字形数（约 5.25pt/字形）。0 = 关闭该预检。
LONGRUN_WARN_CHARS = _env_int("PDFMAKER_LONGRUN_WARN_CHARS", 25)

# ---- fix/build：\texttt 长串自动拆词（源头治理，normalize_text 第四步） ----
# 预警（scan_unbreakable_runs）只「告知」，本项在规范化阶段直接「修复」：对字形数
# ≥ 阈值的 \texttt 内容，在 _ / . 分隔符后自动插入 \allowbreak{}（只允许断行、不改变
# 渲染结果，语义零风险）。默认 20 字形：一行约 86 个等宽字形，≥20 的长串落在行尾
# 即可能溢出；表格 p{宽} 列内更窄，宁早勿晚。0 = 关闭自动拆词（回归纯手工）。
TEXTTT_RELAX_CHARS = _env_int("PDFMAKER_TEXTTT_RELAX_CHARS", 20)

# ---- check/lint：tabularx 非 X 列「单列挤压」预警阈值 ----
# 列格式中的 l/c/r 列不会换行：若其单元格内含超过阈值的不可断长串（典型为长
# \texttt 标识符），该列会被撑宽、挤压 X 列（真实事故：首列 30+ 字形标识符把
# X 列挤成窄条）。命中即 warning（不阻断），建议改用 >{\raggedright\arraybackslash}p{宽}
# 列或给长串加 \allowbreak。0 = 关闭该预检。
TABLE_SQUEEZE_WARN_CHARS = _env_int("PDFMAKER_TABLE_SQUEEZE_WARN_CHARS", 20)

# ---- cleanup：_tmp_old/ 归档份数上限 ----
# 每次 SOP 运行会把中间产物归档进 _tmp_old/，长期累积成磁盘垃圾。保留每个被归档
# 基线名（_tmp / chN / ...）最近 N 份，超出删除最旧者。0 表示不清理（保留全部）。
TMP_OLD_KEEP = _env_int("PDFMAKER_TMP_OLD_KEEP", 10)

# ---- reader：素材强制阅读分块参数 ----
CHUNK_SIZE_CN = 200              # 中文素材单 chunk 行数
CHUNK_SIZE_EN = 320              # 英文素材单 chunk 行数
MAX_BYTES_PER_READ = 30000       # 英文素材单 read 字节上限


def _default_cache_root() -> Path:
    """平台默认缓存根目录：macOS 遵循 ~/Library/Caches/<app>，其余遵循 XDG ~/.cache/<app>。"""
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Caches" / "pdfmaker"
    return Path.home() / ".cache" / "pdfmaker"


# ---- reader：阅读状态存放位置（收口到全局缓存目录，避免污染书稿项目） ----
READER_STATE_DIR = Path(
    os.environ.get(
        "PDFMAKER_READER_STATE_DIR",
        str(_default_cache_root() / "reader"),
    )
)

# ---- verify：URL 验活结果缓存（避免重复联网、支持离线复用上次已知结果） ----
VERIFY_CACHE_TTL_DAYS = _env_int("PDFMAKER_VERIFY_CACHE_TTL_DAYS", 7)  # 缓存新鲜度（天）
VERIFY_CACHE_DIR = Path(
    os.environ.get(
        "PDFMAKER_VERIFY_CACHE_DIR",
        str(_default_cache_root()),
    )
)
VERIFY_CACHE_FILE = "verify_cache.json"

# ---- verify：验活豁免主机名单（内网 / 鉴权后可见的合法链接） ----
# 企业内网、SSO 鉴权后可见的 URL 对 verify 的匿名探测必然 401/403 或超时，
# 但它们是作者真实可访问的合法引用——旧行为下只能全书不放链接来回避。
# 列入名单的主机（精确匹配或子域名后缀匹配）跳过联网探测，标记 EXEMPT
# （按已验证处理、不计 DEAD、不阻断；仍要求格式合法且不截断）。
VERIFY_ALLOW_HOSTS = _env_list("PDFMAKER_VERIFY_ALLOW_HOSTS", [])

# ---- xelatex：可执行文件路径与单次编译超时 ----
XELATEX_BIN = os.environ.get("PDFMAKER_XELATEX")  # None 表示交由 find_xelatex() 运行时探测
XELATEX_TIMEOUT = _env_float("PDFMAKER_XELATEX_TIMEOUT", 300.0)

# ---- 扫描看门狗：check / balance / xref / fix 等纯 Python 扫描步骤的墙钟时限 ----
# 实测全部扫描器在 100KB 病态输入上也不到 4ms，30s 约有万倍余量；
# 要防的失效模式是正则歧义分支的 2^N 指数回溯（实质等于永久挂死），
# 超时即阻断（exit 1），避免「挂死被误判为步骤有点慢」。
SCAN_TIMEOUT = _env_float("PDFMAKER_SCAN_TIMEOUT", 30.0)

# ---- track：引用质量审计启发式（默认已含主流学术域） ----
WIKI_HINTS = ["wikipedia.org", "wiki"]
AUTHORITY_HINTS = [
    "dx.doi.org", "doi.org", "arxiv.org", "plato.stanford.edu",
    "nature.com", "science.org", "onlinelibrary.wiley.com",
    "springer.com", "link.springer.com", "springeropen.com",
    "frontiersin.org", "ieee.org", "mdpi.com", "acm.org",
]

# ---- 项目级配置（.pdfmaker.toml） ----
# TOML 解析用标准库 tomllib（Python 3.11+）；若 tomllib 不可用（极旧运行时），
# 项目级配置静默降级为「仅环境变量 + 默认值」。
PROJECT_CONFIG: dict = {}

# 覆盖映射表：(toml 键, 环境变量名, 模块全局名[, 类型转换])
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
    ("scan_timeout", "PDFMAKER_SCAN_TIMEOUT", "SCAN_TIMEOUT", float),
    ("longrun_warn_chars", "PDFMAKER_LONGRUN_WARN_CHARS", "LONGRUN_WARN_CHARS", int),
    ("texttt_relax_chars", "PDFMAKER_TEXTTT_RELAX_CHARS", "TEXTTT_RELAX_CHARS", int),
    ("table_squeeze_warn_chars", "PDFMAKER_TABLE_SQUEEZE_WARN_CHARS", "TABLE_SQUEEZE_WARN_CHARS", int),
]
_OVERRIDE_LISTS = [
    ("probe_hosts", "PDFMAKER_PROBE_HOSTS", "PROBE_HOSTS"),
    ("authority_hints", "PDFMAKER_AUTHORITY_HINTS", "AUTHORITY_HINTS"),
    ("verify_allow_hosts", "PDFMAKER_VERIFY_ALLOW_HOSTS", "VERIFY_ALLOW_HOSTS"),
]
_OVERRIDE_PATHS = [
    ("reader_state_dir", "PDFMAKER_READER_STATE_DIR", "READER_STATE_DIR"),
    ("verify_cache_dir", "PDFMAKER_VERIFY_CACHE_DIR", "VERIFY_CACHE_DIR"),
]
_OVERRIDE_STRINGS = [
    ("chapter_count_mode", "PDFMAKER_CHAPTER_COUNT_MODE", "CHAPTER_COUNT_MODE"),
]


def _toml_load(path: Path) -> dict:
    """解析 .pdfmaker.toml；支持 [pdfmaker] 段，也兼容平铺键。tomllib 缺失或解析失败时返回 {}。"""
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


def load_project_config(start: str | Path | None = None) -> Path | None:
    """从 start（默认 CWD）向上回溯查找 .pdfmaker.toml，解析为 PROJECT_CONFIG。

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
                # expanduser：toml 里常写 ~/...，不展开会落成相对路径的字面 "~" 目录
                g[gname] = Path(PROJECT_CONFIG[toml_key]).expanduser()
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
        print(
            f"[config] 注意：.pdfmaker.toml 含无法解析的键（已忽略）：{', '.join(ignored)}",
            file=sys.stderr,
        )
