# -*- coding: utf-8 -*-
"""core.lint：全部编译前静态扫描函数的正反例。"""

from pdfmaker.core.lint import (
    inject_frontmatter_noindent,
    scan_caption_position,
    scan_cite_undef,
    scan_codeblock_nonascii,
    scan_crossref,
    scan_empty_frontmatter,
    scan_frontmatter_tables,
    scan_glyphs,
    scan_missing_frontmatter,
    scan_preamble_drift,
    scan_raw_verbatim,
    scan_redundant_heading_number,
    scan_squeezed_tables,
    scan_table_rules,
    scan_table_style,
    scan_tikz_amp,
    scan_tikz_badbreak,
    scan_truncated_urls,
    scan_unbreakable_runs,
)


class TestScanGlyphs:
    def test_flags_text_mode_glyph(self):
        hits = scan_glyphs("正文 ≥ 缺字")
        assert len(hits) == 1
        assert hits[0]["char"] == "≥"
        assert hits[0]["line"] == 1

    def test_math_mode_not_flagged(self):
        assert scan_glyphs(r"$x \ge 1$") == []
        assert scan_glyphs("\\[\\alpha + \\beta\\]") == []
        assert scan_glyphs("\\begin{equation}\\sigma\\end{equation}") == []

    def test_comment_line_skipped(self):
        assert scan_glyphs("% ≥ 注释里的字符") == []

    def test_greek_in_text_flagged(self):
        hits = scan_glyphs("参数 σ 很大")
        assert any(h["char"] == "σ" for h in hits)

    def test_arrow_not_flagged(self):
        # 右箭头（ → ，U+2192）在 CJK 字体中存在，刻意不纳入
        assert scan_glyphs("甲 → 乙") == []


class TestScanTruncatedUrls:
    def test_ellipsis(self):
        assert scan_truncated_urls(r"\url{https://a.com/foo…}") != []

    def test_three_dots(self):
        assert scan_truncated_urls(r"\href{https://a.com/foo...bar}{x}") != []

    def test_whitespace(self):
        assert scan_truncated_urls(r"\url{https://a.com/foo bar}") != []

    def test_normal_url_ok(self):
        assert scan_truncated_urls(r"\url{https://a.com/foo?x=1}") == []

    def test_protocol_slashes_not_misjudged(self):
        # :// 只有两个点之前的部分；正常域名不触发
        assert scan_truncated_urls(r"\url{https://sub.a.com/x}") == []


class TestScanTikzBadbreak:
    def test_bad_break_flagged(self):
        s = "\\begin{tikzpicture}\n\\node{甲\\\\乙};\n\\end{tikzpicture}"
        hits = scan_tikz_badbreak(s)
        assert len(hits) == 1
        assert hits[0]["line"] == 2

    def test_align_ok(self):
        s = "\\begin{tikzpicture}\n\\node[align=center]{甲\\\\乙};\n\\end{tikzpicture}"
        assert scan_tikz_badbreak(s) == []

    def test_shared_style_with_align_ok(self):
        s = ("\\begin{tikzpicture}[box/.style={draw, align=center}]\n"
             "\\node[box]{甲\\\\乙};\n\\end{tikzpicture}")
        assert scan_tikz_badbreak(s) == []

    def test_no_break_ok(self):
        s = "\\begin{tikzpicture}\n\\node{甲乙};\n\\end{tikzpicture}"
        assert scan_tikz_badbreak(s) == []

    def test_outside_tikz_ignored(self):
        assert scan_tikz_badbreak("正文 \\\\ 换行") == []


class TestScanTikzAmp:
    def test_unescaped_amp_flagged(self):
        s = "\\begin{tikzpicture}\n\\node[align=center]{Add & Norm};\n\\end{tikzpicture}"
        assert len(scan_tikz_amp(s)) == 1

    def test_escaped_amp_ok(self):
        s = "\\begin{tikzpicture}\n\\node{Add \\& Norm};\n\\end{tikzpicture}"
        assert scan_tikz_amp(s) == []

    def test_outside_tikz_ignored(self):
        assert scan_tikz_amp("表格 A & B") == []


