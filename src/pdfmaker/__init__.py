# -*- coding: utf-8 -*-
"""pdfmaker —— 中文 LaTeX 报告工程化工具。

把「写一份排版合规的中文 PDF 报告 / 书」这件容易翻车的事，固化成一条受控流水线：
**单章独立编译 → 整书合并**，并在每个关键节点设置质量关卡
（素材强制阅读、URL 联网验活、编译日志体检、跨章标签去重）。

本包仅依赖 Python 标准库与系统 TeX 工具链（xelatex / ctexrep / xeCJK），
无需安装任何 PyPI 包。
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pdf-maker")
except PackageNotFoundError:
    __version__ = "2.0.0"

__all__ = ["__version__"]
