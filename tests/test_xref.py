# -*- coding: utf-8 -*-
"""commands.xref：越界「第N章」文字引用 / 跨章 \\ref / 悬空 \\ref。"""

from pdfmaker.commands import xref
from conftest import write_chapter


class TestXrefMain:
    def test_all_ok(self, project):
        write_chapter(project, 1, "见第~2~章。\n\\label{sec:c1:a}\n\\ref{sec:c1:a}")
        write_chapter(project, 2, "回看第 1 章。")
        assert xref.main([str(project)]) == 0

    def test_text_ref_out_of_range_blocked(self, project):
        write_chapter(project, 1, "详见第9章。")
        write_chapter(project, 2, "正文")
        assert xref.main([str(project)]) == 1

    def test_cross_chapter_ref_blocked(self, project):
        write_chapter(project, 1, "\\ref{sec:c2:b}")
        write_chapter(project, 2, "\\label{sec:c2:b}")
        assert xref.main([str(project)]) == 1

    def test_dangling_ref_warns_not_blocks(self, project):
        write_chapter(project, 1, "\\ref{sec:nowhere}")
        write_chapter(project, 2, "正文")
        assert xref.main([str(project)]) == 0

    def test_expected_extends_range(self, project):
        write_chapter(project, 1, "详见第5章。")
        # 磁盘上只有 1 章；--expected 5 声明全书规模后不再判越界
        assert xref.main([str(project), "--expected", "5"]) == 0

    def test_self_only_ignores_other_chapters(self, project):
        p1 = write_chapter(project, 1, "详见第9章。")   # 越界，但非 target
        write_chapter(project, 2, "正文合规")
        # 以第 2 章为 target 的 self-only：第 1 章的越界不阻断
        assert xref.main(["2", "--self-only"]) == 0
        # 不带 self-only 时整书扫描，第 1 章越界阻断
        assert xref.main(["2"]) == 1

    def test_no_chapters_rc2(self, project):
        assert xref.main([str(project)]) == 2

    def test_pure_appendix_skips_range_check(self, project):
        # 全书无数字章 → (0,0)，无法判定范围，文字引用不检查
        write_chapter(project, "附录A", "见第99章。")
        assert xref.main([str(project)]) == 0