class TestScanCodeblockNonascii:
    def test_nonascii_flagged_once_per_line(self):
        s = "\\begin{codeblock}\n# ±3σ 多个\n# 又一σ\n\\end{codeblock}"
        hits = scan_codeblock_nonascii(s)
        assert len(hits) == 2  # 每行至多一个
        assert hits[0]["line"] == 2

    def test_ascii_ok(self):
        s = "\\begin{codeblock}\n# pure ascii\n\\end{codeblock}"
        assert scan_codeblock_nonascii(s) == []

    def test_verbatim_and_lstlisting_covered(self):
        assert scan_codeblock_nonascii("\\begin{verbatim}\n中文\n\\end{verbatim}") != []
        assert scan_codeblock_nonascii("\\begin{lstlisting}\n中文\n\\end{lstlisting}") != []


class TestScanTableStyle:
    def test_hline_flagged(self):
        hits = scan_table_style("\\begin{tabular}{l l}\n\\hline\na & b\n\\end{tabular}")
        assert any(h["kind"] == "hline" for h in hits)

    def test_vrule_flagged(self):
        hits = scan_table_style("\\begin{tabular}{l|c}\na & b\n\\end{tabular}")
        assert any(h["kind"] == "vrule" for h in hits)

    def test_tabularx_vrule_flagged(self):
        hits = scan_table_style("\\begin{tabularx}{\\textwidth}{l|X}\na & b\n\\end{tabularx}")
        assert any(h["kind"] == "vrule" for h in hits)

    def test_booktabs_ok(self):
        s = ("\\begin{tabularx}{\\textwidth}{l X}\n\\toprule\na & b \\\\\n"
             "\\midrule\nc & d \\\\\n\\bottomrule\n\\end{tabularx}")
        assert scan_table_style(s) == []


class TestScanTableRules:
    def test_missing_rules_flagged(self):
        s = "\\begin{tabular}{l l}\na & b\n\\end{tabular}"
        hits = scan_table_rules(s)
        assert len(hits) == 1 and hits[0]["kind"] == "missing_rule"

    def test_toprule_bottomrule_ok(self):
        s = "\\begin{tabular}{l l}\n\\toprule\na & b\n\\bottomrule\n\\end{tabular}"
        assert scan_table_rules(s) == []


class TestScanCaptionPosition:
    def test_table_caption_below_flagged(self):
        s = ("\\begin{table}[htbp]\n\\begin{tabular}{l l}\n\\toprule\na & b\n\\bottomrule\n"
             "\\end{tabular}\n\\caption{在下}\n\\end{table}")
        hits = scan_caption_position(s)
        assert any(h["kind"] == "caption_table_below" for h in hits)

    def test_table_caption_above_ok(self):
        s = ("\\begin{table}[htbp]\n\\caption{在上}\n\\begin{tabular}{l l}\n\\toprule\na\n"
             "\\bottomrule\n\\end{tabular}\n\\end{table}")
        assert scan_caption_position(s) == []

    def test_figure_caption_above_flagged(self):
        s = ("\\begin{figure}[htbp]\n\\caption{在上}\n"
             "\\begin{tikzpicture}\\node{a};\\end{tikzpicture}\n\\end{figure}")
        hits = scan_caption_position(s)
        assert any(h["kind"] == "caption_figure_above" for h in hits)

    def test_figure_caption_below_ok(self):
        s = ("\\begin{figure}[htbp]\n\\begin{tikzpicture}\\node{a};\\end{tikzpicture}\n"
             "\\caption{在下}\n\\end{figure}")
        assert scan_caption_position(s) == []

    def test_star_variants_covered(self):
        s = ("\\begin{table*}[htbp]\n\\begin{tabular}{l l}\n\\toprule\na\n\\bottomrule\n"
             "\\end{tabular}\n\\caption{在下}\n\\end{table*}")
        assert any(h["kind"] == "caption_table_below" for h in scan_caption_position(s))


class TestScanRawVerbatim:
    def test_flagged(self):
        assert len(scan_raw_verbatim("\\begin{verbatim}\nx\n\\end{verbatim}")) == 1
        assert len(scan_raw_verbatim("\\begin{lstlisting}\nx\n\\end{lstlisting}")) == 1

    def test_codeblock_ok(self):
        assert scan_raw_verbatim("\\begin{codeblock}\nx\n\\end{codeblock}") == []


