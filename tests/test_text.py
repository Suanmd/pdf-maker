# -*- coding: utf-8 -*-
"""core.text：注释剥离、块剔除、字数统计口径。"""

from pdfmaker.core.text import (
    char_count,
    chinese_count,
    count_visible_body,
    strip_blocks,
    strip_latex_comments,
    strip_nonbody,
)


class TestStripLatexComments:
    def test_strips_comment(self):
        assert strip_latex_comments("正文 % 注释\n下一行") == "正文 \n下一行"

    def test_keeps_escaped_percent(self):
        s = r"占比 50\% 左右"
        assert strip_latex_comments(s) == s

    def test_commented_commands_removed(self):
        s = "% \\bibitem{x}\n正文"
        assert "bibitem" not in strip_latex_comments(s)


class TestStripBlocks:
    def test_removes_table_figure_verbatim_codeblock(self):
        s = ("前文\\begin{table}表内容\\end{table}中段"
             "\\begin{tikzpicture}图内容\\end{tikzpicture}"
             "\\begin{verbatim}代码\\end{verbatim}"
             "\\begin{codeblock}代码2\\end{codeblock}后文")
        out = strip_blocks(s)
        assert "表内容" not in out and "图内容" not in out
        assert "代码" not in out and "代码2" not in out
        assert "前文" in out and "中段" in out and "后文" in out

    def test_removes_inline_verb(self):
        assert "逐字" not in strip_blocks(r"前\verb|逐字|后")


class TestCounts:
    def test_chinese_count(self):
        assert chinese_count("你好 world 你好") == 4

    def test_char_count_ignores_whitespace(self):
        assert char_count("a b\t中\n") == 3

    def test_strip_nonbody_keeps_table_cells(self):
        s = ("前文\\begin{table}\\begin{tabularx}{\\textwidth}{l X}\n"
             "单元格文字 & 数据\n\\end{tabularx}\\end{table}后文")
        out = strip_nonbody(s)
        assert "单元格文字" in out  # 表格单元格保留
        assert "前文" in out and "后文" in out

    def test_strip_nonbody_removes_figure_code_bib(self):
        s = ("正文\\begin{figure}图\\end{figure}"
             "\\begin{lstlisting}码\\end{lstlisting}"
             "\\begin{thebibliography}{99}\\bibitem{x} 文献\\end{thebibliography}")
        out = strip_nonbody(s)
        assert "图" not in out and "码" not in out and "文献" not in out
        assert "正文" in out

    def test_count_visible_body(self):
        s = "中 abc \\begin{figure}xxxx\\end{figure}"
        # 可见字符 = 中(1) + abc(3) = 4
        assert count_visible_body(s) == 4
