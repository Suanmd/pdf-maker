# -*- coding: utf-8 -*-
"""commands.compile：单章编译一体化（自动定位 xelatex → 两遍编译 → overflow 体检）。"""

from pdfmaker.commands import compile as compile_mod
from pdfmaker.commands import fix as fix_mod
from pdfmaker.core import xelatex as xel_mod

from conftest import GOOD_CHAPTER, fake_compile_fail, fake_compile_ok, write_chapter


class TestCompileCmd:
    def test_compile_ok_and_overflow(self, project, monkeypatch):
        """两遍编译成功 → 自动跑 overflow 体检 → rc 0。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        write_chapter(project, 1, GOOD_CHAPTER)
        # compile 依赖 fix 产出的 _tmp.tex
        assert fix_mod.main(["1"]) == 0
        rc = compile_mod.main(["1"])
        assert rc == 0
        assert (project / "第1章" / "_tmp.pdf").exists()

    def test_missing_tmp_rc2(self, project):
        """未跑 fix（无 _tmp.tex）→ rc 2 + 提示，不崩溃。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        assert compile_mod.main(["1"]) == 2

    def test_missing_chapter_rc2(self, project):
        assert compile_mod.main(["9"]) == 2

    def test_compile_failure_rc1(self, project, monkeypatch):
        """xelatex 失败 → rc 1。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_fail)
        write_chapter(project, 1, GOOD_CHAPTER)
        assert fix_mod.main(["1"]) == 0
        assert compile_mod.main(["1"]) == 1

    def test_no_overflow_skips_check(self, project, monkeypatch):
        """--no-overflow：编译成功即返回 0，不跑体检。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        write_chapter(project, 1, GOOD_CHAPTER)
        assert fix_mod.main(["1"]) == 0
        assert compile_mod.main(["1", "--no-overflow"]) == 0
