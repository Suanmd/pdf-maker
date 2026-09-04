# -*- coding: utf-8 -*-
"""commands.chapter：单章全流程 SOP 编排（xelatex 用假编译桩替换）。"""

import json

import pytest

import pdfmaker.core.config as cfg
from pdfmaker.commands import chapter as chapter_mod
from pdfmaker.commands import scaffold
from pdfmaker.core import xelatex as xel_mod

from conftest import GOOD_CHAPTER, fake_compile_ok, write_chapter


class TestChapterSOP:
    def test_full_sop_no_verify(self, project, monkeypatch):
        """已撰写正文的章应能无阻断走完全流程 SOP（未撰写骨架会被骨架守卫阻断）。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        write_chapter(project, 1, GOOD_CHAPTER)
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        # 成品落盘
        assert (project / "第1章" / "第1章.pdf").exists()
        # 中间文件已归档
        assert (project / "第1章" / "_tmp_old" / "_tmp.pdf").exists()
        # track 登记为 unverified（--no-verify 显式跳过，绝不谎报已验活）
        st = json.loads((project / "materials.json").read_text(encoding="utf-8"))
        assert st["chapters"]["第1章"]["status"] == "unverified"

    def test_sop_aborts_on_style_violation(self, project, monkeypatch):
        """check 阻断（裸 \\hline） → 流程中止，不会走到编译。"""
        compiled = []

        def spy(xelatex, *args, cwd=None, quiet=False):
            compiled.append(1)
            return fake_compile_ok(xelatex, *args, cwd=cwd)

        monkeypatch.setattr(xel_mod, "compile", spy)
        write_chapter(project, 1,
                      GOOD_CHAPTER + "\n\\begin{tabular}{l l}\n\\hline\na & b\n\\end{tabular}\n")
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 1
        assert compiled == []  # xelatex 未被调用

    def test_missing_chapter_rc2(self, project):
        assert chapter_mod.main(["9", "--no-verify"]) == 2


class TestEnsureChapterSkeleton:
    def test_generates_when_missing_with_material(self, project, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text("# 章标题\n\n## 节一\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("4", str(md), False, str(project), force_cwd=True) is True
        assert (project / "第4章" / "第4章.tex").exists()

    def test_skips_existing(self, project):
        write_chapter(project, 4, "手写")
        assert chapter_mod.ensure_chapter_skeleton("4", None, True, str(project)) is False

    def test_skips_without_material_and_flag(self, project):
        assert chapter_mod.ensure_chapter_skeleton("4", None, False, str(project)) is False

    def test_skips_non_numeric(self, project):
        assert chapter_mod.ensure_chapter_skeleton("附录A", None, True, str(project)) is False


class TestPlaceholderRegen:
    """占位骨架再生：整书初始化的「未命名章标题」占位可被 --material 富骨架替换。"""

    def test_untouched_placeholder_regenerated_with_material(self, project, tmp_path):
        """整书初始化落下的占位骨架 + --material → 再生为素材富骨架。"""
        scaffold._cmd_init([str(project), "--chapters", "1"])
        old = (project / "第1章" / "第1章.tex").read_text(encoding="utf-8")
        assert "\\chapter{未命名章标题}" in old
        md = tmp_path / "素材-第1章.md"
        md.write_text("# 真实章标题\n\n## 节一\n\nhttps://example.com/a\n",
                      encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("1", str(md), False, str(project)) is True
        new = (project / "第1章" / "第1章.tex").read_text(encoding="utf-8")
        assert "\\chapter{真实章标题}" in new
        assert "\\section{节一}" in new
        assert "https://example.com/a" in new

    def test_edited_chapter_never_overwritten(self, project, tmp_path):
        """作者已动笔（非占位骨架）→ 绝不覆盖。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("1", str(md), False, str(project)) is False
        assert "测试章" in (project / "第1章" / "第1章.tex").read_text(encoding="utf-8")


