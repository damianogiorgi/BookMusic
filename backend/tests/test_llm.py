"""Tests for the Ollama transport's conditional "think" field (httpx stubbed)."""

import httpx

from bookmusic.llm import _call_ollama


class FakeResponse:
    def __init__(self, status_code, text="", content=""):
        self.status_code = status_code
        self.text = text
        self._content = content

    def raise_for_status(self):
        if self.status_code >= 400:
            raise httpx.HTTPStatusError(self.text, request=None, response=None)

    def json(self):
        return {"message": {"content": self._content}}


def test_think_false_sent_to_thinking_models(monkeypatch):
    bodies = []

    def fake_post(url, json, timeout):
        bodies.append(json)
        return FakeResponse(200, content="setcpm(30)")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert _call_ollama("sys", "user") == "setcpm(30)"
    assert len(bodies) == 1
    assert bodies[0]["think"] is False


def test_think_dropped_when_model_rejects_it(monkeypatch):
    bodies = []

    def fake_post(url, json, timeout):
        bodies.append(dict(json))
        if "think" in json:
            return FakeResponse(400, text='"gemma4" does not support thinking')
        return FakeResponse(200, content="setcpm(30)")

    monkeypatch.setattr(httpx, "post", fake_post)
    assert _call_ollama("sys", "user") == "setcpm(30)"
    assert len(bodies) == 2
    assert "think" not in bodies[1]
