# -*- coding: utf-8 -*-
"""pdfmaker 核心工具集。

集中存放被多个命令复用的纯函数，确保「路径定位 / 文本统计 / 规范化 /
编译前扫描 / 章节枚举」等逻辑只实现一次、被所有命令以同一方式调用。
"""

from pdfmaker.core.chapters import chapter_range, collect_chapters
from pdfmaker.core.lint import (
    inject_frontmatter_noindent,
    scan_codeblock_nonascii,
    scan_crossref,
    scan_cite_undef,
    scan_frontmatter_tables,
    scan_missing_frontmatter,
    scan_preamble_drift,
    scan_glyphs,
    scan_raw_verbatim,
    scan_table_style,
    scan_table_rules,
    scan_caption_position,
    scan_tikz_amp,
    scan_tikz_badbreak,
    scan_truncated_urls,
    scan_redundant_heading_number,
)
from pdfmaker.core.normalize import normalize_text, url_to_href, wrap_tikz
from pdfmaker.core.paths import (
    find_main_template,
    find_tmp_template,
    mid_name_for,
    resolve_source,
    setup_utf8,
    stem_of,
    workdir_for,
)
from pdfmaker.core.text import (
    char_count,
    chinese_count,
    strip_blocks,
    strip_latex_comments,
    strip_nonbody,
    count_visible_body,
)

__all__ = [
    "setup_utf8",
    "stem_of",
    "resolve_source",
    "mid_name_for",
    "workdir_for",
    "find_tmp_template",
    "find_main_template",
    "strip_blocks",
    "strip_nonbody",
    "count_visible_body",
    "chinese_count",
    "char_count",
    "strip_latex_comments",
    "normalize_text",
    "url_to_href",
    "wrap_tikz",
    "scan_glyphs",
    "scan_truncated_urls",
    "scan_codeblock_nonascii",
    "scan_raw_verbatim",
    "scan_table_style",
    "scan_table_rules",
    "scan_caption_position",
    "scan_tikz_amp",
    "scan_tikz_badbreak",
    "scan_crossref",
    "scan_cite_undef",
    "scan_redundant_heading_number",
    "scan_frontmatter_tables",
    "scan_missing_frontmatter",
    "scan_preamble_drift",
    "inject_frontmatter_noindent",
    "collect_chapters",
    "chapter_range",
]
