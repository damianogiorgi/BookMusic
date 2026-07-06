"""Tests for prompt assembly and the validate-retry loop in generator.generate
(LLM stubbed out)."""

from bookmusic import generator

from test_validator import GOOD

INVALID = "setcpm(30)"  # fails validation: no stack, no modulation, ...


def test_paragraph_only(monkeypatch):
    captured = {}

    def fake_llm(system, user):
        captured["system"], captured["user"] = system, user
        return GOOD

    monkeypatch.setattr(generator, "call_llm", fake_llm)
    assert generator.generate("A quiet morning.") == GOOD
    assert captured["user"] == "PARAGRAPH: A quiet morning."
    assert captured["system"] == generator.SYSTEM_PROMPT


def test_previous_code_feeds_continuity(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        generator, "call_llm",
        lambda system, user: captured.update(user=user) or GOOD,
    )
    generator.generate("A storm breaks.", previous_code="setcpm(22)\nstack()")
    assert captured["user"].startswith("PREVIOUS CODE:\nsetcpm(22)\nstack()")
    assert captured["user"].endswith("PARAGRAPH: A storm breaks.")


def test_valid_code_returns_on_first_attempt(monkeypatch):
    calls = []
    monkeypatch.setattr(
        generator, "call_llm", lambda s, u: calls.append(1) or GOOD
    )
    assert generator.generate("x") == GOOD
    assert len(calls) == 1


def test_invalid_code_is_retried(monkeypatch):
    replies = iter([INVALID, GOOD])
    calls = []
    monkeypatch.setattr(
        generator, "call_llm", lambda s, u: calls.append(1) or next(replies)
    )
    assert generator.generate("x") == GOOD
    assert len(calls) == 2


def test_best_attempt_returned_when_all_fail(monkeypatch):
    # GOOD with one flaw (1 issue) beats INVALID (many issues).
    nearly = GOOD.replace(".gain(.5)", ".gain(.9)")
    replies = iter([INVALID, nearly, INVALID])
    calls = []
    monkeypatch.setattr(
        generator, "call_llm", lambda s, u: calls.append(1) or next(replies)
    )
    assert generator.generate("x") == nearly
    assert len(calls) == generator.MAX_ATTEMPTS
