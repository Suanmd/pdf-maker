# -*- coding: utf-8 -*-
"""扁平布局（单章写作推荐）：第N章.tex 直接在项目根，成品 PDF 落一级目录。

覆盖：scaffold --flat（整书/单章）、chapter SOP 全链路（假编译桩）、
ensure_chapter_skeleton 双布局检测、track/cleanup 的扁平兼容。
"""

import json
from pathlib import Path

import pdfmaker.core.config as cfg
from pdfmaker.commands import chapter as chapter_mod
from pdfmaker.commands import cleanup, scaffold, track
from pdfmaker.core import xelatex as xel_mod
from pdfmaker.core.paths import resolve_material

from conftest import GOOD_CHAPTER, fake_compile_ok, write_chapter


class TestScaffoldFlat:
    def test_init_flat_layout(self, tmp_path):
        root = tmp_path / "book"
        assert scaffold.main([str(root), "--chapters", "2", "--flat"]) == 0
        # 章节直接在项目根，不建目录
        assert (root / "第1章.tex").exists()
        assert (root / "第2章.tex").exists()
        assert not (root / "第1章").exists()
        assert not (root / "第2章").exists()
        # main.tex 的 \input 用扁平路径
        main = (root / "main.tex").read_text(encoding="utf-8")
        assert "\\input{第1章}" in main
        assert "\\input{第1章/第1章}" not in main

    def test_init_default_dir_layout_unchanged(self, tmp_path):
        root = tmp_path / "book"
        assert scaffold.main([str(root), "--chapters", "1"]) == 0
        assert (root / "第1章" / "第1章.tex").exists()
        main = (root / "main.tex").read_text(encoding="utf-8")
        assert "\\input{第1章/第1章}" in main

    def test_chapter_flat(self, tmp_path):
        (tmp_path / "main.tex").write_text("\\documentclass{ctexrep}\n", encoding="utf-8")
        assert scaffold.main(["chapter", "3", "--root", str(tmp_path), "--flat"]) == 0
        assert (tmp_path / "第3章.tex").exists()
        assert not (tmp_path / "第3章").exists()

    def test_chapter_flat_no_overwrite(self, tmp_path):
        (tmp_path / "第3章.tex").write_text("手写内容", encoding="utf-8")
        assert scaffold.main(["chapter", "3", "--root", str(tmp_path), "--flat"]) == 0
        assert (tmp_path / "第3章.tex").read_text(encoding="utf-8") == "手写内容"


class TestChapterSOPFlat:
    def test_full_sop_flat(self, project, monkeypatch):
        """扁平布局走完全流程 SOP：成品 PDF 落在一级目录，中间文件归档到根 _tmp_old/。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        (project / "第1章.tex").write_text(GOOD_CHAPTER, encoding="utf-8")
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        # 成品 PDF 在一级目录（不建 第1章/）
        assert (project / "第1章.pdf").exists()
        assert not (project / "第1章").exists()
        # 中间文件归档到项目根的 _tmp_old/
        assert (project / "_tmp_old" / "_tmp.pdf").exists()
        # track 正常登记（扁平布局下 content_hash 也应记录）
        st = json.loads((project / "materials.json").read_text(encoding="utf-8"))
        assert st["chapters"]["第1章"]["status"] == "unverified"

    def test_sop_flat_autodetect_existing(self, project, monkeypatch):
        """已存在的扁平章节无需 --flat，SOP 自动按扁平布局走。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        monkeypatch.setattr(cfg, "CHAPTER_MIN_CHARS", 0)
        (project / "第1章.tex").write_text(
            "\\chapter{扁平章}\n\\label{cha:c1}\n\n正文。\n", encoding="utf-8")
        rc = chapter_mod.main(["1", "--no-verify"])
        assert rc == 0
        assert (project / "第1章.pdf").exists()
        assert not (project / "第1章").exists()


