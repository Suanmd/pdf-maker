# -*- coding: utf-8 -*-
"""pdfmaker.core —— 核心工具集。

集中存放被多个命令复用的纯函数，确保「路径定位 / 文本统计 / 规范化 /
编译前扫描 / 章节枚举」等逻辑只实现一次、被所有命令以同一方式调用。
"""

from pdfmaker.core.chapters import chapter_range, chapter_sort_key, collect_chapters
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
from pdfmaker.core.normalize import (
    fix_glyphs,
    normalize_text,
    relax_long_texttt,
    url_to_href,
    wrap_tikz,
)
from pdfmaker.core.paths import (
    find_main_template,
    find_material_nearby,
    find_preamble_shared,
    find_tmp_template,
    looks_like_project_root,
    mid_name_for,
    resolve_material,
    resolve_shared_preamble,
    resolve_source,
    setup_utf8,
    stem_of,
    workdir_for,
)
from pdfmaker.core.text import (
    char_count,
    chinese_count,
    count_visible_body,
    strip_blocks,
    strip_latex_comments,
    strip_nonbody,
)

__all__ = [
    # chapters：章节枚举与排序
    "chapter_range",
    "chapter_sort_key",
    "collect_chapters",
    # lint：编译前静态扫描
    "inject_frontmatter_noindent",
    "scan_caption_position",
    "scan_cite_undef",
    "scan_codeblock_nonascii",
    "scan_crossref",
    "scan_empty_frontmatter",
    "scan_frontmatter_tables",
    "scan_glyphs",
    "scan_missing_frontmatter",
    "scan_preamble_drift",
    "scan_raw_verbatim",
    "scan_redundant_heading_number",
    "scan_squeezed_tables",
    "scan_table_rules",
    "scan_table_style",
    "scan_tikz_amp",
    "scan_tikz_badbreak",
    "scan_truncated_urls",
    "scan_unbreakable_runs",
    # normalize：单一规范化真源
    "fix_glyphs",
    "normalize_text",
    "relax_long_texttt",
    "url_to_href",
    "wrap_tikz",
    # paths：路径定位与模板解析
    "find_main_template",
    "find_material_nearby",
    "find_preamble_shared",
    "find_tmp_template",
    "looks_like_project_root",
    "mid_name_for",
    "resolve_material",
    "resolve_shared_preamble",
    "resolve_source",
    "setup_utf8",
    "stem_of",
    "workdir_for",
    # text：文本统计
    "char_count",
    "chinese_count",
    "count_visible_body",
    "strip_blocks",
    "strip_latex_comments",
    "strip_nonbody",
]
