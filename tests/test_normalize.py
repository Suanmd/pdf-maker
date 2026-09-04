# -*- coding: utf-8 -*-
"""core.normalize：URL → href 规范化、TikZ 图宽上限、字形自动修、长 \\texttt 拆词、幂等性。"""

from pdfmaker.core.normalize import (
    fix_glyphs,
    normalize_text,
    relax_long_texttt,
    url_to_href,
    wrap_tikz,
)


class TestUrlToHref:
    def test_basic(self):
        out = url_to_href(r"\url{https://example.com}")
        assert out == r"\href{https://example.com}{https://example.com}"

    def test_display_escapes_special_chars(self):
        out = url_to_href(r"\url{https://a.com/x_y?a=b&c=d#e}")
        assert r"\href{https://a.com/x_y?a=b&c=d#e}" in out
        # 显示文本中的 _ & # 必须转义
        assert r"x\_y" in out and r"b\&c" in out and r"\#e" in out

    def test_display_escapes_tilde_and_caret(self):
        out = url_to_href(r"\url{https://a.com/~user/v^2}")
        assert r"\textasciitilde{}" in out
        assert r"\textasciicircum{}" in out

    def test_percent_decoded_in_display_but_raw_in_target(self):
        out = url_to_href(r"\url{https://a.com/%7Euser}")
        assert out.startswith(r"\href{https://a.com/%7Euser}")
        assert r"\textasciitilde{}user" in out

    def test_idempotent(self):
        once = url_to_href(r"\url{https://example.com/x_y}")
        assert url_to_href(once) == once

    def test_existing_href_untouched(self):
        s = r"\href{https://a.com}{已有}"
        assert url_to_href(s) == s


class TestWrapTikz:
    def test_wraps_bare_tikz(self):
        out = wrap_tikz(r"\begin{tikzpicture}\node{a};\end{tikzpicture}")
        assert r"\begin{adjustbox}{max width=\textwidth}" in out
        assert r"\end{adjustbox}" in out

    def test_idempotent(self):
        once = wrap_tikz(r"\begin{tikzpicture}\node{a};\end{tikzpicture}")
        assert wrap_tikz(once) == once
        assert once.count(r"\begin{adjustbox}") == 1

    def test_skips_resizebox_prewrapped(self):
        s = r"\resizebox{\textwidth}{!}{\begin{tikzpicture}\node{a};\end{tikzpicture}}"
        assert wrap_tikz(s) == s

    def test_skips_adjustbox_prewrapped(self):
        s = r"\begin{adjustbox}{max width=\textwidth}" + "\n" \
            + r"\begin{tikzpicture}\node{a};\end{tikzpicture}" + "\n" + r"\end{adjustbox}"
        assert wrap_tikz(s) == s

    def test_multiple_tikz_all_wrapped(self):
        s = (r"\begin{tikzpicture}\node{a};\end{tikzpicture}" + "\n正文\n"
             + r"\begin{tikzpicture}\node{b};\end{tikzpicture}")
        out = wrap_tikz(s)
        assert out.count(r"\begin{adjustbox}") == 2

    def test_unclosed_tikz_left_asis(self):
        s = r"\begin{tikzpicture}\node{a};"
        assert wrap_tikz(s) == s


class TestFixGlyphs:
    def test_text_mode_wraps_math(self):
        assert fix_glyphs("增长 ≥ 5") == r"增长 $\ge$ 5"

    def test_math_mode_bare_command(self):
        assert fix_glyphs("$x \\ge 1$ ≥") == "$x \\ge 1$ $\\ge$"

    def test_inline_math_parens(self):
        assert fix_glyphs(r"\(x ≥ 1\)") == r"\(x \ge 1\)"

    def test_display_math_brackets(self):
        assert fix_glyphs(r"\[x ≤ 2\]") == r"\[x \le 2\]"

    def test_greek_letters(self):
        assert fix_glyphs("参数 σ 与 π") == r"参数 $\sigma$ 与 $\pi$"

    def test_circled_numbers(self):
        assert fix_glyphs("步骤①然后②") == "步骤(1)然后(2)"
        assert fix_glyphs("⑩") == "(10)"

    def test_celsius(self):
        assert fix_glyphs("25℃") == r"25$^\circ\mathrm{C}$"

    def test_protected_url_untouched(self):
        s = r"\url{https://a.com/≥}"  # URL 内的字符不转换
        assert fix_glyphs(s) == s

    def test_protected_href_untouched(self):
        s = r"\href{https://a.com}{≥≥}"
        assert fix_glyphs(s) == s

    def test_protected_verbatim_untouched(self):
        s = "\\begin{verbatim}\n≥ ≤\n\\end{verbatim}\n正文 ≥"
        out = fix_glyphs(s)
        assert "≥ ≤" in out  # verbatim 内原样
        assert out.endswith(r"正文 $\ge$")

    def test_protected_codeblock_untouched(self):
        s = "\\begin{codeblock}\n# ±3σ\n\\end{codeblock}"
        assert fix_glyphs(s) == s

    def test_idempotent(self):
        once = fix_glyphs("α ≥ ①")
        assert fix_glyphs(once) == once

    def test_no_glyph_fastpath(self):
        s = "纯 ASCII 与中文正文 $x \\ge 1$"
        assert fix_glyphs(s) == s

    def test_double_backslash_not_confused_with_math(self):
        # \\ 后的 $ 不应当作转义美元；表格换行后的数学模式切换仍正确
        s = "a \\\\ b $≥$"
        out = fix_glyphs(s)
        assert r"\ge" in out  # 数学模式内裸命令
        assert "$" in out


