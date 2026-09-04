# -*- coding: utf-8 -*-
"""commands.scaffold：素材解析、合规富骨架、整书初始化、非破坏性写盘。"""

import re

from pdfmaker.commands import scaffold
from pdfmaker.core import lint as lint_mod
from pdfmaker.core.paths import find_tmp_template

from conftest import GOOD_CHAPTER


MATERIAL = """\
# 第3章 电池安全评估

## 背景与动机

随着装机量增长，安全问题凸显。参考 https://example.com/report 与
https://arxiv.org/abs/1234.5678 。

## 评估方法

详见 https://example.com/report （重复 URL，应去重）。

## 结果
"""


class TestParseMaterial:
    def test_parses_title_sections_urls(self, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text(MATERIAL, encoding="utf-8")
        title, sections, urls = scaffold.parse_material(str(md))
        assert title == "第3章 电池安全评估"
        assert sections == ["背景与动机", "评估方法", "结果"]
        assert urls == ["https://example.com/report", "https://arxiv.org/abs/1234.5678"]

    def test_missing_material_returns_empty(self, tmp_path):
        assert scaffold.parse_material(str(tmp_path / "无.md")) == ("", [], [])

    def test_section_same_as_title_skipped(self, tmp_path):
        md = tmp_path / "m.md"
        md.write_text("# 标题\n\n## 标题\n\n## 其它\n", encoding="utf-8")
        _, sections, _ = scaffold.parse_material(str(md))
        assert sections == ["其它"]


class TestStripChapterPrefix:
    def test_strips_numeric(self):
        assert scaffold._strip_chapter_prefix("第3章 电池安全") == "电池安全"

    def test_strips_chinese_numeral(self):
        assert scaffold._strip_chapter_prefix("第三章 电池安全") == "电池安全"

    def test_keeps_normal_title(self):
        assert scaffold._strip_chapter_prefix("电池安全") == "电池安全"


class TestBuildChapterSkeleton:
    def test_compliance_invariants(self):
        sk = scaffold.build_chapter_skeleton(
            3, title="第3章 电池安全", sections=["背景", "方法"],
            urls=["https://a.com/1", "https://a.com/2"])
        # 章标题剥离了「第N章」前缀（避免与 ctexrep 自动编号重复）
        assert "\\chapter{电池安全}" in sk
        # 三线表规范：含 booktabs 规则线、无 \hline、无列格式竖线
        assert "\\toprule" in sk and "\\bottomrule" in sk
        assert "\\hline" not in sk
        assert not re.search(r"\\begin\{tabularx?\}\{[^}]*\}\{[^}]*\|", sk)
        # 表题在上、图题在下
        assert sk.index("\\caption{示例三线表") < sk.index("\\begin{tabularx}")
        assert sk.index("\\end{tikzpicture}") < sk.index("\\caption{示例流程图")
        # codeblock 示例
        assert "\\begin{codeblock}" in sk
        # 引用闭合：预填 bibitem 与 cite 键一致
        bibitems = set(re.findall(r"\\bibitem\{([^}]+)\}", sk))
        cites = set(re.findall(r"\\cite\{([^}]+)\}", sk))
        assert bibitems == {"c3r1", "c3r2"}
        assert cites == {"c3r1", "c3r2"}
        # 标签带章号前缀
        assert "\\label{cha:c3}" in sk and "\\label{sec:c3:intro}" in sk

    def test_default_fallbacks(self):
        sk = scaffold.build_chapter_skeleton(1)
        assert "\\chapter{未命名章标题}" in sk
        assert "\\section{背景与动机}" in sk and "\\section{方法或结论}" in sk
        assert "\\label{cha:c1}" in sk

    def test_no_url_material_has_no_bibliography(self):
        """零引用章（素材无 URL）：不生成 thebibliography，避免空参考文献标题。"""
        sk = scaffold.build_chapter_skeleton(3, title="零引用", sections=["甲"])
        assert "\\begin{thebibliography}" not in sk
        assert "零引用章是合法形态" in sk

    def test_url_material_keeps_bibliography(self):
        sk = scaffold.build_chapter_skeleton(3, title="有引用", sections=["甲"],
                                             urls=["https://a.com/1"])
        assert "\\begin{thebibliography}" in sk
        assert "\\bibitem{c3r1}" in sk

    def test_sections_capped_at_8(self):
        sk = scaffold.build_chapter_skeleton(1, sections=[f"节{i}" for i in range(20)])
        assert sk.count("\\section{节") == 8

    def test_skeleton_passes_style_gates(self):
        """元测试：生成的骨架必须能通过 lint 的全部阻断级样式扫描。"""
        sk = scaffold.build_chapter_skeleton(
            2, title="合规", sections=["甲", "乙"], urls=["https://a.com"])
        assert lint_mod.scan_table_style(sk) == []
        assert lint_mod.scan_table_rules(sk) == []
        assert lint_mod.scan_caption_position(sk) == []
        assert lint_mod.scan_raw_verbatim(sk) == []
        assert lint_mod.scan_cite_undef(sk) == []
        assert lint_mod.scan_tikz_badbreak(sk) == []
        assert lint_mod.scan_tikz_amp(sk) == []
        assert lint_mod.scan_codeblock_nonascii(sk) == []
        assert lint_mod.scan_redundant_heading_number(sk) == []


class TestWriteChapter:
    def test_writes_then_skips(self, project):
        assert scaffold.write_chapter(5, root=str(project)) is True
        p = project / "第5章" / "第5章.tex"
        assert p.exists()
        before = p.read_text(encoding="utf-8")
        assert scaffold.write_chapter(5, root=str(project)) is False  # 不覆盖
        assert p.read_text(encoding="utf-8") == before

    def test_force_overwrites(self, project):
        scaffold.write_chapter(5, root=str(project))
        p = project / "第5章" / "第5章.tex"
        p.write_text("手写内容", encoding="utf-8")
        assert scaffold.write_chapter(5, root=str(project), force=True) is True
        assert "\\chapter{" in p.read_text(encoding="utf-8")


class TestFillMainTemplate:
    def test_all_placeholders_filled(self):
        tpl = ("{{TITLE}}|{{PDF_TITLE}}|{{SUBTITLE}}|{{EPIGRAPH}}|"
               "{{EPIGRAPH_CLOSING}}|{{AUTHOR}}|{{DATE}}|{{CHAPTERS_LIST}}")
        out = scaffold._fill_main_template(
            tpl, title="书名\\\\换行", subtitle="副", epigraph="引",
            epigraph_closing="尾", author="某", date_str="某日",
            chapters_list="\\input{第1章/第1章}")
        assert "{{" not in out
        # PDF_TITLE 必须单行：\\ 被替换为空格
        assert "书名 换行" in out


class TestScaffoldInit:
    def test_generates_compilable_layout(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert scaffold.main(["mybook", "--chapters", "2", "--appendices", "1",
                              "--title", "测试书", "--author", "佚名"]) == 0
        root = tmp_path / "mybook"
        main_tex = (root / "main.tex").read_text(encoding="utf-8")
        assert "\\input{第1章/第1章}" in main_tex
        assert "\\input{第2章/第2章}" in main_tex
        assert "\\input{附录A/附录A}" in main_tex
        # 占位符已被替换/内联
        assert "{{CHAPTERS_LIST}}" not in main_tex
        assert "{{SHARED_PREAMBLE}}" not in main_tex
        assert "\\newtcblisting{codeblock}" in main_tex  # 共用补丁已内联
        assert "测试书" in main_tex
        assert (root / "_tmp.tex").exists()
        assert (root / "第1章" / "第1章.tex").exists()
        assert (root / "附录A" / "附录A.tex").exists()

    def test_refuses_nonempty_dir_without_force(self, project):
        (project / "existing.txt").write_text("x", encoding="utf-8")
        assert scaffold.main([str(project)]) == 2

    def test_force_skips_existing_files(self, project):
        (project / "main.tex").write_text("我的手写 main", encoding="utf-8")
        assert scaffold.main([str(project), "--force"]) == 0
        assert (project / "main.tex").read_text(encoding="utf-8") == "我的手写 main"


class TestScaffoldChapter:
    def test_chapter_from_material(self, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text(MATERIAL, encoding="utf-8")
        root = tmp_path / "book"
        root.mkdir()
        (root / "main.tex").write_text("\\documentclass{ctexrep}\n", encoding="utf-8")
        assert scaffold.main(["chapter", "3", "--material", str(md),
                              "--root", str(root)]) == 0
        tex = (root / "第3章" / "第3章.tex").read_text(encoding="utf-8")
        assert "\\chapter{电池安全评估}" in tex
        assert "\\section{背景与动机}" in tex
        assert "\\bibitem{c3r1}" in tex


class TestPlaceholderMarker:
    """is_untouched_placeholder：判定章文件是否仍是未命名的占位骨架。"""

    def test_is_untouched_placeholder(self):
        assert scaffold.is_untouched_placeholder(
            scaffold.build_chapter_skeleton(3)) is True
        assert scaffold.is_untouched_placeholder(
            scaffold.build_chapter_skeleton(3, title="已命名")) is False
        assert scaffold.is_untouched_placeholder(GOOD_CHAPTER) is False


class TestScaffoldChapterCwdGuard:
    """scaffold chapter 的 CWD 守卫：裸目录拒绝创建，--force 豁免。"""

    def test_scaffold_chapter_guard(self, tmp_path):
        root = tmp_path / "bare"
        root.mkdir()
        assert scaffold.main(["chapter", "3", "--root", str(root)]) == 2
        assert not (root / "第3章").exists()
        assert scaffold.main(["chapter", "3", "--root", str(root), "--force"]) == 0
        assert (root / "第3章" / "第3章.tex").exists()


class TestHeaderSingleMark:
    """页眉单标记版式：章题/节题分置偶奇页，杜绝长标题行中相撞重叠；
    且刻意不用 fancyhdr（其与内核新 mark 机制协作异常会重复排版），
    用内核原生 \\@evenhead/\\@oddhead 自绘 pagestyle。"""

    def _assert_header_scheme(self, text: str):
        assert "\\def\\ps@pdfmaker" in text              # 自绘 pagestyle
        assert "\\@evenhead" in text and "\\@oddhead" in text
        assert "\\leftmark" in text and "\\rightmark" in text
        assert "MakeUppercase" in text                   # 大小写中性化配方
        assert "\\usepackage{fancyhdr}" not in text      # 不再加载 fancyhdr
        assert "\\pagestyle{fancy}" not in text
        assert "\\fancyhead" not in text

    def test_main_template_single_mark(self, tmp_path):
        root = tmp_path / "book"
        assert scaffold.main([str(root), "--chapters", "1"]) == 0
        main = (root / "main.tex").read_text(encoding="utf-8")
        # scaffold 落地的 main.tex 共用补丁已内联，页眉方案应与模板一致
        self._assert_header_scheme(main)

    def test_tmp_template_single_mark(self):
        tmp = find_tmp_template().read_text(encoding="utf-8")
        self._assert_header_scheme(tmp)


class TestStripSectionNumber:
    def test_numeric_dot_prefix(self):
        assert scaffold._strip_section_number("1. 这套系统是什么") == "这套系统是什么"

    def test_nested_numeric_prefix(self):
        assert scaffold._strip_section_number("2.3 异步编排") == "异步编排"

    def test_deep_numeric_prefix(self):
        assert scaffold._strip_section_number("3.1.2 细节") == "细节"

    def test_year_not_stripped(self):
        # 无点号的年份标题不剥离（防误伤）
        assert scaffold._strip_section_number("2024 年度报告") == "2024 年度报告"

    def test_version_like_not_stripped(self):
        assert scaffold._strip_section_number("v9.9 发布说明") == "v9.9 发布说明"

    def test_no_prefix_unchanged(self):
        assert scaffold._strip_section_number("全景总览") == "全景总览"


class TestParseMaterialNumericStrip:
    def test_sections_stripped(self, tmp_path):
        p = tmp_path / "素材.md"
        p.write_text("# 1. 章标题\n\n## 1.1 第一节\n## 普通节\n## 2. 第二节\n",
                     encoding="utf-8")
        title, sections, urls = scaffold.parse_material(str(p))
        assert title == "章标题"
        assert sections == ["第一节", "普通节", "第二节"]
