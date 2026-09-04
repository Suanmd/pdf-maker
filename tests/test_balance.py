# -*- coding: utf-8 -*-
"""commands.balance：结构均衡、引用闭合、阻断/建议分级。"""

from pdfmaker.commands import balance
from conftest import GOOD_CHAPTER, write_chapter


def _bib(n: int, chapter: int = 1) -> str:
    """生成 n 条自洽（bibitem==cite==链接数）的文献块。"""
    items = []
    for i in range(1, n + 1):
        items.append(
            f"\\bibitem{{c{chapter}r{i}}} 作者. 标题. "
            f"\\href{{https://example.com/{chapter}/{i}}}{{ex{i}}}"
        )
    return "\\begin{thebibliography}{99}\n" + "\n".join(items) + "\n\\end{thebibliography}\n"


def _cites(n: int, chapter: int = 1) -> str:
    return "，".join(f"\\cite{{c{chapter}r{i}}}" for i in range(1, n + 1))


class TestCountFigures:
    def test_includegraphics_plus_tikz(self):
        s = "\\includegraphics{a.png}\n\\begin{tikzpicture}x\\end{tikzpicture}"
        assert balance.count_figures(s) == 2


class TestBalanceMain:
    def test_good_chapter_rc0(self, project):
        body = GOOD_CHAPTER  # 1 bibitem / 1 link / 1 cite，自洽
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 0

    def test_orphan_bibitem_blocked(self, project):
        body = GOOD_CHAPTER.replace(
            "\\bibitem{c1r1}",
            "\\bibitem{c1r1} 作者. 标题. \\href{https://example.com/a}{ex}\n"
            "\\bibitem{c1r2}", 1)
        # 现在：bibitem 2（c1r1+c1r2）、链接 1（仅 c1r1 的 href）、cite 1
        # → 孤儿 c1r2 + bibitem/链接数不一致，两项均为阻断级
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_dangling_cite_blocked(self, project):
        body = GOOD_CHAPTER.replace(r"\cite{c1r1}", r"\cite{c1r1,c1r9}")
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_bibitem_link_mismatch_blocked(self, project):
        # bibitem 无链接 → bibitem(1) != link(0)
        body = GOOD_CHAPTER.replace(
            "\\bibitem{c1r1} 作者. 标题. \\href{https://example.com/a}{example}",
            "\\bibitem{c1r1} 作者. 标题（无链接）")
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_empty_section_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\section{空节}\n"
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_truncated_url_blocked(self, project):
        body = GOOD_CHAPTER.replace(
            "https://example.com/a", "https://example.com/aaa…")
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_tikz_badbreak_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{tikzpicture}\n\\node{甲\\\\乙};\n\\end{tikzpicture}\n"
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_tikz_unescaped_amp_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{tikzpicture}\n\\node{Add & Norm};\n\\end{tikzpicture}\n"
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 1

    def test_low_refs_no_advisory_by_default(self, project, capsys):
        """MIN_REFS 默认 0（不设下限）：GOOD_CHAPTER 只有 1 条文献也不发数量建议。

        按需引用哲学：引用是论证需要而非配额，低引用不是缺陷，默认零噪音。
        """
        write_chapter(project, 1, GOOD_CHAPTER)
        assert balance.main(["1"]) == 0
        out = capsys.readouterr().out
        assert "参考文献仅" not in out

    def test_low_refs_advisory_when_min_refs_set(self, project, capsys, monkeypatch):
        """项目经配置显式设置正整数下限（如学术报告指标考核）时，恢复建议级告警。"""
        import pdfmaker.core.config as cfg
        monkeypatch.setattr(cfg, "MIN_REFS", 6)
        write_chapter(project, 1, GOOD_CHAPTER)
        assert balance.main(["1"]) == 0  # 建议级，不阻断
        assert "参考文献仅" in capsys.readouterr().out

    def test_zero_ref_chapter_no_min_refs_advisory(self, project, capsys):
        """零引用章（bibitem==0 且 link==0）：跳过 MIN_REFS 噪音建议。"""
        body = ("\\chapter{零引用}\n\\label{cha:c1}\n\n\\section{背景}\n\n"
                + "本章不含任何外部 URL，属于合法的零引用章。" * 12)
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 0
        out = capsys.readouterr().out
        assert "参考文献仅" not in out

    def test_six_refs_no_advisory(self, project, capsys):
        body = ("\\chapter{测试章}\n\\label{cha:c1}\n\n\\section{背景}\n\n"
                + "正文引用：" + _cites(6) + "。\n\n" + _bib(6))
        write_chapter(project, 1, body)
        assert balance.main(["1"]) == 0
        assert "参考文献仅" not in capsys.readouterr().out
