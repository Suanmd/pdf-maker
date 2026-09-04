# -*- coding: utf-8 -*-
"""pytest 共享夹具：免安装注入 src/、隔离全局状态、书稿项目构造助手。"""

import os
import sys
from pathlib import Path

import pytest

# 免安装运行：把 src/ 注入 sys.path（pip install -e . 后亦无副作用）
ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import pdfmaker.core.config as cfg  # noqa: E402


@pytest.fixture(autouse=True)
def _isolate_state(tmp_path, monkeypatch):
    """每个测试用独立缓存/状态目录，并屏蔽外部环境变量与项目配置干扰。"""
    monkeypatch.setattr(cfg, "READER_STATE_DIR", tmp_path / "reader_state")
    monkeypatch.setattr(cfg, "VERIFY_CACHE_DIR", tmp_path / "verify_cache")
    cfg.PROJECT_CONFIG.clear()
    for k in list(os.environ):
        if k.startswith("PDFMAKER_"):
            monkeypatch.delenv(k, raising=False)
    yield


@pytest.fixture
def project(tmp_path, monkeypatch):
    """创建空书稿项目根目录并把 cwd 切进去（resolve_source 以 CWD 优先定位）。"""
    root = tmp_path / "book"
    root.mkdir()
    monkeypatch.chdir(root)
    return root


def write_chapter(root: Path, n, body: str) -> Path:
    """在 root 下落地 第N章/第N章.tex（n 也可为「附录A」），返回源文件路径。"""
    stem = n if str(n).startswith("附录") else f"第{n}章"
    d = root / stem
    d.mkdir(parents=True, exist_ok=True)
    p = d / f"{stem}.tex"
    p.write_text(body, encoding="utf-8")
    return p


# 一个完全合规的章节正文：三线表（表题在上）+ 1 条自洽引用，可直接通过 check/balance。
GOOD_CHAPTER = r"""\chapter{测试章}
\label{cha:c1}

\section{背景}
\label{sec:c1:intro}

这里是正文内容，包含若干中文字符用于字数统计与结构校验。引用文献\cite{c1r1}。

\begin{table}[htbp]
\centering
\caption{示例三线表}
\label{tab:c1:x}
\begin{tabularx}{\textwidth}{l X}
\toprule
列甲 & 列乙 \\
\midrule
甲 & 乙 \\
\bottomrule
\end{tabularx}
\end{table}

\begin{thebibliography}{99}
\bibitem{c1r1} 作者. 标题. \href{https://example.com/a}{example}
\end{thebibliography}
"""


# ---- 假编译桩（替换 core.xelatex.compile，不依赖真实 TeX） ----

def fake_compile_ok(xelatex, *args, cwd=None, quiet=False):
    """假 xelatex（单章成功）：写出干净的 _tmp.log 与假的 _tmp.pdf，返回 0。"""
    d = Path(cwd)
    (d / "_tmp.log").write_text("This is XeTeX\n", encoding="utf-8")
    (d / "_tmp.pdf").write_bytes(b"%PDF-1.5 fake")
    return 0


def fake_compile_fail(xelatex, *args, cwd=None, quiet=False):
    """假 xelatex（失败）：不产生任何产物，直接返回 1。"""
    return 1


def fake_build_compile_ok(xelatex, *args, cwd=None, quiet=False):
    """假 xelatex（整书合并成功）：写出干净的 main.log 与假的 main.pdf，返回 0。"""
    d = Path(cwd)
    (d / "main.log").write_text("This is XeTeX\nOutput written on main.pdf (3 pages).\n",
                                encoding="utf-8")
    (d / "main.pdf").write_bytes(b"%PDF-1.5 fake")
    return 0