class TestScanCrossref:
    def test_undefined_label_flagged(self):
        hits = scan_crossref("见 \\ref{sec:c2:other}")
        assert len(hits) == 1 and hits[0]["target"] == "sec:c2:other"

    def test_local_label_ok(self):
        s = "\\label{sec:c1:a}\n见 \\ref{sec:c1:a}"
        assert scan_crossref(s) == []

    def test_eqref_pageref_covered(self):
        assert len(scan_crossref("\\eqref{eq:x}")) == 1
        assert len(scan_crossref("\\pageref{p:x}")) == 1


class TestScanCiteUndef:
    def test_dangling_cite_flagged(self):
        hits = scan_cite_undef("引用\\cite{c1r9}\n\\begin{thebibliography}{99}\n"
                               "\\bibitem{c1r1} x\n\\end{thebibliography}")
        assert len(hits) == 1 and hits[0]["key"] == "c1r9"

    def test_defined_ok(self):
        s = "引用\\cite{c1r1}\n\\begin{thebibliography}{99}\n\\bibitem{c1r1} x\n\\end{thebibliography}"
        assert scan_cite_undef(s) == []

    def test_multi_key_cite(self):
        s = "\\cite{c1r1, c1r2}\n\\bibitem{c1r1} x"
        hits = scan_cite_undef(s)
        assert [h["key"] for h in hits] == ["c1r2"]

    def test_commented_cite_ignored(self):
        s = "% \\cite{c1r9}\n\\bibitem{c1r1} x"
        assert scan_cite_undef(s) == []

    def test_codeblock_cite_ignored(self):
        s = "\\begin{codeblock}\n# \\cite{fake}\n\\end{codeblock}\n\\bibitem{c1r1} x"
        assert scan_cite_undef(s) == []

    def test_bibitem_with_optional_label(self):
        s = "\\cite{k1}\n\\bibitem[甲]{k1} x"
        assert scan_cite_undef(s) == []


class TestScanRedundantHeadingNumber:
    def test_chapter_prefix_flagged(self):
        hits = scan_redundant_heading_number("\\chapter{第3章 标题}")
        assert hits and hits[0]["kind"] == "chapter_prefix"

    def test_section_prefix_flagged(self):
        hits = scan_redundant_heading_number("\\section{1.2 标题}")
        assert hits and hits[0]["kind"] == "section_prefix"

    def test_star_variant_skipped(self):
        assert scan_redundant_heading_number("\\chapter*{第3章 标题}") == []

    def test_normal_heading_ok(self):
        assert scan_redundant_heading_number("\\chapter{标题}\\section{介绍}") == []


class TestFrontmatterNoindent:
    FRONT = "序言正文\n\n\\begin{tabularx}{\\textwidth}{l X}\na & b\n\\end{tabularx}\n\n\\input{第1章/第1章}\n"

    def test_scan_flags_missing_noindent(self):
        bad = scan_frontmatter_tables(self.FRONT)
        assert bad == [3]

    def test_scan_ok_with_noindent(self):
        s = "序言\n\n\\noindent\n\\begin{tabularx}{\\textwidth}{l X}\na\n\\end{tabularx}\n\\input{第1章/第1章}"
        assert scan_frontmatter_tables(s) == []

    def test_scan_skips_table_float(self):
        s = ("\\begin{table}[htbp]\n\\begin{tabularx}{\\textwidth}{l X}\na\n\\end{tabularx}\n"
             "\\end{table}\n\\input{第1章/第1章}")
        assert scan_frontmatter_tables(s) == []

    def test_scan_ignores_chapters_after_input(self):
        s = "\\input{第1章/第1章}\n\n\\begin{tabular}{l}\na\n\\end{tabular}\n"
        assert scan_frontmatter_tables(s) == []

    def test_inject_adds_noindent(self):
        out = inject_frontmatter_noindent(self.FRONT)
        assert "\\noindent\n\\begin{tabularx}" in out
        # 注入后扫描通过
        assert scan_frontmatter_tables(out) == []

    def test_inject_idempotent(self):
        once = inject_frontmatter_noindent(self.FRONT)
        assert inject_frontmatter_noindent(once) == once

    def test_inject_preserves_tail(self):
        out = inject_frontmatter_noindent(self.FRONT)
        assert out.endswith("\\input{第1章/第1章}\n")