class TestEnsureSkeletonFlat:
    def test_skips_when_flat_file_exists(self, project):
        (project / "第4章.tex").write_text("手写", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("4", None, True, str(project)) is False
        # 不得生成目录布局的重复文件
        assert not (project / "第4章").exists()

    def test_follows_flat_siblings(self, project, tmp_path):
        # 项目里已有扁平章节 → 自动起稿跟随扁平布局（无需显式 --flat）
        (project / "第1章.tex").write_text("已有", encoding="utf-8")
        md = tmp_path / "素材.md"
        md.write_text("# 章标题\n\n## 节一\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("2", str(md), False, str(project), force_cwd=True) is True
        assert (project / "第2章.tex").exists()
        assert not (project / "第2章").exists()

    def test_flat_flag_forces_flat(self, project, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text("# 章标题\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("5", str(md), False,
                                                   str(project), flat=True,
                                                   force_cwd=True) is True
        assert (project / "第5章.tex").exists()
        assert not (project / "第5章").exists()

    def test_default_dir_layout_without_siblings(self, project, tmp_path):
        md = tmp_path / "素材.md"
        md.write_text("# 章标题\n", encoding="utf-8")
        assert chapter_mod.ensure_chapter_skeleton("5", str(md), False, str(project), force_cwd=True) is True
        assert (project / "第5章" / "第5章.tex").exists()


class TestTrackFlat:
    def test_update_records_hash_and_stale_works(self, project):
        (project / "第1章.tex").write_text("扁平章内容", encoding="utf-8")
        assert track.main(["update", str(project), "第1章", "100", "5", "0"]) == 0
        st = json.loads((project / "materials.json").read_text(encoding="utf-8"))
        # 扁平布局下 content_hash 必须记录到（修复前为 None）
        assert st["chapters"]["第1章"]["content_hash"]
        # stale：未变更 → 0
        assert track.main(["stale", str(project), "第1章"]) == 0
        # 改坏源文件 → stale 报 1
        (project / "第1章.tex").write_text("被改坏", encoding="utf-8")
        assert track.main(["stale", str(project), "第1章"]) == 1

    def test_init_enumerates_flat_chapters(self, project):
        (project / "第1章.tex").write_text("一", encoding="utf-8")
        (project / "第2章.tex").write_text("二", encoding="utf-8")
        assert track.main(["init", str(project)]) == 0
        st = json.loads((project / "materials.json").read_text(encoding="utf-8"))
        assert "第1章" in st["chapters"]
        assert "第2章" in st["chapters"]


class TestCleanupFlat:
    def test_cleanup_flat_archives_to_root(self, project):
        (project / "第1章.tex").write_text("源", encoding="utf-8")
        (project / "_tmp.pdf").write_bytes(b"%PDF-fake")
        (project / "_tmp.tex").write_text("tmp", encoding="utf-8")
        (project / "ch1.tex").write_text("mid", encoding="utf-8")
        assert cleanup.main(["1"]) == 0
        # 成品落一级目录
        assert (project / "第1章.pdf").read_bytes() == b"%PDF-fake"
        # 中间文件归档到根的 _tmp_old/
        assert (project / "_tmp_old" / "_tmp.tex").exists()
        assert (project / "_tmp_old" / "ch1.tex").exists()
        assert not (project / "_tmp.pdf").exists()


class TestResolveMaterial:
    """素材定位约定：多章素材在章节文件夹，扁平单章在项目根。"""

    def test_as_given_path_wins(self, project):
        p = project / "素材-第1章.md"
        p.write_text("# 素材", encoding="utf-8")
        assert resolve_material("素材-第1章.md", "1") == Path("素材-第1章.md")  # 相对进、相对出

    def test_chapter_folder_convention(self, project):
        # 多章约定：素材在 第N章/ 内，裸文件名从项目根也能解析
        ch = project / "第1章"
        ch.mkdir()
        p = ch / "素材-第1章.md"
        p.write_text("# 素材", encoding="utf-8")
        assert resolve_material("素材-第1章.md", "1") == Path("第1章/素材-第1章.md")

    def test_chapter_folder_beats_root(self, project):
        # 两处都有时，显式给定路径（项目根）优先——用户字面意图
        (project / "素材-第1章.md").write_text("根", encoding="utf-8")
        ch = project / "第1章"
        ch.mkdir()
        (ch / "素材-第1章.md").write_text("章内", encoding="utf-8")
        assert resolve_material("素材-第1章.md", "1") == Path("素材-第1章.md")

    def test_missing_returns_as_given(self, project):
        # 找不到时原样返回（由下游 reader/scaffold 报错），不阻断
        assert resolve_material("不存在.md", "1") == Path("不存在.md")

    def test_absolute_path_passthrough(self, project, tmp_path):
        p = tmp_path / "abs.md"
        p.write_text("x", encoding="utf-8")
        assert resolve_material(str(p), "1") == p

    def test_chapter_sop_with_material_in_chapter_folder(self, project, monkeypatch):
        """多章约定端到端：素材在 第1章/ 内，`chapter 1 --material 素材-第1章.md`
        裸文件名自动解析，reader 阅读与 track 登记都指向章内路径。"""
        monkeypatch.setattr(xel_mod, "compile", fake_compile_ok)
        monkeypatch.setattr(cfg, "CHAPTER_MIN_CHARS", 0)
        ch = project / "第1章"
        ch.mkdir()
        (ch / "素材-第1章.md").write_text("# 素材\n\n## 节一\n\n内容\n", encoding="utf-8")
        write_chapter(project, 1, GOOD_CHAPTER)  # 已撰写正文（非占位骨架），否则触发再生早退
        rc = chapter_mod.main(["1", "--material", "素材-第1章.md", "--no-verify"])
        assert rc == 0
        st = json.loads((project / "materials.json").read_text(encoding="utf-8"))
        srcs = st["chapters"]["第1章"]["source_files"]
        assert srcs and srcs[0].endswith("第1章/素材-第1章.md")
        # reader 状态按解析后的路径键控，chunk 数已登记
        assert st["chapters"]["第1章"]["chunks_read_count"] >= 1
