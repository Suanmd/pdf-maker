# -*- coding: utf-8 -*-
"""core.config：环境变量覆盖、.pdfmaker.toml 项目配置（优先级 env > toml > 默认）。"""

import sys
from pathlib import Path

import pdfmaker.core.config as cfg


class TestEnvParsing:
    def test_env_int(self, monkeypatch):
        monkeypatch.setenv("PDFMAKER_T_INT", "42")
        assert cfg._env_int("PDFMAKER_T_INT", 1) == 42

    def test_env_int_invalid_falls_back(self, monkeypatch):
        monkeypatch.setenv("PDFMAKER_T_INT", "abc")
        assert cfg._env_int("PDFMAKER_T_INT", 7) == 7

    def test_env_float(self, monkeypatch):
        monkeypatch.setenv("PDFMAKER_T_FLOAT", "2.5")
        assert cfg._env_float("PDFMAKER_T_FLOAT", 1.0) == 2.5

    def test_env_list(self, monkeypatch):
        monkeypatch.setenv("PDFMAKER_T_LIST", "a.com, b.com ,, c.com")
        assert cfg._env_list("PDFMAKER_T_LIST", []) == ["a.com", "b.com", "c.com"]

    def test_env_list_default_copy(self):
        d = ["x"]
        assert cfg._env_list("PDFMAKER_T_LIST_UNSET", d) == ["x"]
        assert cfg._env_list("PDFMAKER_T_LIST_UNSET", d) is not d


class TestPlatformCacheDir:
    def test_darwin_uses_library_caches(self):
        # 本机为 macOS：默认缓存根应落在 ~/Library/Caches/pdfmaker
        if sys.platform == "darwin":
            assert cfg._default_cache_root() == Path.home() / "Library" / "Caches" / "pdfmaker"

    def test_reader_state_under_cache_root(self):
        # conftest 已把默认值替换为 tmp；这里重新计算真实默认值验证结构
        root = cfg._default_cache_root()
        assert root.name == "pdfmaker"
        assert root.parent.name in ("Caches", ".cache")


class TestProjectConfig:
    TOML = """\
[pdfmaker]
chapter_min_chars = 4000
url_timeout = 20.0
probe_hosts = ["https://a.com", "https://b.com"]
reader_state_dir = "~/custom_reader_state"
"""

    def test_load_finds_upward(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        sub = tmp_path / "a" / "b"
        sub.mkdir(parents=True)
        monkeypatch.chdir(sub)
        found = cfg.load_project_config()
        assert found == tmp_path / ".pdfmaker.toml"
        assert cfg.PROJECT_CONFIG["chapter_min_chars"] == 4000

    def test_load_missing_returns_none(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        assert cfg.load_project_config() is None
        assert cfg.PROJECT_CONFIG == {}

    def test_apply_toml_overrides_default(self, tmp_path, monkeypatch):
        monkeypatch.setattr(cfg, "CHAPTER_MIN_CHARS", 2000)
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        assert cfg.CHAPTER_MIN_CHARS == 4000

    def test_env_beats_toml(self, tmp_path, monkeypatch):
        # 环境变量在模块导入时已被读入全局值；apply 遇到已设置的环境变量会跳过 toml。
        # 这里模拟「全局值已是环境变量给的 5000」，验证 toml 的 4000 不会覆盖它。
        monkeypatch.setattr(cfg, "CHAPTER_MIN_CHARS", 5000)
        monkeypatch.setenv("PDFMAKER_CHAPTER_MIN_CHARS", "5000")
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        assert cfg.CHAPTER_MIN_CHARS == 5000  # toml 被跳过，保持环境变量的值

    def test_toml_path_expanduser(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        # 不展开 ~ 会得到字面相对路径 "~"；展开后应等于 $HOME/custom_reader_state
        assert cfg.READER_STATE_DIR == Path.home() / "custom_reader_state"

    def test_bad_toml_degrades_silently(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text("[[[不是合法 toml", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        assert cfg.load_project_config() is not None
        assert cfg.PROJECT_CONFIG == {}

    def test_flat_keys_supported(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text("chapter_min_chars = 1234\n", encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        assert cfg.PROJECT_CONFIG["chapter_min_chars"] == 1234


class TestNewConfigKeys:
    TOML = """\
[pdfmaker]
texttt_relax_chars = 30
table_squeeze_warn_chars = 18
verify_allow_hosts = ["internal.example.com", "docs.corp.local"]
"""

    def test_scalar_overrides(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        assert cfg.TEXTTT_RELAX_CHARS == 30
        assert cfg.TABLE_SQUEEZE_WARN_CHARS == 18

    def test_list_override(self, tmp_path, monkeypatch):
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        assert cfg.VERIFY_ALLOW_HOSTS == ["internal.example.com", "docs.corp.local"]

    def test_env_beats_toml_for_new_keys(self, tmp_path, monkeypatch):
        # 与 CHAPTER_MIN_CHARS 的既有用例同理：模块在导入时已读入环境变量，
        # 这里用 setattr 模拟「全局值已是环境变量给的 22」，验证 toml 的 30 不会覆盖。
        monkeypatch.setattr(cfg, "TEXTTT_RELAX_CHARS", 22)
        monkeypatch.setenv("PDFMAKER_TEXTTT_RELAX_CHARS", "22")
        (tmp_path / ".pdfmaker.toml").write_text(self.TOML, encoding="utf-8")
        monkeypatch.chdir(tmp_path)
        cfg.load_project_config()
        cfg.apply_project_config()
        assert cfg.TEXTTT_RELAX_CHARS == 22  # toml 的 30 被跳过