class TestCwdGuard:
    """CWD 守卫：在「不像书稿项目根」的目录拒绝创建章骨架，--force-cwd 显式豁免。"""

    def test_bare_dir_refused(self, project):
        """裸目录（无 main.tex/章节结构）创建骨架 → SystemExit(2)，不产生文件。"""
        with pytest.raises(SystemExit) as e:
            chapter_mod.ensure_chapter_skeleton("3", None, True, str(project))
        assert e.value.code == 2
        assert not (project / "第3章").exists()

    def test_bare_dir_refused_with_hint(self, tmp_path, capsys):
        """裸目录拒绝创建；素材在一级子目录可定位时，报错附 cd 线索。"""
        outer = tmp_path / "outer"          # 裸目录（无 main.tex / 章节结构）
        outer.mkdir()
        book = outer / "realbook"           # 真正的书稿在子目录里
        (book / "第1章").mkdir(parents=True)
        (book / "第1章" / "素材-第1章.md").write_text("# 素材\n", encoding="utf-8")
        with pytest.raises(SystemExit) as e:
            chapter_mod.ensure_chapter_skeleton(
                "1", "素材-第1章.md", False, str(outer))
        assert e.value.code == 2
        out = capsys.readouterr().err
        assert "不像书稿项目根" in out
        assert "realbook" in out            # 下探线索指出了真正的项目目录
        assert not (outer / "第1章").exists()

    def test_force_cwd_allows(self, project, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton(
            "3", str(md), False, str(project), force_cwd=True) is True
        assert (project / "第3章" / "第3章.tex").exists()

    def test_project_root_passes(self, project, tmp_path):
        """含 main.tex 的目录正常放行（无需豁免）。"""
        (project / "main.tex").write_text("\\documentclass{ctexrep}\n", encoding="utf-8")
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("3", str(md), False, str(project)) is True


class TestMaterialNearbyHint:
    """素材缺失诊断：裸文件名找不到时下探一级子目录，给出「你可能想 cd 到 X」提示。"""

    def test_missing_material_subdir_hint(self, tmp_path, monkeypatch, capsys):
        """chapter --material 裸文件名找不到时，下探子目录并给 cd 提示（rc 2）。"""
        outer = tmp_path / "outer"
        outer.mkdir()
        monkeypatch.chdir(outer)
        book = outer / "book"
        (book / "第1章").mkdir(parents=True)
        (book / "第1章" / "素材-第1章.md").write_text("# 素材\n", encoding="utf-8")
        rc = chapter_mod.main(["1", "--material", "素材-第1章.md"])
        assert rc == 2
        assert "book" in capsys.readouterr().err

    def test_existing_material_unaffected(self, project, tmp_path, capsys):
        """素材正常存在时不产生「素材不存在」误报（章缺失则自动起稿 + 早退）。"""
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n", encoding="utf-8")
        (project / "main.tex").write_text("\\documentclass{ctexrep}\n", encoding="utf-8")
        rc = chapter_mod.main(["9", "--material", str(md)])
        assert rc == 0  # 自动起稿 + 素材阅读 + 早退
        assert "素材不存在" not in capsys.readouterr().err


class TestRegenEarlyExit:
    """骨架再生后早退：再生占位骨架 + 素材阅读后直接引导撰写并 exit 0，不空跑后续步骤。"""

    def test_regen_exits_before_fix(self, project, tmp_path, capsys):
        """占位骨架再生 + 素材阅读后早退：rc 0、有引导文案、未跑 fix（无 chN.tex）。"""
        scaffold._cmd_init([str(project), "--chapters", "1"])
        md = tmp_path / "素材-第1章.md"
        md.write_text("# 早退测试章\n\n## 节一\n", encoding="utf-8")
        rc = chapter_mod.main(["1", "--material", str(md)])
        assert rc == 0
        out = capsys.readouterr().out
        assert "素材富骨架已就绪" in out
        tex = (project / "第1章" / "第1章.tex").read_text(encoding="utf-8")
        assert "\\chapter{早退测试章}" in tex          # 骨架已被素材再生
        assert not (project / "第1章" / "ch1.tex").exists()  # fix 未运行

    def test_written_chapter_proceeds(self, project, tmp_path, monkeypatch):
        """已撰写正文的章不受早退影响（fix 正常执行）。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        monkeypatch.setattr(cfg, "CHAPTER_MIN_CHARS", 0)
        write_chapter(project, 1, GOOD_CHAPTER)
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        assert (project / "第1章" / "第1章.pdf").exists()
