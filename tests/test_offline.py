"""Tests that need no API keys. Run: .venv/bin/python -m pytest -q tests"""
from types import SimpleNamespace

from hoito.agent import _drop_unverified, _profile, verify_answer
from hoito.safety import red_flags
from hoito.sources import Registry
from hoito.verify import check

PAGE = """# Asiakasmaksut 2026

| Palvelu | Maksu |
|---|---|
| Lääkärin vastaanottokäynti terveysasemalla | 25,30 € |

Päivystyskäynnin maksu on **28,70 €**. Lisätietoja [täältä](https://example.fi/x).
Exchange students who are not covered by FSHS can use the public health centre."""


def test_exact_quote():
    assert check("Päivystyskäynnin maksu on 28,70 €.", PAGE) == "exact"


def test_quote_survives_markdown_and_table_pipes():
    assert check("Lääkärin vastaanottokäynti terveysasemalla 25,30 €", PAGE) == "exact"
    assert check("Lisätietoja täältä", PAGE) == "exact"


def test_quote_with_small_difference_is_near():
    assert check("Exchange students who are not covered by the FSHS can use the public health centre.", PAGE) == "near"


def test_invented_quote_is_missing():
    assert check("Päivystyskäynnin maksu on 41,20 €.", PAGE) == "missing"
    assert check("Exchange students can always use FSHS for free.", PAGE) == "missing"
    assert check("", PAGE) == "missing"


def test_red_flags():
    assert "chest pain" in red_flags("I have chest pain and feel sick")
    assert "trouble breathing" in red_flags("my kid can't breathe properly")
    assert "chest pain" in red_flags("Minulla on rintakipu")
    assert red_flags("my ear hurts since yesterday") == []
    assert red_flags("lower back pain for two weeks") == []


def _registry() -> Registry:
    reg = Registry()
    reg.add(SimpleNamespace(url="https://hel.fi/fees", title="Fees", text=PAGE, highlights=None,
                            published_date="2026-01-01", crawl_date=None), "official")
    return reg


def _answer(quote: str) -> dict:
    claim = lambda q: {"text": "x", "source_id": "S1", "quote": q}  # noqa: E731
    return {"urgency": "today", "headline": "h", "summary": "s",
            "primary": {"title": "t", "kind": "public_health_centre", "when": "w", "facts": [claim(quote)]},
            "alternatives": [], "costs": [claim("Päivystyskäynnin maksu on 28,70 €.")], "heads_up": [],
            "bring": [{"text": "x", "source_id": "S9", "quote": "nope"}], "message_fi": "", "message_en": ""}


def test_verify_and_drop():
    a = _answer("This sentence is not on the page at all.")
    problems = verify_answer(a, _registry())
    assert len(problems) == 2  # bad quote + unknown source id
    assert a["costs"][0]["verified"] == "exact"
    assert _drop_unverified(a) == 2
    assert a["primary"]["facts"] == [] and a["bring"] == [] and len(a["costs"]) == 1


def test_profile_mentions_region_and_red_flag():
    p = _profile({"status": "exchange_student", "city": "Espoo", "problem": "chest pain since an hour"})
    assert "Western Uusimaa" in p and "luvn.fi" in p
    assert "Red flags" in p


def test_changed_number_in_long_quote_is_missing():
    page = "The client fee for a visit to the emergency department is 28,70 euros for adults over 18 years of age."
    assert check("The client fee for a visit to the emergency department is 28,70 euros for adults over 18.", page) == "exact"  # a cut-off quote is still on the page
    assert check("The client fee for a visit to the emergency department is 41,20 euros for adults over 18 years of age.", page) == "missing"


def _fake_tools(monkeypatch):
    from hoito import sources

    page = SimpleNamespace(url="https://yths.fi/en/fees", title="Fees", text="Exchange students pay a health fee of 40 euros.",
                           highlights=None, published_date="2026-08-01", crawl_date=None)

    async def fake_tool(reg, name, args):
        s = reg.add(page, "official", live=(name == "read_page"))
        return {"results": [{"source_id": s.id, "title": s.title, "url": s.url, "excerpt": page.text}]}

    monkeypatch.setattr(sources, "run_tool", fake_tool)


