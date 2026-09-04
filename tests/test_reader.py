# -*- coding: utf-8 -*-
"""commands.reader：素材强制阅读三阶段（index/chunk/verify/ingest/toc/clean）。"""

import json

import pytest

from pdfmaker.commands import reader
import pdfmaker.core.config as cfg


@pytest.fixture
def material(tmp_path):
    """450 行中文素材：按 CHUNK_SIZE_CN=200 应规划为 3 个 chunk。"""
    p = tmp_path / "素材.md"
    lines = ["# 素材标题", "", "## 背景"]
    lines += [f"第 {i} 行中文内容。" for i in range(447)]
    p.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return p


class TestDetectKind:
    def test_chinese(self):
        assert reader.detect_kind("这是一段中文内容" * 10) == "cn"

    def test_english(self):
        assert reader.detect_kind("This is an English sentence. " * 10) == "en"

    def test_empty(self):
        assert reader.detect_kind("") == "en"


class TestStatePath:
    def test_deterministic_hash(self, material):
        assert reader.state_path(str(material)) == reader.state_path(str(material))

    def test_lives_in_global_cache(self, material):
        sp = reader.state_path(str(material))
        assert sp.parent == cfg.READER_STATE_DIR
        assert sp.name.startswith("reader-state-") and sp.suffix == ".json"

    def test_no_dotfile_in_content_dir(self, material):
        reader.main(["index", str(material)])
        assert not list(material.parent.glob(".reader-state-*.json"))


class TestLifecycle:
    def test_index_writes_state(self, material, capsys):
        assert reader.main(["index", str(material)]) == 0
        report = json.loads(capsys.readouterr().out.split("\n[STATE WRITTEN]")[0])
        assert report["kind"] == "cn"
        assert report["chunks_planned"] == 3
        st = reader.load_state(str(material))
        assert st["total_chunks"] == 3
        assert st["chunks_read"] == []

    def test_verify_fails_before_reading(self, material, capsys):
        reader.main(["index", str(material)])
        assert reader.main(["verify", str(material)]) == 1
        assert "FAIL" in capsys.readouterr().out

    def test_full_chunk_read_passes(self, material):
        reader.main(["index", str(material)])
        for n in range(3):
            assert reader.main(["chunk", str(material), str(n)]) == 0
        assert reader.main(["verify", str(material)]) == 0

    def test_gap_fails_verify(self, material, capsys):
        reader.main(["index", str(material)])
        reader.main(["chunk", str(material), "0"])
        reader.main(["chunk", str(material), "2"])  # 跳过 chunk 1
        assert reader.main(["verify", str(material)]) == 1
        assert "MISSING: [1]" in capsys.readouterr().out

    def test_chunk_out_of_range_dies(self, material):
        reader.main(["index", str(material)])
        with pytest.raises(SystemExit):
            reader.main(["chunk", str(material), "99"])

    def test_chunk_without_index_dies(self, material):
        with pytest.raises(SystemExit):
            reader.main(["chunk", str(material), "0"])

    def test_modified_file_fails_bytes_check(self, material):
        reader.main(["ingest", str(material)])
        with material.open("a", encoding="utf-8") as f:
            f.write("新增一行\n")
        assert reader.main(["verify", str(material)]) == 1

    def test_ingest_end_to_end(self, material):
        assert reader.main(["ingest", str(material)]) == 0
        st = reader.load_state(str(material))
        assert sorted(st["chunks_read"]) == [0, 1, 2]

    def test_missing_file_dies(self, tmp_path):
        with pytest.raises(SystemExit):
            reader.main(["index", str(tmp_path / "不存在.md")])

    def test_toc_prints_headings(self, material, capsys):
        assert reader.main(["toc", str(material)]) == 0
        out = capsys.readouterr().out
        assert "素材标题" in out and "背景" in out


class TestClean:
    def test_clean_global_dry_run_then_apply(self, material):
        reader.main(["ingest", str(material)])
        state_files = list(cfg.READER_STATE_DIR.glob("reader-state-*.json"))
        assert len(state_files) == 1
        # 试运行：不删
        assert reader.main(["clean", "--global"]) == 0
        assert len(list(cfg.READER_STATE_DIR.glob("reader-state-*.json"))) == 1
        # --apply：真删
        assert reader.main(["clean", "--global", "--apply"]) == 0
        assert list(cfg.READER_STATE_DIR.glob("reader-state-*.json")) == []

    def test_clean_legacy_dotfiles(self, tmp_path):
        legacy = tmp_path / "sub" / ".reader-state-deadbeef.json"
        legacy.parent.mkdir(parents=True)
        legacy.write_text("{}", encoding="utf-8")
        assert reader.main(["clean", str(tmp_path), "--apply"]) == 0
        assert not legacy.exists()


class TestIngestCache:
    """ingest 缓存短路：素材未变更时跳过逐块重读，--force 强制重读。"""

    def test_second_ingest_short_circuits(self, tmp_path, capsys):
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n\n" + "行\n" * 50, encoding="utf-8")
        assert reader.main(["ingest", str(md)]) == 0
        capsys.readouterr()
        assert reader.main(["ingest", str(md)]) == 0
        out = capsys.readouterr().out
        assert "跳过逐块重读" in out
        assert "=== CHUNK" not in out  # 未重新 dump 全文

    def test_force_rereads(self, tmp_path, capsys):
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n\n" + "行\n" * 50, encoding="utf-8")
        assert reader.main(["ingest", str(md)]) == 0
        capsys.readouterr()
        assert reader.main(["ingest", str(md), "--force"]) == 0
        assert "=== CHUNK" in capsys.readouterr().out

    def test_modified_material_rereads(self, tmp_path, capsys):
        """素材变更后缓存失效，重新逐块通读。"""
        md = tmp_path / "素材.md"
        md.write_text("# 标题\n\n" + "行\n" * 50, encoding="utf-8")
        assert reader.main(["ingest", str(md)]) == 0
        md.write_text(md.read_text(encoding="utf-8") + "新增一行\n", encoding="utf-8")
        capsys.readouterr()
        assert reader.main(["ingest", str(md)]) == 0
        assert "=== CHUNK" in capsys.readouterr().out
