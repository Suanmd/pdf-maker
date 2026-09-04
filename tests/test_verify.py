# -*- coding: utf-8 -*-
"""commands.verify：URL 抽取、格式校验、状态码分类、缓存、软 404、main 决策（网络全部 mock）。"""

import json
import time

import pytest

from pdfmaker.commands import verify
import pdfmaker.core.config as cfg
from conftest import write_chapter


class TestExtractUrls:
    def test_url_and_href(self):
        tex = r"\url{https://a.com} \href{https://b.com}{显示}"
        assert verify.extract_urls(tex) == ["https://a.com", "https://b.com"]

    def test_verb_excluded(self):
        tex = r"\verb|\url{https://fake.com}| \url{https://real.com}"
        assert verify.extract_urls(tex) == ["https://real.com"]


class TestFormatOk:
    @pytest.mark.parametrize("url", [
        "https://example.com/x",
        "http://a.b.com:8080/p?q=1",
    ])
    def test_valid(self, url):
        assert verify.format_ok(url)

    @pytest.mark.parametrize("url", [
        "",
        "https://例子.com/x",       # 非 ASCII
        "https://a.com/x y",         # 空白
        "ftp://a.com/x",             # 非 http(s)
        "https:///nohost",           # 无 netloc
    ])
    def test_invalid(self, url):
        assert not verify.format_ok(url)


class TestLooksTruncated:
    def test_cases(self):
        assert verify._looks_truncated("https://a.com/…")
        assert verify._looks_truncated("https://a.com/x...y")
        assert verify._looks_truncated("https://a.com/x y")
        assert not verify._looks_truncated("https://a.com/x.y")


class TestClassifyHttp:
    def test_2xx_3xx_live(self):
        assert verify._classify_http("u", 200)[0] == "LIVE"
        assert verify._classify_http("u", 301)[0] == "LIVE"

    def test_hard_dead(self):
        assert verify._classify_http("u", 404)[0] == "DEAD"
        assert verify._classify_http("u", 410)[0] == "DEAD"

    def test_soft_blocked_still_live(self):
        for code in (401, 403, 429):
            assert verify._classify_http("u", code)[0] == "LIVE"

    def test_method_rejected_still_live(self):
        for code in (400, 405, 406, 407):
            assert verify._classify_http("u", code)[0] == "LIVE"

    def test_server_error_returns_none_for_retry(self):
        for code in (500, 502, 503, 504, 408, 425):
            assert verify._classify_http("u", code) is None

    def test_451_archive_fallback(self, monkeypatch):
        monkeypatch.setattr(verify, "archive_has", lambda u, timeout=None: (True, "snap-url"))
        url, status, _ = verify._classify_http("https://a.com", 451)
        assert status == "ARCHIVE"

    def test_451_no_archive_is_dead(self, monkeypatch):
        monkeypatch.setattr(verify, "archive_has", lambda u, timeout=None: (False, ""))
        _, status, _ = verify._classify_http("https://a.com", 451)
        assert status == "DEAD"


class TestSoft404:
    def test_indicators(self):
        assert verify._looks_soft404("<html>Page not found</html>")
        assert verify._looks_soft404("抱歉，页面不存在")
        assert not verify._looks_soft404("正常论文内容")
        assert not verify._looks_soft404("")


class TestCache:
    def test_roundtrip(self, tmp_path):
        p = tmp_path / "c.json"
        verify.save_cache(p, {"https://a.com": {"status": "LIVE", "detail": "d", "ts": 1.0}})
        assert verify.load_cache(p)["https://a.com"]["status"] == "LIVE"

    def test_load_missing_returns_empty(self, tmp_path):
        assert verify.load_cache(tmp_path / "nope.json") == {}

    def test_load_corrupt_returns_empty(self, tmp_path):
        p = tmp_path / "c.json"
        p.write_text("{损坏", encoding="utf-8")
        assert verify.load_cache(p) == {}

    def test_cache_path_default_uses_cfg(self):
        assert verify._cache_path(None) == cfg.VERIFY_CACHE_DIR / cfg.VERIFY_CACHE_FILE

    def test_cache_path_override(self):
        assert verify._cache_path("/tmp/x.json") == verify.Path("/tmp/x.json")


# ---- main() 决策流（probe_network / probe_one 全部 mock，不触网） ----

def _mock_online(monkeypatch, status="LIVE", detail="HTTP 200"):
    monkeypatch.setattr(verify, "probe_network", lambda: True)
    monkeypatch.setattr(
        verify, "probe_one",
        lambda u, retries=None, timeout=None: (u, status, detail))


