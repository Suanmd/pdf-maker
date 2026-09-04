# -*- coding: utf-8 -*-
"""规整与加固的回归测试：锁定重构面与修复点的行为。

覆盖点：
- core/__init__.py 导出清单完整且可导入（含补齐的公共函数）；
- core/lint.py 的 _iter_tikz_nodes 共享迭代器与 _INLINE_MATH_RE 抗指数回溯；
- commands/overflow.py 的 find_log / _search_up 日志发现；
- cli.py 子命令分发表完整；
- scaffold 骨架对任意章数书稿 xref-clean；
- 全部扫描器在对抗性语料上有界完成；
- core/watchdog.py 扫描看门狗的超时阻断与配置覆盖。
"""

import re
import time
from pathlib import Path

import pytest

import pdfmaker.core as core
import pdfmaker.core.config as cfg
from pdfmaker.cli import _SUBCOMMANDS
from pdfmaker.cli import main as cli_main
from pdfmaker.commands import check, overflow, scaffold, xref
from pdfmaker.core import lint as core_lint
from pdfmaker.core.lint import _mask_math, scan_glyphs
from pdfmaker.core.watchdog import ScanTimeoutError, scan_watchdog

from conftest import GOOD_CHAPTER, write_chapter


class TestCoreExports:
    def test_all_exports_importable(self):
        for name in core.__all__:
            assert callable(getattr(core, name)), f"core.{name} 不可调用"

    def test_new_exports_present(self):
        # 公共函数导出清单
        for name in ("chapter_sort_key", "fix_glyphs",
                     "find_preamble_shared", "resolve_shared_preamble"):
            assert name in core.__all__
            assert callable(getattr(core, name))

    def test_no_duplicate_exports(self):
        assert len(core.__all__) == len(set(core.__all__))


class TestIterTikzNodes:
    def test_yields_node_text_and_opts(self):
        tex = (r"\begin{tikzpicture}" + "\n"
               r"\node[draw, align=center] (a) {你好\\世界};" + "\n"
               r"\end{tikzpicture}")
        nodes = list(core_lint._iter_tikz_nodes(tex))
        assert len(nodes) == 1
        bstart, nstart, block, opts, node_text = nodes[0]
        assert "align=center" in opts
        assert node_text == "你好\\\\世界"

    def test_skips_coordinate_and_nested_option_groups(self):
        tex = (r"\begin{tikzpicture}" + "\n"
               r"\node[box/.style={draw}, box] at (0,0) {文本};" + "\n"
               r"\end{tikzpicture}")
        nodes = list(core_lint._iter_tikz_nodes(tex))
        assert len(nodes) == 1
        assert nodes[0][4] == "文本"

    def test_escaped_brace_in_node_text(self):
        tex = (r"\begin{tikzpicture}" + "\n"
               r"\node (a) {foo \} bar};" + "\n"
               r"\end{tikzpicture}")
        nodes = list(core_lint._iter_tikz_nodes(tex))
        assert len(nodes) == 1
        assert nodes[0][4] == "foo \\} bar"

    def test_no_tikz_yields_nothing(self):
        assert list(core_lint._iter_tikz_nodes("纯正文，没有图。")) == []

    def test_badbreak_and_amp_share_iterator(self):
        # 同一节点同时触发两种扫描时，两者报告的行号一致（共享解析逻辑）
        tex = ("\\begin{tikzpicture}\n"
               "\\node (a) {甲\\\\乙 & 丙};\n"
               "\\end{tikzpicture}\n")
        bad = core_lint.scan_tikz_badbreak(tex)
        amp = core_lint.scan_tikz_amp(tex)
        assert len(bad) == 1 and len(amp) == 1
        assert bad[0]["line"] == amp[0]["line"] == 2


