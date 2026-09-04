# -*- coding: utf-8 -*-
"""commands.labels：跨章重复 label 去重与跨章引用中止。"""

import pytest

from pdfmaker.commands import labels
from conftest import GOOD_CHAPTER, write_chapter


class TestChapterKey:
    def test_numeric(self):
        assert labels.chapter_key("第3章/第3章.tex") == "3"

    def test_appendix(self):
        assert labels.chapter_key("附录A/附录A.tex") == "附录A"

    def test_unknown(self):
        assert labels.chapter_key("其他.tex") == "?"


class TestLabelsMain:
    def test_dedup_renames_both_chapters(self, project):
        p1 = write_chapter(project, 1, "\\label{fig:x}\n见 \\ref{fig:x}")
        p2 = write_chapter(project, 2, "\\label{fig:x}\n也见 \\ref{fig:x}")
        assert labels.main([str(project)]) == 0
        t1 = p1.read_text(encoding="utf-8")
        t2 = p2.read_text(encoding="utf-8")
        assert "\\label{fig:x-ch1}" in t1 and "\\ref{fig:x-ch1}" in t1
        assert "\\label{fig:x-ch2}" in t2 and "\\ref{fig:x-ch2}" in t2
        # 原名不再出现
        assert "\\label{fig:x}" not in t1 and "\\label{fig:x}" not in t2

    def test_no_collision_no_change(self, project):
        p1 = write_chapter(project, 1, "\\label{fig:a}")
        p2 = write_chapter(project, 2, "\\label{fig:b}")
        assert labels.main([str(project)]) == 0
        assert p1.read_text(encoding="utf-8") == "\\label{fig:a}"

    def test_cross_ref_aborts_without_changes(self, project):
        p1 = write_chapter(project, 1, "\\label{fig:x}")
        p2 = write_chapter(project, 2, "\\label{fig:x}")
        # 第 3 章引用了冲突 label 但自身不定义 → 跨章引用，必须中止
        p3 = write_chapter(project, 3, "参见 \\ref{fig:x}")
        rc = labels.main([str(project)])
        assert rc == 2
        # 中止时不做任何改写
        assert p1.read_text(encoding="utf-8") == "\\label{fig:x}"
        assert p3.read_text(encoding="utf-8") == "参见 \\ref{fig:x}"

    def test_no_chapter_files_raises(self, project):
        with pytest.raises(SystemExit):
            labels.main([str(project)])


class TestNoCollisionOutput:
    """无冲突时的输出：提示「无需改名」，不打印空的「应用改名：」段落。"""

    def test_no_collision_message(self, project, capsys):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert labels.main([str(project)]) == 0
        out = capsys.readouterr().out
        assert "无需改名" in out
        assert "应用改名" not in out
