# -*- coding: utf-8 -*-
"""commands.fix：单章预处理——规范化、中间文件、_tmp.tex 生成。"""

import pytest

from pdfmaker.commands import fix
from conftest import write_chapter


CH2_SRC = (
    "\\chapter{第二章}\n"
    "\\section{节}\n"
    "链接 \\url{https://example.com/a_b} 与符号 ≥。\n"
    "\\begin{tikzpicture}\n\\node{a};\n\\end{tikzpicture}\n"
)


class TestFixMain:
    def test_generates_mid_and_tmp(self, project):
        write_chapter(project, 2, CH2_SRC)
        assert fix.main(["2"]) == 0

        mid = (project / "第2章" / "ch2.tex").read_text(encoding="utf-8")
        # URL 规范化：\url → \href，显示文本转义
        assert "\\href{https://example.com/a_b}{https://example.com/a\\_b}" in mid
        assert "\\url{" not in mid
        # 字形自动修：正文 ≥ → $\ge$
        assert "$\\ge$" in mid
        # TikZ 图宽上限
        assert "\\begin{adjustbox}{max width=\\textwidth}" in mid

        tmp = (project / "第2章" / "_tmp.tex").read_text(encoding="utf-8")
        # 占位符替换为实际中间文件
        assert "\\input{ch2.tex}" in tmp
        assert "\\input{CHAPTER_TEX}" not in tmp
        # 共用补丁已内联
        assert "{{SHARED_PREAMBLE}}" not in tmp
        assert "\\newtcblisting{codeblock}" in tmp
        assert "\\def\\Url@FormatString" in tmp

    def test_idempotent_rerun(self, project):
        write_chapter(project, 2, CH2_SRC)
        fix.main(["2"])
        first = (project / "第2章" / "ch2.tex").read_text(encoding="utf-8")
        fix.main(["2"])
        second = (project / "第2章" / "ch2.tex").read_text(encoding="utf-8")
        assert first == second
        assert first.count("\\begin{adjustbox}") == 1

    def test_appendix_mid_name(self, project):
        write_chapter(project, "附录A", "\\chapter{附录}\n正文 \\url{https://a.com}\n")
        assert fix.main(["附录A"]) == 0
        assert (project / "附录A" / "附录A_ch.tex").exists()
        tmp = (project / "附录A" / "_tmp.tex").read_text(encoding="utf-8")
        assert "\\input{附录A_ch.tex}" in tmp

    def test_missing_chapter_raises(self, project):
        with pytest.raises(SystemExit):
            fix.main(["9"])