class TestVerifyMain:
    def _chapter_with_url(self, project, url):
        return write_chapter(project, 1, f"参考 \\href{{{url}}}{{显示}}")

    def test_all_live_rc0(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com")
        _mock_online(monkeypatch)
        assert verify.main(["1"]) == 0

    def test_dead_rc1(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/dead")
        _mock_online(monkeypatch, status="DEAD", detail="HTTP 404")
        assert verify.main(["1"]) == 1

    def test_transient_rc2(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/flaky")
        _mock_online(monkeypatch, status="TRANSIENT", detail="重试耗尽")
        assert verify.main(["1"]) == 2

    def test_format_bad_rc1_without_network(self, project, monkeypatch):
        self._chapter_with_url(project, "https://例子.com/x")
        # probe_network 不应被依赖；即便在线 FORMAT 也必判 rc 1
        _mock_online(monkeypatch)
        assert verify.main(["1"]) == 1

    def test_no_urls_rc0(self, project):
        write_chapter(project, 1, "全章无任何链接")
        assert verify.main(["1"]) == 0

    def test_book_mode_collects_all_chapters(self, project, monkeypatch):
        write_chapter(project, 1, r"\href{https://a.com/1}{x}")
        write_chapter(project, 2, r"\href{https://a.com/2}{y}")
        probed = []

        def fake_probe(u, retries=None, timeout=None):
            probed.append(u)
            return (u, "LIVE", "HTTP 200")

        monkeypatch.setattr(verify, "probe_network", lambda: True)
        monkeypatch.setattr(verify, "probe_one", fake_probe)
        assert verify.main([str(project)]) == 0
        assert sorted(probed) == ["https://a.com/1", "https://a.com/2"]

    def test_cache_reused_on_second_run(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/cached")
        calls = []

        def fake_probe(u, retries=None, timeout=None):
            calls.append(u)
            return (u, "LIVE", "HTTP 200")

        monkeypatch.setattr(verify, "probe_network", lambda: True)
        monkeypatch.setattr(verify, "probe_one", fake_probe)
        assert verify.main(["1"]) == 0
        assert calls == ["https://example.com/cached"]
        # 第二次：新鲜缓存命中，不再联网
        assert verify.main(["1"]) == 0
        assert calls == ["https://example.com/cached"]

    def test_refresh_ignores_cache(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/cached")
        calls = []

        def fake_probe(u, retries=None, timeout=None):
            calls.append(u)
            return (u, "LIVE", "HTTP 200")

        monkeypatch.setattr(verify, "probe_network", lambda: True)
        monkeypatch.setattr(verify, "probe_one", fake_probe)
        verify.main(["1"])
        verify.main(["1", "--refresh"])
        assert len(calls) == 2

    def test_offline_with_fresh_cache_rc0(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/offline")
        cache_file = cfg.VERIFY_CACHE_DIR / cfg.VERIFY_CACHE_FILE
        cfg.VERIFY_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_file.write_text(json.dumps({
            "https://example.com/offline": {"status": "LIVE", "detail": "d", "ts": time.time()}
        }), encoding="utf-8")
        monkeypatch.setattr(verify, "probe_network", lambda: False)
        monkeypatch.setattr(verify, "_probe_targets_reachable", lambda urls, timeout=None: False)
        assert verify.main(["1"]) == 0

    def test_offline_without_cache_rc2(self, project, monkeypatch):
        self._chapter_with_url(project, "https://example.com/uncached")
        monkeypatch.setattr(verify, "probe_network", lambda: False)
        monkeypatch.setattr(verify, "_probe_targets_reachable", lambda urls, timeout=None: False)
        assert verify.main(["1"]) == 2


class TestHostAllowed:
    def test_exact_match(self):
        assert verify.host_allowed("https://internal.example.com/x", ["internal.example.com"])

    def test_subdomain_suffix_match(self):
        assert verify.host_allowed("https://docs.internal.example.com/x", ["example.com"])

    def test_no_match(self):
        assert not verify.host_allowed("https://example.com/x", ["other.com"])

    def test_suffix_does_not_match_partial_label(self):
        # notexample.com 不应被 example.com 后缀误伤（必须是 .example.com 或全等）
        assert not verify.host_allowed("https://notexample.com/x", ["example.com"])

    def test_empty_allowlist(self):
        assert not verify.host_allowed("https://example.com/x", [])

    def test_case_insensitive(self):
        assert verify.host_allowed("https://Docs.Example.COM/x", ["example.COM"])


class TestVerifyAllowHosts:
    def test_exempt_host_skips_probing_rc0(self, project, monkeypatch):
        # 豁免主机完全不触网（probe_one 若被调用即失败），结果 EXEMPT 且 exit 0
        write_chapter(project, 1, r"内网 \href{https://docs.internal.example.com/x}{文档}")
        monkeypatch.setenv("PDFMAKER_VERIFY_ALLOW_HOSTS", "internal.example.com")
        monkeypatch.setattr(verify.cfg, "VERIFY_ALLOW_HOSTS", ["internal.example.com"])
        monkeypatch.setattr(verify, "probe_network", lambda: True)
        def _boom(u, retries=None, timeout=None):
            raise AssertionError("豁免主机不应发起探测")
        monkeypatch.setattr(verify, "probe_one", _boom)
        assert verify.main(["1"]) == 0

    def test_exempt_still_format_checked(self, project, monkeypatch):
        # 豁免只免验活：格式非法（含中文）的豁免主机 URL 仍判 FORMAT rc 1
        write_chapter(project, 1, r"坏 \href{https://docs.internal.example.com/中文}{文档}")
        monkeypatch.setattr(verify.cfg, "VERIFY_ALLOW_HOSTS", ["internal.example.com"])
        monkeypatch.setattr(verify, "probe_network", lambda: True)
        assert verify.main(["1"]) == 1

    def test_mixed_exempt_and_live(self, project, monkeypatch):
        # 豁免主机 + 普通主机混合：普通主机照常联网验活
        write_chapter(project, 1,
                      r"A \href{https://docs.internal.example.com/x}{内网} "
                      r"B \href{https://example.com/y}{公网}")
        monkeypatch.setattr(verify.cfg, "VERIFY_ALLOW_HOSTS", ["internal.example.com"])
        _mock_online(monkeypatch)
        assert verify.main(["1"]) == 0

    def test_exempt_offline_also_rc0(self, project, monkeypatch):
        # 离线时豁免主机同样按已验证处理（不需要缓存、不判 TRANSIENT）
        write_chapter(project, 1, r"内网 \href{https://docs.internal.example.com/x}{文档}")
        monkeypatch.setattr(verify.cfg, "VERIFY_ALLOW_HOSTS", ["internal.example.com"])
        monkeypatch.setattr(verify, "probe_network", lambda: False)
        monkeypatch.setattr(verify, "_probe_targets_reachable", lambda urls, timeout=None: False)
        assert verify.main(["1"]) == 0