class TestScanMissingFrontmatter:
    def test_all_present(self):
        s = "\\chapter*{摘\\quad 要}\\chapter*{序\\quad 言}\\chapter*{术语表}"
        assert scan_missing_frontmatter(s) == []

    def test_all_missing(self):
        assert scan_missing_frontmatter("正文") == ["摘要", "序言", "术语表"]


class TestScanPreambleDrift:
    SHARED = ("\\def\\Url@FormatString{}\n"
              "\\patchcmd{\\thebibliography}{\\chapter*{\\bibname}}{}{}{}\n"
              "\\newtcblisting{codeblock}{}\n"
              "\\setlength{\\emergencystretch}{3.5em}\n")

    def test_no_drift(self):
        assert scan_preamble_drift(self.SHARED, self.SHARED) == []

    def test_drift_detected(self):
        main = self.SHARED.replace("\\newtcblisting{codeblock}{}\n", "")
        assert scan_preamble_drift(main, self.SHARED) == ["codeblock 环境"]


class TestScanEmptyFrontmatter:
    """scan_empty_frontmatter：前置部分「存在但只有模板占位注释」的空壳检测。"""

    def test_filled_frontmatter_not_reported(self):
        text = ("\\chapter*{摘\\quad 要}\n本书讨论优化器。\n"
                "\\chapter*{序\\quad 言}\n写给读者的话。\n"
                "\\tableofcontents\n\\chapter{正章}\n")
        assert scan_empty_frontmatter(text) == []

    def test_comment_only_abstract_reported(self):
        """摘要标题下只有模板注释 + 结构命令（与模板默认一致）→ 检出「摘要」。"""
        text = ("\\chapter*{摘\\quad 要}\n\\addcontentsline{toc}{chapter}{摘要}\n\n"
                "% 在此输入摘要正文\n\n\\newpage\n\n"
                "\\chapter*{序\\quad 言}\n有内容的序言。\n\\chapter{正章}\n")
        assert scan_empty_frontmatter(text) == ["摘要"]

    def test_empty_preface_reported(self):
        text = ("\\chapter*{摘\\quad 要}\n摘要正文。\n"
                "\\chapter*{序\\quad 言}\n% 待写\n\\chapter{正章}\n")
        assert scan_empty_frontmatter(text) == ["序言"]

    def test_missing_section_not_reported(self):
        """整节缺失归 scan_missing_frontmatter 管，本函数不重复报告。"""
        text = "\\chapter*{摘\\quad 要}\n摘要正文。\n\\chapter{正章}\n"
        assert scan_empty_frontmatter(text) == []

    def test_body_stops_at_boundary(self):
        """正文判定到 \\tableofcontents / 下一 \\chapter 为止，后面章节内容不误填充。"""
        text = ("\\chapter*{摘\\quad 要}\n% 空着\n"
                "\\tableofcontents\n\\chapter{正章}\n正文很多。\n\\end{document}\n")
        assert scan_empty_frontmatter(text) == ["摘要"]


