# -*- coding: utf-8 -*-
"""文本统计：去掉表格/图/verbatim 逐字块后统计正文字数。"""

import re

# 统计正文字数时要剔除的块：表格 / 图 / verbatim / \\verb 逐字
_BLOCK_RE = re.compile(
    r"\\begin\{table\}.*?\\end\{table\}"
    r"|\\begin\{tikzpicture\}.*?\\end\{tikzpicture\}"
    r"|\\begin\{verbatim\}.*?\\end\{verbatim\}"
    r"|\\begin\{codeblock\}.*?\\end\{codeblock\}"
    r"|\\verb([^a-zA-Z]).*?\1",
    flags=re.DOTALL,
)

# LaTeX 注释：从 %（非转义 \%）到行尾。统计前剥离，避免注释里的 \\bibitem /
# \\begin{table} 等字样被误计（曾导致 check 把文件头注释里的「\\bibitem」也算进计数）。
_COMMENT_RE = re.compile(r"(?<!\\)%(.*)$", re.MULTILINE)


def strip_latex_comments(text: str) -> str:
    """移除 LaTeX 行注释（``\\%`` 转义的百分号保留）。

    用于结构性统计（\\bibitem / \\begin{table} 等）前剔除被注释掉的源码，
    防止注释行里的命令字样被当成真实命令计数。
    """
    return _COMMENT_RE.sub("", text)


def strip_blocks(text: str) -> str:
    """去掉表格 / 图 / verbatim / \\verb 逐字块，避免它们的内容混入正文字数。"""
    return _BLOCK_RE.sub("", text)


def chinese_count(text: str) -> int:
    """统计中文字符数（用于内容密度 / 小节字数评估）。"""
    return len(re.findall(r"[一-鿿]", text))


def char_count(text: str) -> int:
    """统计非空可见字符数（CJK + 拉丁字母 + 数字 + 标点，去空白）。

    用于小节字数下限判定——相比仅数中文，能正确评估「中英文混排 + 少量公式」
    的小节，避免「内容很充实却因英文多被判过短」的误报。
    """
    return len(re.sub(r"\s", "", text))


# 非正文环境（不计入整章字数门禁）：图像 / 代码 / 参考文献。
# 关键区别：表格（tabular / tabularx / longtable / array）**不**在此列——其单元格
# 文字是作者真实撰写的章节内容（对比表 / 里程碑表 / 风险登记表等）。原 ``strip_blocks``
# 会连表格整段剔除，导致「软章」（路线图 / 展望类）正文偏短、被迫凑字）。
# figure / tikzpicture 是图像、verbatim / codeblock / lstlisting 是代码、thebibliography
# 是参考文献，均不计入「正文字数」。
_NONBODY_ENV_RE = re.compile(
    r"\\begin\{(figure|tikzpicture|verbatim|codeblock|lstlisting|thebibliography)(\*?)\}"
    r".*?\\end\{\1\2\}",
    flags=re.DOTALL,
)
_INLINE_VERB_RE = re.compile(r"\\verb([^a-zA-Z]).*?\1", flags=re.DOTALL)


def strip_nonbody(text: str) -> str:
    """去掉「非正文」环境（图 / 代码 / 参考文献），但**保留表格单元格文字**。

    供整章字数门禁的可见字符统计使用，区别于 ``strip_blocks``（连表格一起剔除）。
    """
    t = strip_latex_comments(text)
    t = _NONBODY_ENV_RE.sub("", t)
    t = _INLINE_VERB_RE.sub("", t)
    return t


def count_visible_body(text: str) -> int:
    """整章正文字数（非空可见字符），**保留表格单元格文字**（见 ``strip_nonbody``）。

    用于整章字数硬门禁（check 命令）。相比旧实现（``char_count(strip_blocks(...))``
    连表格一起剔除），本函数把表格单元格文字计入，使「软章」不再被迫凑字。
    """
    return char_count(strip_nonbody(text))
