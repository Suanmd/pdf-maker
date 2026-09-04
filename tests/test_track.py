# -*- coding: utf-8 -*-
"""commands.track：materials.json 生命周期（init/show/check/update/stale/bib-audit）。"""

import json

from pdfmaker.commands import track
from conftest import GOOD_CHAPTER, write_chapter


def _materials(project):
    return json.loads((project / "materials.json").read_text(encoding="utf-8"))


class TestInit:
    def test_init_creates_entries_from_dirs(self, project):
        write_chapter(project, 1, "a")
        write_chapter(project, 2, "b")
        write_chapter(project, "附录A", "c")
        assert track.main(["init", str(project)]) == 0
        st = _materials(project)
        assert sorted(st["chapters"]) == ["第1章", "第2章", "附录A"]
        assert st["chapters"]["第1章"]["status"] == "pending"

    def test_init_preserves_existing(self, project):
        write_chapter(project, 1, "a")
        track.main(["update", str(project), "第1章", "10", "2", "1"])
        before = _materials(project)["chapters"]["第1章"]["status"]
        track.main(["init", str(project)])
        assert _materials(project)["chapters"]["第1章"]["status"] == before


class TestUpdateAndCheck:
    def test_check_pending_rc2(self, project):
        write_chapter(project, 1, "a")
        track.main(["init", str(project)])
        assert track.main(["check", str(project), "第1章"]) == 2

    def test_update_verified_then_check_rc0(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        assert track.main(["update", str(project), "第1章", "100", "20", "3"]) == 0
        assert track.main(["check", str(project), "第1章"]) == 0
        st = _materials(project)
        assert st["chapters"]["第1章"]["status"] == "verified"
        assert st["chapters"]["第1章"]["content_hash"]  # 源指纹已记录

    def test_update_unverified(self, project):
        write_chapter(project, 1, "a")
        track.main(["update", str(project), "第1章", "1", "1", "0", "--unverified"])
        st = _materials(project)
        assert st["chapters"]["第1章"]["status"] == "unverified"
        assert st["chapters"]["第1章"]["verified"] is None
        assert track.main(["check", str(project), "第1章"]) == 2

    def test_update_pending_verify(self, project):
        write_chapter(project, 1, "a")
        track.main(["update", str(project), "第1章", "1", "1", "0", "--pending-verify"])
        assert _materials(project)["chapters"]["第1章"]["status"] == "pending-verify"
        assert track.main(["check", str(project), "第1章"]) == 2

    def test_update_auto_inits_missing_materials(self, project):
        write_chapter(project, 3, "a")
        assert not (project / "materials.json").exists()
        assert track.main(["update", str(project), "第3章", "1", "1", "0"]) == 0
        assert (project / "materials.json").exists()

    def test_update_unknown_chapter_registered(self, project):
        write_chapter(project, 1, "a")
        track.main(["init", str(project)])
        track.main(["update", str(project), "第7章", "1", "1", "0"])
        assert "第7章" in _materials(project)["chapters"]

    def test_material_merged_dedup(self, project):
        write_chapter(project, 1, "a")
        track.main(["update", str(project), "第1章", "1", "1", "0", "--material", "m1.md"])
        track.main(["update", str(project), "第1章", "1", "1", "0",
                    "--material", "m1.md", "--unverified"])
        assert _materials(project)["chapters"]["第1章"]["source_files"] == ["m1.md"]

    def test_check_missing_materials_rc1(self, project):
        assert track.main(["check", str(project), "第1章"]) == 1

    def test_check_unknown_chapter_rc1(self, project):
        write_chapter(project, 1, "a")
        track.main(["init", str(project)])
        assert track.main(["check", str(project), "第9章"]) == 1


class TestStale:
    def test_fresh_rc0(self, project):
        write_chapter(project, 1, GOOD_CHAPTER)
        track.main(["update", str(project), "第1章", "100", "20", "3"])
        assert track.main(["stale", str(project), "第1章"]) == 0

    def test_stale_after_modification_rc1(self, project):
        p = write_chapter(project, 1, GOOD_CHAPTER)
        track.main(["update", str(project), "第1章", "100", "20", "3"])
        p.write_text(GOOD_CHAPTER + "\n新增内容\n", encoding="utf-8")
        assert track.main(["stale", str(project), "第1章"]) == 1

    def test_not_verified_rc2(self, project):
        write_chapter(project, 1, "a")
        track.main(["init", str(project)])
        assert track.main(["stale", str(project), "第1章"]) == 2


class TestShowAndAutoInit:
    def test_show(self, project, capsys):
        write_chapter(project, 1, "a")
        track.main(["init", str(project)])
        assert track.main(["show", str(project)]) == 0
        assert "第1章" in capsys.readouterr().out

    def test_show_missing_rc1(self, project):
        assert track.main(["show", str(project)]) == 1

    def test_auto_init(self, project):
        write_chapter(project, 1, "a")
        # materials.json 缺失 → 自动 init 后再 check（pending → rc 2）
        assert track.main(["auto-init", str(project), "第1章"]) == 2
        assert (project / "materials.json").exists()


class TestBibAudit:
    def test_no_urls_rc0(self, project):
        write_chapter(project, 1, "无链接章节")
        track.main(["init", str(project)])
        assert track.main(["bib-audit", str(project)]) == 0

    def test_low_authority_warns_rc1(self, project, capsys):
        body = ("\\chapter{t}\n\\begin{thebibliography}{99}\n"
                "\\bibitem{c1r1} \\href{https://zh.wikipedia.org/a}{w1}\n"
                "\\bibitem{c1r2} \\href{https://arxiv.org/abs/1}{a1}\n"
                "\\end{thebibliography}")
        write_chapter(project, 1, body)
        track.main(["init", str(project)])
        # 权威源仅 1（arxiv）< 3 → 告警 rc 1
        assert track.main(["bib-audit", str(project)]) == 1

    def test_commented_urls_ignored(self, project):
        # 骨架里的注释占位 \bibitem / \href 不计入审计
        body = "\\chapter{t}\n% \\bibitem{c1r1} \\href{https://example.com/x}{示例}\n"
        write_chapter(project, 1, body)
        track.main(["init", str(project)])
        assert track.main(["bib-audit", str(project)]) == 0  # 无真实 URL → 跳过 → 全过

    def test_enough_authority_rc0(self, project):
        body = ("\\chapter{t}\n\\begin{thebibliography}{99}\n"
                "\\bibitem{c1r1} \\href{https://arxiv.org/abs/1}{a1}\n"
                "\\bibitem{c1r2} \\href{https://doi.org/10.1/x}{a2}\n"
                "\\bibitem{c1r3} \\href{https://nature.com/x}{a3}\n"
                "\\end{thebibliography}")
        write_chapter(project, 1, body)
        track.main(["init", str(project)])
        assert track.main(["bib-audit", str(project)]) == 0


class TestTrackUpdateAuto:
    """track update --auto：size/lines 取章节 .tex 实测，chunks 取素材 reader 状态。"""

    def test_auto_computes_from_tex_and_material(self, project, tmp_path):
        from pdfmaker.commands import reader as reader_mod
        write_chapter(project, 2, GOOD_CHAPTER)
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n\n正文\n", encoding="utf-8")
        assert reader_mod.main(["ingest", str(md)]) == 0
        rc = track.main(["update", str(project), "第2章", "--auto",
                         "--material", str(md)])
        assert rc == 0
        info = _materials(project)["chapters"]["第2章"]
        tex = project / "第2章" / "第2章.tex"
        assert info["size_bytes"] == tex.stat().st_size
        assert info["total_lines"] == tex.read_text(encoding="utf-8").count("\n")
        assert info["chunks_read_count"] == 1  # 3 行素材 = 1 chunk
        assert info["status"] == "verified"

    def test_positional_still_works(self, project):
        """旧的手动三整数用法保持兼容。"""
        write_chapter(project, 1, GOOD_CHAPTER)
        rc = track.main(["update", str(project), "第1章", "100", "20", "1"])
        assert rc == 0
        assert _materials(project)["chapters"]["第1章"]["size_bytes"] == 100

    def test_missing_numbers_without_auto_rc2(self, project, capsys):
        write_chapter(project, 1, GOOD_CHAPTER)
        rc = track.main(["update", str(project), "第1章"])
        assert rc == 2
        assert "--auto" in capsys.readouterr().out