class TestNormalizeText:
    def test_composition_order(self):
        s = r"\url{https://a.com/x} ≥ \begin{tikzpicture}\node{a};\end{tikzpicture}"
        out = normalize_text(s)
        assert r"\href{https://a.com/x}" in out
        assert r"$\ge$" in out
        assert r"\begin{adjustbox}" in out

    def test_idempotent(self):
        s = r"\url{https://a.com/x_y} ≥ ① \begin{tikzpicture}\node{a};\end{tikzpicture}"
        once = normalize_text(s)
        assert normalize_text(once) == once

    def test_ascii_unchanged(self):
        s = "\\chapter{你好}\nplain ASCII text\n"
        assert normalize_text(s) == s


class TestRelaxLongTexttt:
    LONG = r"\texttt{rollout.max\_head\_offpolicyness}"

    def test_long_texttt_gets_allowbreak_at_separators(self):
        out = relax_long_texttt(self.LONG, threshold=20)
        assert r"\allowbreak{}" in out
        # 分隔符（. 与 \_）后都应有断点
        assert r"rollout.\allowbreak{}" in out
        assert r"\texttt{" in out  # 命令本身保留

    def test_short_texttt_unchanged(self):
        s = r"短 \texttt{short} 不变"
        assert relax_long_texttt(s, threshold=20) == s

    def test_idempotent(self):
        once = relax_long_texttt(self.LONG, threshold=20)
        assert relax_long_texttt(once, threshold=20) == once

    def test_joint_texttt_slash_gets_break(self):
        s = r"\texttt{aa}/\texttt{bb}"
        out = relax_long_texttt(s, threshold=20)
        assert r"/\allowbreak{}\texttt{" in out
        # 幂等：二次不再重复插入
        assert relax_long_texttt(out, threshold=20) == out

    def test_codeblock_protected(self):
        s = ("\\begin{codeblock}\n"
             r'x = "texttt{rollout.max\_head\_offpolicyness}"' + "\n"
             "\\end{codeblock}")
        assert relax_long_texttt(s, threshold=5) == s

    def test_url_protected(self):
        # \\url{} 内容是原始 URL，绝不能插入断点
        s = r"\url{https://a.com/rollout.max_head_offpolicyness_long_path}"
        assert relax_long_texttt(s, threshold=5) == s

    def test_href_display_texttt_gets_relaxed_but_url_untouched(self):
        # \\href 的显示文本是排版内容：其中的长 \\texttt 拆词是特性（同样会溢出）；
        # 但 URL 目标部分绝不能被改动
        s = r"\href{https://a.com/x_y}{\texttt{rollout.max\_head\_offpolicyness}}"
        out = relax_long_texttt(s, threshold=5)
        assert r"\href{https://a.com/x_y}" in out
        assert r"\allowbreak{}" in out

    def test_threshold_zero_disables(self):
        assert relax_long_texttt(self.LONG, threshold=0) == self.LONG

    def test_content_with_braces_skipped(self):
        s = r"\texttt{foo{bar}baz\_qux\_quux\_corge\_grault}"
        # 含嵌套花括号的内容跳过拆词（结构复杂，不冒险），但不应崩溃
        out = relax_long_texttt(s, threshold=5)
        assert s == out

    def test_normalize_text_includes_relax(self):
        out = normalize_text(r"\texttt{actor.hybrid\_engine.wrap\_policy}")
        assert r"\allowbreak{}" in out

    def test_normalize_text_relax_idempotent(self):
        s = r"\texttt{actor.hybrid\_engine.wrap\_policy} 与 \texttt{a}/\texttt{b}"
        once = normalize_text(s)
        assert normalize_text(once) == once

    def test_unclosed_texttt_no_crash(self):
        s = r"未闭合 \texttt{rollout.max\_head\_offpolicyness"
        out = relax_long_texttt(s, threshold=5)
        assert isinstance(out, str)  # 不崩溃即合格（结构错误由其它门禁报告）
