# -*- coding: utf-8 -*-
"""commands.overflow：编译日志体检——阻断信号、代码块/公式降级、vbox 警告。"""

import os

import pytest

from pdfmaker.commands import overflow


CLEAN_LOG = "This is XeTeX, Version 3.141592\nOutput written on main.pdf (5 pages).\n"

OVERFULL_LOG = (
    CLEAN_LOG
    + "Overfull \\hbox (25.3pt too wide) in paragraph at lines 4--5:\n"
)

CH1_WITH_CODEBLOCK = (
    "\\chapter{甲}\n"            # 行 1
    "正文\n"                     # 行 2
    "\\begin{codeblock}\n"       # 行 3
    "code line one\n"            # 行 4
    "code line two\n"            # 行 5
    "\\end{codeblock}\n"         # 行 6
)

CH1_WITH_EQUATION = (
    "\\chapter{甲}\n"            # 行 1
    "正文\n"                     # 行 2
    "\\begin{equation}\n"        # 行 3
    "x = 1\n"                    # 行 4
    "y = 2\n"                    # 行 5
    "\\end{equation}\n"          # 行 6
)


@pytest.fixture
def logdir(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    return tmp_path


def _write(logdir, name, content):
    p = logdir / name
    p.write_text(content, encoding="utf-8")
    return p


class TestOverflowMain:
    def test_clean_log_rc0(self, logdir):
        p = _write(logdir, "_tmp.log", CLEAN_LOG)
        assert overflow.main([str(p)]) == 0

    def test_overfull_blocks(self, logdir):
        _write(logdir, "ch1.tex", "\\chapter{甲}\n正文\n更多\n第四行\n第五行\n")
        p = _write(logdir, "_tmp.log", OVERFULL_LOG)
        assert overflow.main([str(p)]) == 1

    def test_overfull_in_codeblock_downgraded(self, logdir):
        # Overfull 行区间 4--5 完全落在 codeblock（行 3-6）内 → 降级为警告
        _write(logdir, "ch1.tex", CH1_WITH_CODEBLOCK)
        p = _write(logdir, "_tmp.log", OVERFULL_LOG)
        assert overflow.main([str(p)]) == 0

    def test_overfull_in_math_downgraded(self, logdir):
        _write(logdir, "ch1.tex", CH1_WITH_EQUATION)
        p = _write(logdir, "_tmp.log", OVERFULL_LOG)
        assert overflow.main([str(p)]) == 0

    def test_missing_character_blocks(self, logdir):
        p = _write(logdir, "_tmp.log", CLEAN_LOG + "Missing character: There is no σ\n")
        assert overflow.main([str(p)]) == 1

    def test_multiply_defined_blocks(self, logdir):
        p = _write(logdir, "_tmp.log", CLEAN_LOG + "Label `fig:x' multiply-defined.\n")
        assert overflow.main([str(p)]) == 1

    def test_undefined_references_block(self, logdir):
        p = _write(logdir, "_tmp.log",
                   CLEAN_LOG + "LaTeX Warning: There were undefined references.\n")
        assert overflow.main([str(p)]) == 1

    def test_fatal_blocks(self, logdir):
        p = _write(logdir, "_tmp.log", CLEAN_LOG + "! Fatal error occurred.\n")
        assert overflow.main([str(p)]) == 1

    def test_underfull_not_blocking(self, logdir):
        p = _write(logdir, "_tmp.log", CLEAN_LOG + "Underfull \\hbox (badness 10000) in paragraph\n")
        assert overflow.main([str(p)]) == 0

    def test_vbox_overfull_not_blocking(self, logdir):
        p = _write(logdir, "_tmp.log",
                   CLEAN_LOG + "Overfull \\vbox (10.0pt too high) has occurred at lines 3--4\n")
        assert overflow.main([str(p)]) == 0

    def test_missing_log_raises(self, logdir):
        with pytest.raises(SystemExit):
            overflow.main([str(logdir / "不存在.log")])


class TestLogDiscovery:
    def test_auto_find_tmp_log(self, logdir):
        _write(logdir, "_tmp.log", CLEAN_LOG)
        assert overflow.main([]) == 0

    def test_search_up_finds_log_in_parent(self, logdir):
        _write(logdir, "_tmp.log", CLEAN_LOG)
        sub = logdir / "子目录"
        sub.mkdir()
        os.chdir(sub)
        assert overflow.main(["_tmp.log"]) == 0


class TestHelpers:
    def test_codeblock_line_ranges(self):
        assert overflow._codeblock_line_ranges(CH1_WITH_CODEBLOCK) == [(3, 6)]

    def test_math_env_line_ranges(self):
        assert overflow._math_env_line_ranges(CH1_WITH_EQUATION) == [(3, 6)]

    def test_collect_source_texts_skips_tmp_and_main(self, logdir):
        _write(logdir, "ch1.tex", "a")
        _write(logdir, "_tmp.tex", "b")
        _write(logdir, "main.tex", "c")
        _write(logdir, "_tmp.log", CLEAN_LOG)
        names = [p.name for p in overflow._collect_source_texts(logdir / "_tmp.log")]
        assert names == ["ch1.tex"]


class TestSourceMapping:
    """Overfull 源行号映射：内容锚定 / difflib 行对齐 / 表格单元格提示。"""

    def _setup_chapter(self, logdir):
        orig = (
            "\\chapter{测试章}\n"          # 行 1
            "\\section{配置}\n"            # 行 2
            "正文 \\texttt{prepare\\_batch(dataloader, ProxyRLVRWorkflow)} 溢出。\n"  # 行 3
            "\\begin{table}[htbp]\n"       # 行 4
            "\\begin{tabularx}{\\textwidth}{l X}\n"  # 行 5
            "\\toprule\n"                  # 行 6
            "字段 & 说明 \\\\\n"           # 行 7
            "\\midrule\n"                  # 行 8
            "\\texttt{TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE} & 缓冲 \\\\\n"  # 行 9
            "\\bottomrule\n"               # 行 10
            "\\end{tabularx}\n"            # 行 11
            "\\end{table}\n"               # 行 12
        )
        norm = orig.replace(
            "TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_BUCKET\\_MEM\\_SIZE",
            "TRANSFER\\_ENGINE\\_COPY\\_LARGE\\_}\\allowbreak{}\\texttt{BUCKET\\_MEM\\_SIZE",
        )
        _write(logdir, "第2章.tex", orig)
        _write(logdir, "ch2.tex", norm)
        return orig, norm

    def test_content_anchor_maps_to_original_line(self, logdir, capsys):
        self._setup_chapter(logdir)
        log = (
            "This is XeTeX\n(./_tmp.tex\n(./ch2.tex\n"
            "Overfull \\hbox (41.0pt too wide) in paragraph at lines 3--3\n"
            " []\\TU/lmtt/m/n/10.95 prepare_batch(dataloader, ProxyRLVRWorkflow)\n"
            "Output written on _tmp.pdf (1 pages).\n"
        )
        p = _write(logdir, "_tmp.log", log)
        assert overflow.main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "第2章.tex 行 3" in out
        assert "内容锚定" in out

    def test_difflib_fallback_and_table_hint(self, logdir, capsys):
        self._setup_chapter(logdir)
        log = (
            "This is XeTeX\n(./_tmp.tex\n(./ch2.tex\n"
            "Overfull \\hbox (64.1pt too wide) in paragraph at lines 12--12\n"
            " []\n"
            "Output written on _tmp.pdf (1 pages).\n"
        )
        p = _write(logdir, "_tmp.log", log)
        assert overflow.main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "第2章.tex 行 12" in out
        assert "行号对齐" in out
        # 表格候选必须指出具体单元格（第 1 列的 TRANSFER 长串）
        assert "表格候选" in out
        assert "TRANSFER_ENGINE_COPY_LARGE_BUCKET_MEM_SIZE" in out

    def test_unmappable_marks_normalized_lines(self, logdir, capsys):
        # 无任何源文件时：不崩溃，并明确标注「归一化副本行号」
        log = (
            "This is XeTeX\n(./_tmp.tex\n"
            "Overfull \\hbox (10.0pt too wide) in paragraph at lines 9--9\n"
            " []\nOutput written on _tmp.pdf (1 pages).\n"
        )
        p = _write(logdir, "_tmp.log", log)
        assert overflow.main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "归一化副本" in out

    def test_build_layout_anchor_into_project_original(self, logdir, capsys):
        # 整书 _build 布局：锚定应命中项目根 第N章/第N章.tex（而非 _build 归一副本）
        build = logdir / "_build"
        build.mkdir()
        chap = logdir / "第3章"
        chap.mkdir()
        (chap / "第3章.tex").write_text(
            "\\chapter{整书章}\n正文 \\texttt{RemoteHybridDLLMTrainWorker} 长名。\n",
            encoding="utf-8")
        (build / "第3章.tex").write_text(
            "\\begin{adjustbox}{max width=\\textwidth}\n图\n\\end{adjustbox}\n"
            "\\chapter{整书章}\n"
            "正文 \\texttt{RemoteHybridDLLMTrain}\\allowbreak{}\\texttt{Worker} 长名。\n",
            encoding="utf-8")
        log = (
            "This is XeTeX\n(./main.tex\n(./第1章.tex)\n(./第3章.tex\n"
            "Overfull \\hbox (20.6pt too wide) in paragraph at lines 5--5\n"
            " []\\TU/lmtt/m/n/10.95 RemoteHybridDLLMTrainWorker\n"
            "Output written on main.pdf (3 pages).\n"
        )
        p = _write(build, "main.log", log)
        assert overflow.main([str(p)]) == 1
        out = capsys.readouterr().out
        assert "第3章.tex 行 2" in out
        assert "内容锚定" in out
