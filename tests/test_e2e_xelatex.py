# -*- coding: utf-8 -*-
"""端到端真实编译（需要本机安装 xelatex；未安装时自动 skip）。

与 test_build.py / test_chapter_cmd.py 的假编译桩不同，本文件走真实
xelatex ×2 → overflow → 落盘的完整链路，验证模板与工具链在本机的真实可用性。
"""

import glob
import shutil
from pathlib import Path

import pytest

from pdfmaker.commands import build as build_mod
from pdfmaker.commands import chapter as chapter_mod
from pdfmaker.commands import scaffold

from conftest import GOOD_CHAPTER, write_chapter


def _xelatex_available() -> bool:
    if shutil.which("xelatex"):
        return True
    cands = ["/Library/TeX/texbin/xelatex", "/opt/homebrew/bin/xelatex",
             "/usr/local/bin/xelatex", "/usr/bin/xelatex"]
    cands += glob.glob("/usr/local/texlive/*/bin/*/xelatex")
    cands += glob.glob(str(Path.home() / "Library/TinyTeX/bin/*/xelatex"))
    cands += glob.glob(str(Path.home() / "texlive/*/bin/*/xelatex"))
    return any(Path(c).exists() for c in cands)


pytestmark = pytest.mark.skipif(not _xelatex_available(),
                                reason="本机未安装 xelatex（TeX Live / MacTeX / TinyTeX）")


class TestRealCompile:
    def test_single_chapter_sop_real_xelatex(self, project, monkeypatch):
        """真实跑通单章全流程 SOP（跳过联网验活），产出真实 PDF。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        pdf = project / "第1章" / "第1章.pdf"
        assert pdf.exists() and pdf.stat().st_size > 1000
        assert pdf.read_bytes()[:5] == b"%PDF-"

    def test_build_real_xelatex(self, tmp_path, monkeypatch):
        """真实整书合并：labels → xref → 规范化 → xelatex×2 → overflow → main.pdf。"""
        root = tmp_path / "book"
        assert scaffold.main([str(root), "--chapters", "1", "--title", "真编测试",
                              "--author", "佚名"]) == 0
        rc = build_mod.main([str(root)])
        assert rc == 0
        pdf = root / "main.pdf"
        assert pdf.exists() and pdf.read_bytes()[:5] == b"%PDF-"
        assert not (root / "_build").exists()

    def test_single_chapter_sop_flat_real_xelatex(self, project, monkeypatch):
        """扁平布局真实跑通单章 SOP：章 .tex 在项目根，成品 PDF 落一级目录。"""
        (project / "第1章.tex").write_text(GOOD_CHAPTER, encoding="utf-8")
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        pdf = project / "第1章.pdf"
        assert pdf.exists() and pdf.stat().st_size > 1000
        assert pdf.read_bytes()[:5] == b"%PDF-"
        assert not (project / "第1章").exists()  # 扁平布局不建章目录
