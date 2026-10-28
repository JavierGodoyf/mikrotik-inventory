import pytest

from app import upstream


class FakeResponse:
    def __init__(self, text, status=200):
        self.text = text
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise upstream.httpx.HTTPStatusError("boom", request=None, response=None)


def test_fetch_latest_parses_version_and_timestamp(monkeypatch):
    captured = {}

    def fake_get(url, **kwargs):
        captured["url"] = url
        return FakeResponse("7.25 1792678320\n")

    monkeypatch.setattr(upstream.httpx, "get", fake_get)
    version, released = upstream.fetch_latest("stable", "7")

    assert version == "7.25"
    assert released is not None and released.year == 2026
    assert captured["url"].endswith("NEWESTa7.stable")


def test_fetch_latest_rejects_unpublished_channel(monkeypatch):
    monkeypatch.setattr(upstream.httpx, "get", lambda *a, **k: FakeResponse("0.00\n"))
    with pytest.raises(upstream.UpstreamError):
        upstream.fetch_latest("long-term", "7")


def test_fetch_latest_wraps_http_errors(monkeypatch):
    monkeypatch.setattr(upstream.httpx, "get", lambda *a, **k: FakeResponse("nope", 503))
    with pytest.raises(upstream.UpstreamError):
        upstream.fetch_latest("stable", "7")
