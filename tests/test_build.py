# -*- coding: utf-8 -*-
"""commands.build：整书合并编排（xelatex 用假编译桩替换，不依赖真实 TeX）。"""

import glob
import re
import shutil
from pathlib import Path

import pytest

from pdfmaker.commands import build as build_mod
from pdfmaker.commands import scaffold
from pdfmaker.core import xelatex as xel_mod

from conftest import fake_build_compile_ok, fake_compile_fail


def _make_book(root: Path, chapters: int = 2) -> None:
    """scaffold 生成书稿，并消掉末章「下一章」越界引用（让 xref 预检通过）。"""
    assert scaffold.main([str(root), "--chapters", str(chapters),
                          "--title", "测试书", "--author", "佚名"]) == 0
    for p in root.glob("第*章/第*章.tex"):
        t = p.read_text(encoding="utf-8")
        t = re.sub(r"（第~\d+ 章）", "", t)
        p.write_text(t, encoding="utf-8")


class TestBuildMain:
    def test_full_merge_success(self, tmp_path, monkeypatch):
        root = tmp_path / "book"
        _make_book(root)
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        assert (root / "main.pdf").read_bytes() == b"%PDF-1.5 fake"
        assert not (root / "_build").exists()  # 成功后清理

    def test_normalized_copies_share_single_source(self, tmp_path, monkeypatch):
        """合并时 _build 内的归一副本必须与单章 fix 同一套 normalize_text。"""
        root = tmp_path / "book"
        _make_book(root)
        captured = {}

        def spy_compile(xelatex, *args, cwd=None, quiet=False):
            d = Path(cwd)
            captured["main.tex"] = (d / "main.tex").read_text(encoding="utf-8")
            captured["ch1"] = (d / "第1章.tex").read_text(encoding="utf-8")
            return fake_build_compile_ok(xelatex, *args, cwd=cwd)

        monkeypatch.setattr(xel_mod, "compile", spy_compile)
        assert build_mod.main([str(root)]) == 0
        # main.tex 的 \input 被重写指向 _build 内的归一副本
        assert "\\input{第1章.tex}" in captured["main.tex"]
        assert "\\input{第1章/第1章}" not in captured["main.tex"]
        # 归一副本不含 \url（已被 normalize 为 \href）
        assert "\\url{" not in captured["ch1"]
        # 归一副本的 tikzpicture 已被 adjustbox 包裹（单一规范化真源生效）
        assert "\\begin{adjustbox}" in captured["ch1"]
        # 源文件不被改写（规范化只作用于副本）
        src1 = (root / "第1章" / "第1章.tex").read_text(encoding="utf-8")
        assert "\\begin{adjustbox}" not in src1

    def test_xelatex_failure_keeps_build_dir(self, tmp_path, monkeypatch):
        root = tmp_path / "book"
        _make_book(root)
        monkeypatch.setattr(xel_mod, "compile", fake_compile_fail)
        assert build_mod.main([str(root)]) == 1
        assert (root / "_build").exists()  # 失败保留现场

    def test_missing_main_tex_rc2(self, tmp_path):
        root = tmp_path / "book"
        root.mkdir()
        assert build_mod.main([str(root)]) == 2

    def test_unfilled_placeholder_rc2(self, tmp_path):
        root = tmp_path / "book"
        root.mkdir()
        (root / "main.tex").write_text("\\input{第1章/第1章}\n{{CHAPTERS_LIST}}",
                                       encoding="utf-8")
        assert build_mod.main([str(root)]) == 2

    def test_no_chapter_inputs_rc2(self, tmp_path, monkeypatch):
        root = tmp_path / "book"
        _make_book(root)
        # 抹掉 main.tex 里的全部 \input
        main_tex = root / "main.tex"
        main_tex.write_text(
            re.sub(r"\\input\{[^}]+\}\n?", "", main_tex.read_text(encoding="utf-8")),
            encoding="utf-8")
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 2

    def test_nonexistent_root_rc2(self, tmp_path):
        assert build_mod.main([str(tmp_path / "不存在")]) == 2

    def test_comment_input_ignored(self, tmp_path, monkeypatch, capsys):
        """main.tex 注释里的 \\input{假章/假章} 不应被解析/告警。"""
        root = tmp_path / "book"
        _make_book(root, chapters=1)
        main_tex = root / "main.tex"
        main_tex.write_text(
            main_tex.read_text(encoding="utf-8")
            + "\n% 示例：每章写一行 \\input{第N章/第N章}\n",
            encoding="utf-8")
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        out = capsys.readouterr().out
        assert "无法解析" not in out  # 注释里的 \input 不产生告警

    def test_empty_frontmatter_warns_but_proceeds(self, tmp_path, monkeypatch, capsys):
        """模板默认 main.tex 的摘要/序言只有占位注释 → 非阻断 WARN，合并照常成功。"""
        root = tmp_path / "book"
        _make_book(root)
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        out = capsys.readouterr().out
        assert "正文为空" in out
        assert "摘要" in out

    def test_filled_frontmatter_no_warn(self, tmp_path, monkeypatch, capsys):
        """摘要/序言填写正文后不再告警。"""
        root = tmp_path / "book"
        _make_book(root)
        main_tex = root / "main.tex"
        t = main_tex.read_text(encoding="utf-8")
        t = t.replace("% 在此输入摘要正文（建议 150-300 字，概括全书主题、章节结构与核心结论）",
                      "本摘要已填写。")
        t = t.replace("% 在此输入序言正文（建议 200-400 字，介绍写作缘起 / 资料来源 / 读者对象 / 阅读建议）",
                      "本序言已填写。")
        main_tex.write_text(t, encoding="utf-8")
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        assert "正文为空" not in capsys.readouterr().out

    def test_warn_summary_repeated_at_end(self, tmp_path, monkeypatch, capsys):
        """非阻断告警必须在末尾汇总重列（exit 0 时预检 WARN 易被编译长输出淹没）。"""
        root = tmp_path / "book"
        _make_book(root)
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        out = capsys.readouterr().out
        assert "本轮合并携带" in out
        # 汇总块在「合并完成」之后，是输出的最后内容
        assert out.rindex("本轮合并携带") > out.rindex("合并完成")
        # 空壳前置与占位骨架两条 WARN 均收进汇总
        assert "- 前置部分存在但正文为空：摘要" in out
        assert "- 第1章.tex 仍是未撰写的占位骨架" in out

    def test_clean_book_no_warn_summary(self, tmp_path, monkeypatch, capsys):
        """前置部分与章节全部撰写后：无 WARN，末尾也不出现汇总块。"""
        root = tmp_path / "book"
        _make_book(root)
        main_tex = root / "main.tex"
        t = main_tex.read_text(encoding="utf-8")
        t = t.replace("% 在此输入摘要正文（建议 150-300 字，概括全书主题、章节结构与核心结论）",
                      "本摘要已填写。")
        t = t.replace("% 在此输入序言正文（建议 200-400 字，介绍写作缘起 / 资料来源 / 读者对象 / 阅读建议）",
                      "本序言已填写。")
        main_tex.write_text(t, encoding="utf-8")
        for p in root.glob("第*章/第*章.tex"):
            p.write_text(p.read_text(encoding="utf-8")
                         .replace("未命名章标题", "已撰写章节"), encoding="utf-8")
        monkeypatch.setattr(xel_mod, "compile", fake_build_compile_ok)
        assert build_mod.main([str(root)]) == 0
        assert "本轮合并携带" not in capsys.readouterr().out


