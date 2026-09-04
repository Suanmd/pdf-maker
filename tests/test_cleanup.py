# -*- coding: utf-8 -*-
"""commands.cleanup：成品落盘、中间文件归档、归档份数上限。"""

from pathlib import Path

from pdfmaker.commands import cleanup


class TestPruneArchive:
    def test_groups_by_baseline_and_keeps_newest(self, tmp_path):
        d = tmp_path / "_tmp_old"
        d.mkdir()
        names = ["_tmp.tex", "_tmp.1.tex", "_tmp.2.tex", "_tmp.3.tex"]
        for n in names:
            (d / n).write_text("x", encoding="utf-8")
        removed = cleanup._prune_archive(d, max_keep=2)
        # 无索引视为最旧（索引 0），保留索引最大的 2 份
        assert sorted(removed) == ["_tmp.1.tex", "_tmp.tex"]
        assert sorted(p.name for p in d.iterdir()) == ["_tmp.2.tex", "_tmp.3.tex"]

    def test_within_keep_noop(self, tmp_path):
        d = tmp_path / "_tmp_old"
        d.mkdir()
        (d / "_tmp.tex").write_text("x", encoding="utf-8")
        assert cleanup._prune_archive(d, max_keep=10) == []

    def test_keep_zero_disables(self, tmp_path):
        d = tmp_path / "_tmp_old"
        d.mkdir()
        for i in range(15):
            (d / f"_tmp.{i}.tex").write_text("x", encoding="utf-8")
        assert cleanup._prune_archive(d, max_keep=0) == []
        assert len(list(d.iterdir())) == 15

    def test_missing_dir_noop(self, tmp_path):
        assert cleanup._prune_archive(tmp_path / "nope", max_keep=3) == []


class TestCleanupMain:
    def test_full_flow(self, project):
        ch = project / "第1章"
        ch.mkdir()
        (ch / "第1章.tex").write_text("源", encoding="utf-8")
        (ch / "_tmp.pdf").write_bytes(b"%PDF-fake")
        (ch / "_tmp.tex").write_text("tmp", encoding="utf-8")
        (ch / "_tmp.log").write_text("log", encoding="utf-8")
        (ch / "ch1.tex").write_text("mid", encoding="utf-8")

        assert cleanup.main(["1"]) == 0

        # 成品落盘
        assert (ch / "第1章.pdf").read_bytes() == b"%PDF-fake"
        # 源文件保留
        assert (ch / "第1章.tex").exists()
        # 中间文件归档（移动而非删除）
        old = ch / "_tmp_old"
        assert (old / "_tmp.pdf").exists()
        assert (old / "_tmp.tex").exists()
        assert (old / "_tmp.log").exists()
        assert (old / "ch1.tex").exists()
        # 原位已清空
        assert not (ch / "_tmp.pdf").exists()
        assert not (ch / "ch1.tex").exists()

    def test_archive_collision_gets_suffix(self, project):
        ch = project / "第1章"
        ch.mkdir()
        (ch / "第1章.tex").write_text("源", encoding="utf-8")
        (ch / "_tmp.pdf").write_bytes(b"v2")
        old = ch / "_tmp_old"
        old.mkdir()
        (old / "_tmp.pdf").write_bytes(b"v1")
        assert cleanup.main(["1"]) == 0
        assert (old / "_tmp.pdf").read_bytes() == b"v1"      # 旧归档未被覆盖
        assert (old / "_tmp.1.pdf").read_bytes() == b"v2"    # 新归档追加序号

    def test_missing_tmp_pdf_warns_but_rc0(self, project):
        ch = project / "第1章"
        ch.mkdir()
        (ch / "第1章.tex").write_text("源", encoding="utf-8")
        assert cleanup.main(["1"]) == 0
        assert not (ch / "第1章.pdf").exists()

    def test_listing_file_archived(self, project):
        # tcolorbox listings 引擎（codeblock 环境）写出的 _tmp.listing 也应归档
        ch = project / "第1章"
        ch.mkdir()
        (ch / "第1章.tex").write_text("源", encoding="utf-8")
        (ch / "_tmp.pdf").write_bytes(b"%PDF-fake")
        (ch / "_tmp.listing").write_text("listing", encoding="utf-8")
        assert cleanup.main(["1"]) == 0
        assert (ch / "_tmp_old" / "_tmp.listing").exists()
        assert not (ch / "_tmp.listing").exists()