class TestScanUnbreakableRuns:
    r"""scan_unbreakable_runs：等宽 \texttt 不可断行长串（Overfull \hbox 风险）预警。

    用例素材取自真实成书写作期触发过 Overfull 的 12 处长标识符场景。
    """

    def test_long_identifier_flagged(self):
        # 真实案例：38 字形采样器类名，编译实测 Overfull
        hits = scan_unbreakable_runs(
            r"提供 \texttt{GatherAndInnerLoopSPDistributedSampler}（继承 X）"
        )
        assert len(hits) == 1
        assert hits[0]["run"] == "GatherAndInnerLoopSPDistributedSampler"
        assert hits[0]["length"] == 38

    def test_chained_texttt_via_slash_merged(self):
        # \texttt{native}/\texttt{auto}... 经 / 连排在 TeX 眼中是一个不可断整体
        hits = scan_unbreakable_runs(
            r"策略：\texttt{native}/\texttt{auto}/\texttt{expert\_lookahead}"
            r"/\texttt{expert\_with\_layer} 四档"
        )
        assert len(hits) == 1
        assert hits[0]["run"] == "native/auto/expert_lookahead/expert_with_layer"
        assert hits[0]["length"] == 46

    def test_escaped_underscore_counts_as_one_glyph(self):
        # PYTORCH\_NPU\_ALLOC\_CONF=expandable\_segments:True —— 47 字形（真实案例）
        hits = scan_unbreakable_runs(
            r"\texttt{PYTORCH\_NPU\_ALLOC\_CONF=expandable\_segments:True}。"
        )
        assert len(hits) == 1
        assert hits[0]["length"] == 47

    def test_short_run_not_flagged(self):
        assert scan_unbreakable_runs(r"调用 \texttt{ops.rms\_norm(...)} 即可") == []

    def test_just_below_threshold_not_flagged(self):
        # 24 字形 < 默认阈值 25
        assert scan_unbreakable_runs(r"\texttt{GatherAndInnerLoopSPDist}") == []

    def test_threshold_zero_disables(self):
        assert scan_unbreakable_runs(
            r"\texttt{GatherAndInnerLoopSPDistributedSampler}", threshold=0
        ) == []

    def test_custom_threshold(self):
        hits = scan_unbreakable_runs(r"\texttt{abcdefghij}", threshold=10)
        assert len(hits) == 1 and hits[0]["length"] == 10

    def test_codeblock_env_not_flagged(self):
        # codeblock 内的 \texttt 是字面文本而非命令（等宽折行环境，无溢出风险）
        text = ("\\begin{codeblock}\n"
                "\\texttt{GatherAndInnerLoopSPDistributedSampler}\n"
                "\\end{codeblock}")
        assert scan_unbreakable_runs(text) == []

    def test_comment_not_flagged(self):
        assert scan_unbreakable_runs(
            r"% \texttt{GatherAndInnerLoopSPDistributedSampler}"
        ) == []

    def test_plain_prose_word_not_flagged(self):
        # 无 \texttt 的长英文词走正文断词，不在预警范围
        assert scan_unbreakable_runs(
            "thisisaverylongenglishidentifierwithoutanybreak"
        ) == []

    def test_cjk_is_boundary(self):
        # CJK 前后是天然断点，两段短串各自不达阈值
        assert scan_unbreakable_runs(r"\texttt{abc}中文\texttt{def}") == []

    def test_command_word_is_boundary(self):
        # \quad 等命令词是断点，不应与 texttt 内容粘成假长串
        assert scan_unbreakable_runs(
            r"前\quad\texttt{GatherAndInnerLoopSPDistributedSampler}后",
            threshold=39,
        ) == []

    def test_command_word_glue_still_flags_real_run(self):
        hits = scan_unbreakable_runs(
            r"使用\textbf{加粗}\texttt{GatherAndInnerLoopSPDistributedSampler}即可"
        )
        assert len(hits) == 1
        assert hits[0]["run"] == "GatherAndInnerLoopSPDistributedSampler"

    def test_hyphen_is_boundary(self):
        # TeX 允许在显式连字符后断行
        assert scan_unbreakable_runs(
            r"\texttt{abcdefghijklm}- nopqrstuvwxyz", threshold=14
        ) == []

    def test_space_inside_texttt_is_boundary(self):
        # \texttt 内的空格同样是断点
        assert scan_unbreakable_runs(
            r"\texttt{plan=\{x\} aaaaaaaaaaaaaaaaaaaa bbbbbbbbbbbbbbbbbbbb}"
        ) == []

    def test_line_number_accurate(self):
        text = ("第一章\n"
                "第二行\n"
                "第三行 \\texttt{GatherAndInnerLoopSPDistributedSampler}\n"
                "第四行\n")
        hits = scan_unbreakable_runs(text)
        assert len(hits) == 1
        assert hits[0]["line"] == 3

    def test_unbalanced_texttt_no_crash(self):
        # 未闭合的 \texttt{ 放弃解析（结构错误归其它门禁），不得崩溃
        assert scan_unbreakable_runs(
            r"\texttt{GatherAndInnerLoopSPDistributedSampler"
        ) == []

    def test_no_texttt_fast_path(self):
        assert scan_unbreakable_runs("纯中文正文，没有任何等宽命令。") == []

    def test_run_overlapping_href_url_not_flagged(self):
        # \href 里的长 URL 走 hyperref 可断行实现，不属于 \texttt 区间
        assert scan_unbreakable_runs(
            r"\href{https://example.com/aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa}{x}"
        ) == []