class TestXelatexWrapper:
    def test_timeout_returns_124_not_raises(self, tmp_path):
        """超时应以约定的 TIMEOUT_RC(124) 返回，而非向上抛 TimeoutExpired。"""
        sleeper = shutil.which("sleep") or "/bin/sleep"
        rc = xel_mod.compile(sleeper, "5", cwd=str(tmp_path), timeout=0.2)
        assert rc == xel_mod.TIMEOUT_RC

    def test_success_passthrough_rc(self, tmp_path):
        true_bin = shutil.which("true") or "/usr/bin/true"
        assert xel_mod.compile(true_bin, cwd=str(tmp_path), timeout=5) == 0


class TestFindXelatex:
    def test_env_override(self, tmp_path, monkeypatch):
        fake = tmp_path / "xelatex-fake"
        fake.write_text("#!/bin/sh\n", encoding="utf-8")
        monkeypatch.setenv("PDFMAKER_XELATEX", str(fake))
        assert build_mod.find_xelatex() == str(fake)

    def test_env_nonexistent_falls_through(self, monkeypatch):
        monkeypatch.setenv("PDFMAKER_XELATEX", "/nonexistent/xelatex")
        result = build_mod.find_xelatex()
        assert isinstance(result, str) and result

    def test_returns_string_by_default(self):
        result = build_mod.find_xelatex()
        assert isinstance(result, str) and result
        if shutil.which("xelatex"):
            assert result == "xelatex"
        else:
            # PATH 未收录时：应命中平台候选/glob（如 ~/texlive），或兜底 "xelatex"
            known = glob.glob(str(Path.home() / "texlive/*/bin/*/xelatex"))
            if known:
                assert result in known
            else:
                assert result == "xelatex"
