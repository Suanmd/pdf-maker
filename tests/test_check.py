# -*- coding: utf-8 -*-
"""commands.check：字数门禁（默认告警、--strict 阻断）、排版样式门禁、悬空引用门禁、warning 级预检。"""

from pdfmaker.commands import check
from conftest import GOOD_CHAPTER, write_chapter


class TestEvaluateGate:
    def test_no_gate_always_passes(self):
        ok, _ = check.evaluate_gate(0, 2000, no_gate=True)
        assert ok

    def test_below_min_fails(self):
        ok, msg = check.evaluate_gate(100, 2000)
        assert not ok and "不足" in msg

    def test_above_max_fails_when_max_set(self):
        ok, msg = check.evaluate_gate(9000, 2000, max_chars=6000)
        assert not ok and "超长" in msg

    def test_max_zero_means_unlimited(self):
        ok, _ = check.evaluate_gate(10**9, 2000, max_chars=0)
        assert ok

    def test_boundary_passes(self):
        assert check.evaluate_gate(2000, 2000)[0]


class TestCheckMain:
    def test_good_chapter_rc0(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "0"]) == 0

    def test_word_gate_warns_not_blocks(self, project, capsys):
        """字数不足默认仅 WARN（exit 0），不再强制返工。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "999999"]) == 0
        out = capsys.readouterr().out
        assert "WARN" in out and "仅告警" in out

    def test_word_gate_strict_blocks(self, project, capsys):
        """--strict 恢复硬门禁：字数不足 exit 1。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "999999", "--strict"]) == 1
        assert "FAIL" in capsys.readouterr().out

    def test_no_gate_overrides(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "999999", "--no-gate"]) == 0

    def test_hline_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{tabular}{l l}\n\\hline\na & b\n\\end{tabular}\n"
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_vrule_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{tabular}{l|c}\na & b\n\\end{tabular}\n"
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_missing_booktabs_rules_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{tabular}{l l}\na & b\n\\end{tabular}\n"
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_raw_verbatim_blocked(self, project):
        body = GOOD_CHAPTER + "\n\\begin{verbatim}\ncode\n\\end{verbatim}\n"
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_caption_below_table_blocked(self, project):
        body = GOOD_CHAPTER + (
            "\n\\begin{table}[htbp]\n\\begin{tabular}{l l}\n\\toprule\na & b\n\\bottomrule\n"
            "\\end{tabular}\n\\caption{错位}\n\\end{table}\n"
        )
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_dangling_cite_blocked(self, project):
        body = GOOD_CHAPTER + "\n悬空引用\\cite{c1r99}\n"
        write_chapter(project, 1, body)
        assert check.main(["1", "--min-chars", "0"]) == 1

    def test_glyph_warning_not_blocking(self, project, capsys):
        write_chapter(project, 1, GOOD_CHAPTER + "\n正文含 ≥ 字符\n")
        assert check.main(["1", "--min-chars", "0"]) == 0
        assert "字符风险" in capsys.readouterr().out

    def test_appendix_accepted(self, project):
        write_chapter(project, "附录A", GOOD_CHAPTER)
        assert check.main(["附录A", "--min-chars", "0"]) == 0

    def test_visible_count_mode(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "0", "--count-mode", "visible"]) == 0

    def test_word_gate_warn_message_has_guidance(self, project, capsys):
        """字数不足的 WARN 文案含：缺口字数、lint 提示、--count-mode visible 出口。"""
        write_chapter(project, 1, GOOD_CHAPTER)  # 正文远低于默认 2000 下限
        rc = check.main(["1"])
        assert rc == 0  # 默认仅告警，不阻断
        out = capsys.readouterr().out
        assert "WARN" in out
        assert "还差" in out
        assert "lint" in out
        assert "--count-mode visible" in out

    def test_longrun_warning_not_blocking(self, project, capsys):
        """\texttt 不可断行长串：warning 级预警（exit 0），不阻断。"""
        write_chapter(project, 1, GOOD_CHAPTER + (
            "\n长串示例：\\texttt{GatherAndInnerLoopSPDistributedSampler} 登场。\n"))
        assert check.main(["1", "--min-chars", "0"]) == 0
        out = capsys.readouterr().out
        assert "不可断行长串" in out
        assert "GatherAndInnerLoopSPDistributedSampler" in out

    def test_longrun_clean_chapter_ok(self, project, capsys):
        """无超长串时打印 OK 行。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--min-chars", "0"]) == 0
        assert "不可断行长串" in capsys.readouterr().out

    def test_longrun_disabled_by_config(self, project, capsys, monkeypatch):
        """LONGRUN_WARN_CHARS=0 关闭该预检。"""
        import pdfmaker.core.config as cfg
        monkeypatch.setattr(cfg, "LONGRUN_WARN_CHARS", 0)
        write_chapter(project, 1, GOOD_CHAPTER + (
            "\n长串示例：\\texttt{GatherAndInnerLoopSPDistributedSampler} 登场。\n"))
        assert check.main(["1", "--min-chars", "0"]) == 0
        assert "GatherAndInnerLoopSPDistributedSampler" not in capsys.readouterr().out
