# -*- coding: utf-8 -*-
"""cli 分发 + commands.lint 快速预检。"""

from pdfmaker import cli
from pdfmaker.commands import lint
from conftest import GOOD_CHAPTER, write_chapter


class TestCli:
    def test_help(self, capsys):
        assert cli.main(["--help"]) == 0
        assert "pdfmaker" in capsys.readouterr().out

    def test_no_args_shows_help(self):
        assert cli.main([]) == 0

    def test_version(self, capsys):
        assert cli.main(["--version"]) == 0
        assert "pdfmaker" in capsys.readouterr().out

    def test_unknown_command_rc2(self, capsys):
        assert cli.main(["不存在的命令"]) == 2

    def test_all_subcommands_registered(self):
        for name in ("fix", "check", "balance", "lint", "overflow", "xref",
                     "verify", "build", "chapter", "cleanup", "labels",
                     "reader", "track", "scaffold"):
            assert name in cli._SUBCOMMANDS


class TestLintCmd:
    def test_always_rc0_on_good_chapter(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert lint.main(["1"]) == 0

    def test_always_rc0_even_with_violations(self, project):
        # lint 是提示级：即便存在阻断级问题也 exit 0
        write_chapter(project, 1, GOOD_CHAPTER + "\n\\begin{verbatim}\nx\n\\end{verbatim}\n")
        assert lint.main(["1"]) == 0

    def test_missing_chapter_rc2(self, project):
        assert lint.main(["9"]) == 2
