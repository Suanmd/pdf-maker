# -*- coding: utf-8 -*-
"""core.chapters：章节枚举与排序。"""

from pdfmaker.core.chapters import chapter_range, chapter_sort_key, collect_chapters
from conftest import write_chapter


class TestSortKey:
    def test_numeric_order_not_lexicographic(self):
        keys = [chapter_sort_key(f"第{n}章/第{n}章.tex") for n in (1, 2, 10)]
        assert keys == sorted(keys)

    def test_appendix_after_chapters(self):
        assert chapter_sort_key("第10章/第10章.tex") < chapter_sort_key("附录A/附录A.tex")

    def test_unknown_last(self):
        assert chapter_sort_key("第1章/x.tex") < chapter_sort_key("其他.tex")


class TestCollect:
    def test_collects_both_layouts(self, project):
        write_chapter(project, 1, "a")
        write_chapter(project, 2, "b")
        write_chapter(project, "附录A", "c")
        # 旧扁平布局
        (project / "第3章.tex").write_text("d", encoding="utf-8")
        files = collect_chapters(project)
        names = [f.name for f in files]
        assert names == ["第1章.tex", "第2章.tex", "第3章.tex", "附录A.tex"]

    def test_empty_project(self, project):
        assert collect_chapters(project) == []

    def test_chapter_range(self, project):
        assert chapter_range(project) == (0, 0)
        write_chapter(project, 2, "a")
        write_chapter(project, 5, "b")
        write_chapter(project, "附录A", "c")  # 附录不影响数字范围
        assert chapter_range(project) == (2, 5)
