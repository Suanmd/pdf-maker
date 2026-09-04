# -*- coding: utf-8 -*-
"""core.paths：路径定位、模板解析、共用补丁占位符。"""

import pytest

from pdfmaker.core import paths
from pdfmaker.core.paths import (
    find_main_template,
    find_tmp_template,
    mid_name_for,
    resolve_shared_preamble,
    resolve_source,
    stem_of,
    workdir_for,
)
from conftest import write_chapter


class TestStemAndMid:
    def test_stem_numeric(self):
        assert stem_of("3") == "第3章"

    def test_stem_appendix_passthrough(self):
        assert stem_of("附录A") == "附录A"

    def test_mid_numeric(self):
        assert mid_name_for("3") == "ch3.tex"

    def test_mid_appendix(self):
        assert mid_name_for("附录A") == "附录A_ch.tex"


class TestResolveSource:
    def test_standard_layout(self, project):
        p = write_chapter(project, 2, "内容")
        assert resolve_source("2") == p.resolve()

    def test_flat_layout(self, project):
        p = project / "第3章.tex"
        p.write_text("x", encoding="utf-8")
        assert resolve_source("3") == p.resolve()

    def test_direct_tex_path(self, project):
        p = write_chapter(project, 4, "内容")
        assert resolve_source(str(p)) == p.resolve()

    def test_appendix(self, project):
        p = write_chapter(project, "附录A", "内容")
        assert resolve_source("附录A") == p.resolve()

    def test_missing_raises_with_tried_paths(self, project):
        with pytest.raises(SystemExit) as exc:
            resolve_source("99", "pdfmaker test")
        msg = str(exc.value)
        assert "第99章" in msg and "已尝试" in msg

    def test_from_inside_chapter_dir(self, project, monkeypatch):
        p = write_chapter(project, 5, "内容")
        monkeypatch.chdir(p.parent)
        assert resolve_source("5") == p.resolve()


class TestWorkdirFor:
    def test_prefers_dir_with_tmp_pdf(self, project):
        p = write_chapter(project, 1, "内容")
        (project / "_tmp.pdf").write_bytes(b"root")
        (p.parent / "_tmp.pdf").write_bytes(b"ch")
        assert workdir_for("1") == p.parent  # 章目录有 _tmp.pdf，优先

    def test_falls_back_to_existing(self, project):
        p = write_chapter(project, 1, "内容")
        assert workdir_for("1") == p.parent

    def test_ultimate_fallback(self, project):
        # 无 _tmp.pdf 时返回首个存在的目录：cwd（项目根）总是存在
        assert workdir_for("7") == project


class TestTemplates:
    def test_tmp_template_exists(self):
        p = find_tmp_template()
        assert p.exists() and p.name == "_tmp.tex"

    def test_main_template_exists(self):
        p = find_main_template()
        assert p.exists() and p.name == "main.tex"

    def test_shared_preamble_resolution(self):
        tpl = find_tmp_template().read_text(encoding="utf-8")
        assert "{{SHARED_PREAMBLE}}" in tpl  # 源模板含占位符
        resolved = resolve_shared_preamble(tpl)
        assert "{{SHARED_PREAMBLE}}" not in resolved
        assert "\\newtcblisting{codeblock}" in resolved  # 补丁片段已内联

    def test_shared_preamble_passthrough_without_placeholder(self):
        assert resolve_shared_preamble("无占位符") == "无占位符"

    def test_comment_mention_not_replaced(self):
        """回归：注释/散文里提及占位符不得被替换（多行片段注入注释会炸编译）。"""
        text = ("% 说明：模板里的 {{SHARED_PREAMBLE}} 会被替换\n"
                "正文行\n"
                "{{SHARED_PREAMBLE}}\n"
                "后续\n")
        out = resolve_shared_preamble(text)
        lines = out.split("\n")
        assert lines[0] == "% 说明：模板里的 {{SHARED_PREAMBLE}} 会被替换"  # 注释原样保留
        assert lines[1] == "正文行"
        assert "\\newtcblisting{codeblock}" in out  # 独立行被替换
        assert lines[-2] == "后续"  # 末行为空串（原文以 \n 结尾）


class TestLooksLikeProjectRoot:
    """looks_like_project_root：CWD 守卫的项目根判定（main.tex / materials.json / 章节目录）。"""

    def test_markers(self, tmp_path):
        assert paths.looks_like_project_root(tmp_path) is False
        (tmp_path / "main.tex").write_text("x", encoding="utf-8")
        assert paths.looks_like_project_root(tmp_path) is True

    def test_chapter_dir_counts(self, tmp_path):
        (tmp_path / "第2章").mkdir()
        assert paths.looks_like_project_root(tmp_path) is True

    def test_materials_json_counts(self, tmp_path):
        (tmp_path / "materials.json").write_text("{}", encoding="utf-8")
        assert paths.looks_like_project_root(tmp_path) is True