def _fake_answer(quote):
    return {"urgency": "this_week", "headline": "Book FSHS", "summary": "s",
            "primary": {"title": "FSHS", "kind": "student_health", "when": "w",
                        "facts": [{"text": "Fee is 40 €", "source_id": "S1", "quote": quote}]},
            "alternatives": [], "costs": [], "heads_up": [], "bring": [], "message_fi": "fi", "message_en": "en"}


# The script both providers follow: search → submit with a bad quote → resubmit with the right quote.
SCRIPT = [("search_official", {"query": "fees"}),
          ("submit_answer", _fake_answer("Exchange students pay 50 euros.")),
          ("submit_answer", _fake_answer("Exchange students pay a health fee of 40 euros."))]


def _run_and_check():
    import asyncio

    from hoito import agent
    events = []

    async def collect(e):
        events.append(e)

    out = asyncio.run(agent.run({"problem": "fees?", "status": "exchange_student", "city": "Espoo"}, collect))
    kinds = [e["type"] for e in events]
    assert kinds.count("step") == 2 and "note" in kinds and kinds[-1] == "answer"
    assert out["answer"]["primary"]["facts"][0]["verified"] == "exact"
    assert out["stats"]["claims"] == 1 and out["stats"]["dropped"] == 0
    assert [s["id"] for s in out["sources"]] == ["S1"]
    return out


def test_agent_loop_claude(monkeypatch):
    from hoito import llm
    _fake_tools(monkeypatch)
    monkeypatch.setenv("HOITO_PROVIDER", "claude")
    turns = iter([[SimpleNamespace(type="tool_use", id=f"t{i}", name=n, input=a)] for i, (n, a) in enumerate(SCRIPT)])
    sent = []

    class FakeMessages:
        async def create(self, **kw):
            sent.append(kw["messages"][-1])
            return SimpleNamespace(stop_reason="tool_use", content=next(turns), usage=SimpleNamespace(input_tokens=1000, output_tokens=100))

    monkeypatch.setattr(llm.anthropic, "AsyncAnthropic", lambda: SimpleNamespace(beta=SimpleNamespace(messages=FakeMessages())))
    out = _run_and_check()
    assert out["stats"]["model"] == "claude-opus-5-5"
    assert sent[2]["content"][0]["is_error"] is True  # the bad quote went back as an error


def test_agent_loop_openai(monkeypatch):
    import json as _json

    from hoito import llm
    _fake_tools(monkeypatch)
    monkeypatch.setenv("HOITO_PROVIDER", "openai")
    monkeypatch.delenv("OPENAI_MODEL", raising=False)

    class Msg(SimpleNamespace):
        def model_dump(self, exclude_none=True):
            return {"role": "assistant", "content": None, "tool_calls": [
                {"id": tc.id, "type": "function", "function": {"name": tc.function.name, "arguments": tc.function.arguments}} for tc in self.tool_calls]}

    turns = iter([Msg(refusal=None, tool_calls=[SimpleNamespace(id=f"c{i}", function=SimpleNamespace(name=n, arguments=_json.dumps(a)))])
                  for i, (n, a) in enumerate(SCRIPT)])
    sent = []

    class FakeCompletions:
        async def create(self, **kw):
            sent.append(list(kw["messages"]))
            assert kw["tools"][-1]["function"]["strict"] is True
            return SimpleNamespace(choices=[SimpleNamespace(message=next(turns))], usage=SimpleNamespace(prompt_tokens=1000, completion_tokens=100))

    monkeypatch.setattr(llm.openai, "AsyncOpenAI", lambda **kw: SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    out = _run_and_check()
    assert out["stats"]["model"] == "gpt-4.1"
    last = sent[2][-1]
    assert last["role"] == "tool" and last["tool_call_id"] == "c1" and last["content"].startswith("ERROR:")