class TestOverflowLogDiscovery:
    def test_log_names_constant(self):
        assert overflow.LOG_NAMES == ("_tmp.log", "main.log", "book.log")

    def test_search_up_walks_ancestors(self, tmp_path, monkeypatch):
        deep = tmp_path / "a" / "b" / "c"
        deep.mkdir(parents=True)
        (tmp_path / "a" / "_tmp.log").write_text("x", encoding="utf-8")
        monkeypatch.chdir(deep)
        assert overflow._search_up("_tmp.log") == tmp_path / "a" / "_tmp.log"

    def test_search_up_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert overflow._search_up("不存在.log") is None

    def test_find_log_prefers_cwd(self, tmp_path, monkeypatch):
        (tmp_path / "main.log").write_text("x", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert overflow.find_log() == tmp_path / "main.log"


class TestCliDispatch:
    def test_help_and_version(self, capsys):
        assert cli_main(["--help"]) == 0
        assert cli_main(["--version"]) == 0
        out = capsys.readouterr().out
        assert "pdfmaker" in out

    def test_unknown_command_rc2(self):
        assert cli_main(["不存在的命令"]) == 2

    def test_subcommand_table_complete(self):
        expected = {"fix", "check", "balance", "lint", "compile", "overflow", "xref",
                    "verify", "build", "chapter", "cleanup", "labels",
                    "reader", "track", "scaffold"}
        assert set(_SUBCOMMANDS) == expected
        for mod in _SUBCOMMANDS.values():
            assert callable(mod.main)


class TestScaffoldSkeletonXrefClean:
    """脚手架骨架不得含会触发自家 xref 门禁的盲写章号（历史修复回归）。"""

    def test_skeleton_has_no_hardcoded_chapter_refs(self):
        tex = scaffold.build_chapter_skeleton(1)
        # 骨架文本里不允许出现「第~N 章」式硬编码跨章引用（N 为具体数字）
        assert not re.search(r"第~\d+[~ ]*章", tex), "骨架含盲写章号，会触发 xref 越界阻断"

    def test_skeleton_passes_xref_in_single_chapter_book(self, tmp_path, monkeypatch):
        root = tmp_path / "book"
        root.mkdir()
        monkeypatch.chdir(root)
        scaffold.write_chapter(1, root=str(root))
        assert xref.main(["."]) == 0


class TestInlineMathRegexNoBacktracking:
    """$...$ 掩码正则不得指数回溯（历史事故：裸 $ + 大量反斜杠曾挂死 check）。"""

    def test_bare_dollar_followed_by_backslashes_no_hang(self):
        # 裸 $（# 前缀，非转义）+ 5000 个反斜杠序列：修复前 2^N 爆炸，修复后线性
        s = "#$ARGUMENTS " + r"\href{x}" * 5000
        t0 = time.time()
        masked = _mask_math(s)
        assert time.time() - t0 < 5, "mask_math 在裸 $ + 反斜杠序列上挂起"
        assert len(masked) == len(s)  # 掩码保持等长

    def test_inline_math_semantics_unchanged(self):
        # 正常行内数学仍被掩码（σ 在数学模式内不报缺字）
        assert scan_glyphs("正文 $\\sigma \\to \\beta$ 结束") == []
        # 正文裸 σ 仍报警
        assert len(scan_glyphs("正文裸用 σ 字符")) == 1


class TestAdversarialScanCorpus:
    """对抗性语料：所有扫描器在恶意输入上必须有界完成（长效护栏）。

    每条语料针对一类历史/潜在病理：未闭合定界符、密集反斜杠、未闭合括号、
    超长行。任何扫描器在这类输入上挂起都属于回归。
    """

    CORPUS = {
        # 未闭合裸 $ + 密集反斜杠（本次挂死的原案）
        "unclosed_dollar": "#$X " + r"\href{a}{b}" * 2000,
        # 未闭合 \begin 环境
        "unclosed_begin": "\\begin{tabularx}" + "a & b \\\\\n" * 2000,
        # 未闭合 tikz 节点大括号
        "unclosed_brace": "\\begin{tikzpicture}\\node (a) {文本" + "x" * 5000,
        # 密集转义美元（合法但易诱发歧义）
        "escaped_dollars": r"\$" * 5000,
        # 超长单行（10 万字符无换行）
        "long_line": "字" * 100000,
    }

    @pytest.mark.parametrize("name", sorted(CORPUS))
    def test_all_scanners_bounded(self, name):
        text = self.CORPUS[name]
        scanners = [n for n in dir(core) if n.startswith("scan_")]
        assert scanners, "core 应导出 scan_* 扫描器"
        t0 = time.time()
        for sname in scanners:
            fn = getattr(core, sname)
            if sname == "scan_preamble_drift":
                fn(text, text)  # 双参数扫描器：main 文本 + shared 文本
            else:
                fn(text)
        elapsed = time.time() - t0
        assert elapsed < 10, f"扫描器在对抗语料 {name} 上耗时 {elapsed:.1f}s（疑似回溯）"


class TestScanWatchdog:
    """扫描看门狗：超时阻断、快速放行、退出后定时器解除。"""

    def test_fires_on_slow_block(self):
        with pytest.raises(ScanTimeoutError, match="slow-step"):
            with scan_watchdog(0.1, "slow-step"):
                time.sleep(5)

    def test_passes_fast_block(self):
        with scan_watchdog(30, "fast-step"):
            pass  # 立即完成，不触发

    def test_timer_disarmed_after_exit(self):
        with scan_watchdog(0.2, "done-step"):
            pass
        time.sleep(0.4)  # 退出后定时器已解除，不应再触发
        # 若定时器未解除，此处会抛 ScanTimeoutError 导致测试失败

    def test_check_times_out_as_blocking(self, project, monkeypatch):
        # 确定性超时：时限压到 1ms，并把扫描路径上的 scan_glyphs 换成 50ms 慢函数
        # → 必然触发看门狗 → check 应 exit 1 阻断。
        # 旧写法只压时限：小章节在快机器上全部扫描可在 1ms 内完成，不构成超时，
        # 测试因此偶发失败（竞态）；本例把「超时」变成确定性事件。
        import time as _time

        monkeypatch.setattr(cfg, "SCAN_TIMEOUT", 0.001)
        monkeypatch.setattr(
            "pdfmaker.commands.check.scan_glyphs",
            lambda text: (_time.sleep(0.05), [])[1],
        )
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1"]) == 1

    def test_check_normal_within_default_timeout(self, project):
        # 默认 30s 时限下正常章节应通过（GOOD_CHAPTER 字数不足会 exit 1，
        # 故用 --no-gate 关闭字数门禁，只验证看门狗不误伤）
        write_chapter(project, 1, GOOD_CHAPTER)
        assert check.main(["1", "--no-gate"]) == 0

    def test_scan_timeout_env_override(self, monkeypatch):
        # 环境变量覆盖路径（_env_float 读取），不 reload 模块以免污染全局状态
        monkeypatch.setenv("PDFMAKER_SCAN_TIMEOUT", "45.5")
        assert cfg._env_float("PDFMAKER_SCAN_TIMEOUT", 30.0) == 45.5

    def test_scan_timeout_toml_override(self, monkeypatch):
        # toml 覆盖路径：PROJECT_CONFIG + apply_project_config
        monkeypatch.setattr(cfg, "SCAN_TIMEOUT", 30.0)
        monkeypatch.setitem(cfg.PROJECT_CONFIG, "scan_timeout", 12.5)
        cfg.apply_project_config()
        assert cfg.SCAN_TIMEOUT == 12.5
