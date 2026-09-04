# -*- coding: utf-8 -*-
"""pdfmaker.templates —— 内置 LaTeX 模板资源包。

包含整书主控模板（main.tex）、单章编译 preamble 模板（_tmp.tex）、共用补丁片段
（_preamble_shared.tex）与章节阅读笔记模板（chapter_init_notes_template.md）。
这些模板以包数据形式随 pdfmaker 分发，由 ``pdfmaker.core.paths`` 的
``find_main_template()`` / ``find_tmp_template()`` / ``find_preamble_shared()``
从包内资源唯一定位，缺失时抛出 ``SystemExit``。
"""