class TestScanSqueezedTables:
    def _tex(self, colspec: str, rows: str) -> str:
        return (
            "\\begin{table}[htbp]\n"          # 行 1
            "\\begin{tabularx}{\\textwidth}{" + colspec + "}\n"  # 行 2
            "\\toprule\n"                     # 行 3
            "字段 & 说明 \\\\\n"              # 行 4
            "\\midrule\n"                     # 行 5
            + rows +
            "\\bottomrule\n"
            "\\end{tabularx}\n"
            "\\end{table}\n"
        )

    def test_l_column_long_texttt_hit(self):
        tex = self._tex("l X",
            "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} & 缓冲 \\\\\n")
        hits = scan_squeezed_tables(tex, threshold=20)
        assert len(hits) == 1
        h = hits[0]
        assert h["col"] == 1 and h["letter"] == "l"
        assert h["length"] == 42
        assert h["line"] == 6  # 长串所在源行（非 \\end{tabularx} 行）
        assert "TRANSFER" in h["run"]

    def test_x_column_exempt(self):
        tex = self._tex("l X",
            "short & \\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} \\\\\n")
        assert scan_squeezed_tables(tex, threshold=20) == []

    def test_p_column_exempt(self):
        tex = self._tex(">{\\raggedright\\arraybackslash}p{4.6cm} X",
            "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} & 缓冲 \\\\\n")
        assert scan_squeezed_tables(tex, threshold=20) == []

    def test_below_threshold_no_hit(self):
        tex = self._tex("l X", "\\texttt{short\\_name} & 缓冲 \\\\\n")
        assert scan_squeezed_tables(tex, threshold=20) == []

    def test_plain_english_outside_texttt_no_hit(self):
        # 不在 \texttt 内的英文长词可走断词，不误报
        tex = self._tex("l X",
            "antidisestablishmentarianismistically & 缓冲 \\\\\n")
        assert scan_squeezed_tables(tex, threshold=20) == []

    def test_cjk_breaks_run_no_hit(self):
        # CJK 是天然断点：长串中夹中文则分段变短，不报
        tex = self._tex("l X",
            "\\texttt{abcdefgh}中文\\texttt{abcdefgh} & 缓冲 \\\\\n")
        assert scan_squeezed_tables(tex, threshold=20) == []

    def test_threshold_zero_returns_empty(self):
        tex = self._tex("l X",
            "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} & 缓冲 \\\\\n")
        assert scan_squeezed_tables(tex, threshold=0) == []

    def test_escaped_ampersand_not_split(self):
        # \\& 不是列分隔符：含 \\& 的长串仍在第 1 列
        tex = self._tex("l X",
            "\\texttt{abc\\&def\\_ghi\\_jkl\\_mno\\_pqr} & 缓冲 \\\\\n")
        hits = scan_squeezed_tables(tex, threshold=15)
        assert len(hits) == 1 and hits[0]["col"] == 1

    def test_escaped_underscore_counts_one_glyph(self):
        # \_ 按 1 字形计：20 个转义下划线串 = 20 字形
        tex = self._tex("l X", "\\texttt{" + "\\_".join(["abcd"] * 5) + "} & x \\\\\n")
        hits = scan_squeezed_tables(tex, threshold=24)
        assert hits and hits[0]["length"] == 24

    def test_cr_column_also_checked(self):
        tex = self._tex("c X", "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET} & x \\\\\n")
        hits = scan_squeezed_tables(tex, threshold=20)
        assert len(hits) == 1 and hits[0]["letter"] == "c"

    def test_codeblock_masked(self):
        # codeblock 内的表格内容是字面文本，不参与扫描（不崩溃、不误报）
        tex = ("\\begin{codeblock}\n"
               "\\begin{tabularx}{\\textwidth}{l X}\n"
               "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} & x \\\\\n"
               "\\end{tabularx}\n"
               "\\end{codeblock}\n")
        assert scan_squeezed_tables(tex, threshold=5) == []
