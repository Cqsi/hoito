"""The agent: Claude plans the searches, Exa fetches the pages, code checks every quote."""
import asyncio
import json
import time
from datetime import datetime
from typing import Awaitable, Callable
from zoneinfo import ZoneInfo

from . import llm, sources
from .config import MAX_TURNS, REGIONS, SEARCH_TURNS, STATUSES, STATUS_HINTS
from .safety import red_flags
from .verify import check

Event = Callable[[dict], Awaitable[None]]


async def _noop(_: dict) -> None:
    pass


SYSTEM = """You are Hoito, a healthcare navigator for international people in Finland.
Someone tells you who they are, where they are and what is wrong. You find out, from official and
provider web pages fetched right now, where they should go, what it costs and how to get seen.

Rules
- You route people; you never diagnose. Do not name conditions or suggest treatments or medicines.
- Every fact you give (place, opening hours, phone number, fee, refund, eligibility, news) must come
  from a page your tools returned. Never rely on memory for Finnish fees, hours or rules: they change.
- If the person describes something that could be an emergency, the first line is to call 112.
- Match urgency to the problem, not to the clock. Problems that have lasted days or weeks without getting
  suddenly worse (a long cough, low mood, a check-up, a prescription renewal, a test) can wait for the
  regular service: make that the main option even at the weekend, and say when it reopens.
- When the person may need care before the regular service reopens (new or worsening pain, fever, an
  injury), include the medical helpline 116117 as an option (cite 116117.fi or the region's page): it tells
  people whether to go to emergency now or wait, and often books the visit.
- Many official pages are only in Finnish or Swedish. Search in English and Finnish (for example
  "terveysasema asiakasmaksu 2026", "päivystys", "opiskelijaterveydenhuolto"). Quote the original
  language and write the claim in English.
- Prefer the most specific page: the regional wellbeing services county's own page beats a national
  overview. If the region's site is not among the defaults, search for it by name.

How to work
1. In your first turn, call several tools at once (they run in parallel): search_official for the
   right place to go for this person's status and city, search_official for fees, news_check for
   anything this month that changes the advice (strikes, closed or congested emergency departments,
   changed fees), and search_private if a private clinic is a sensible option for this status.
2. Then read_page on the 2-4 most important pages (fees, opening hours, the place you recommend) to get
   today's exact wording.
3. Finish by calling submit_answer once. Each fact is a claim with a source_id and a quote: an exact
   sentence or table row copied character for character from that source's text (max 30 words).
   The quote is checked automatically against the page; claims whose quote is not on the page are
   rejected. Do not stitch sentences together or fix typos inside quotes.
   The claim text must say only what its own quote says. Never merge two facts (for example a resident fee
   and a rule for non-residents) into one claim: give each its own claim and quote. If the fee that applies
   to this person is not on any page, say what the page does say rather than guessing.
4. Keep it short: 2-4 facts for the main place, 1-3 alternatives, the costs that apply to this person,
   and heads-up items only if the news actually affects them. Leave a section empty rather than pad it.
5. message_fi / message_en: a short message the person can read out at reception or paste into a
   booking chat (who they are, their status, what is wrong in plain words, when it started, what they
   are asking for). Use [brackets] for details you do not know, such as their name.

Be quick: aim for 2-3 turns of tool calls before submit_answer."""

_CLAIM = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text", "source_id", "quote"],
    "properties": {
        "text": {"type": "string", "description": "The fact in plain English, one sentence."},
        "source_id": {"type": "string", "description": "Id of the source, e.g. S3."},
        "quote": {"type": "string", "description": "Exact sentence or table row from that source (original language)."},
    },
}
_OPTION = {
    "type": "object",
    "additionalProperties": False,
    "required": ["title", "kind", "when", "facts"],
    "properties": {
        "title": {"type": "string", "description": "Name of the place or service, e.g. 'Haartman Hospital emergency department'."},
        "kind": {"type": "string", "enum": ["emergency", "helpline", "student_health", "occupational", "public_health_centre", "private", "pharmacy", "other"]},
        "when": {"type": "string", "description": "When this is the right choice, e.g. 'Tonight, if the pain gets worse'."},
        "facts": {"type": "array", "items": _CLAIM},
    },
}

TOOLS = [
    {
        "name": "search_official",
        "description": "Search the live web, limited to official Finnish health and benefits sites (Kela, FSHS/YTHS, 116117, InfoFinland, HUS, ministries, regional wellbeing services counties). Returns excerpts with source ids. Pass `domains` to search specific sites, e.g. a region's own domain.",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "What to find, in English or Finnish."},
                "objective": {"type": "string", "description": "Goal for this search turn; say which documents should rank first, which should be excluded, and what specific facts or figures to pull from them."},
                "domains": {"type": "array", "items": {"type": "string"}, "description": "Optional list of domains, e.g. ['hel.fi','hus.fi']. Omit to search the default official list."},
            },
            "required": ["query", "objective"],
        },
    },
    {
        "name": "search_private",
        "description": "Search the live web, limited to private clinic chains in Finland (Mehiläinen, Terveystalo, Pihlajalinna, Aava) for locations, opening hours and visit prices.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "objective": {"type": "string", "description": "Goal for this search turn; say which documents should rank first, which should be excluded, and what specific facts or figures to pull from them."},}, "required": ["query", "objective"]},
    },
    {
        "name": "news_check",
        "description": "Search the live web for news from the last 30 days for things that change where to go: strikes, closed or congested emergency departments, fee changes, epidemics.",
        "input_schema": {"type": "object", "properties": {"query": {"type": "string"}, "objective": {"type": "string", "description": "Goal for this search turn; say which documents should rank first, which should be excluded, and what specific facts or figures to pull from them."},}, "required": ["query", "objective"]},
    },
    {
        "name": "read_page",
        "description": "Fetch the full, current text of one page live. Use on the pages you will cite for fees, opening hours and the recommended place.",
        "input_schema": {"type": "object", "properties": {"url": {"type": "string"}}, "required": ["url"]},
    },
    {
        "name": "submit_answer",
        "description": "Submit the final answer. Call exactly once, at the end.",
        "strict": True,
        "input_schema": {
            "type": "object",
            "additionalProperties": False,
            "required": ["urgency", "headline", "summary", "primary", "alternatives", "costs", "heads_up", "bring", "message_fi", "message_en"],
            "properties": {
                "urgency": {"type": "string", "enum": ["emergency", "today", "this_week", "routine"]},
                "headline": {"type": "string", "description": "One line: where to go, e.g. 'Book a nurse at FSHS Otaniemi tomorrow morning'."},
                "summary": {"type": "string", "description": "Two sentences max, why this is the right place for this person."},
                "primary": _OPTION,
                "alternatives": {"type": "array", "items": _OPTION},
                "costs": {"type": "array", "items": _CLAIM, "description": "Fees and refunds that apply to this person."},
                "heads_up": {"type": "array", "items": _CLAIM, "description": "Recent news that affects the advice. Empty if none."},
                "bring": {"type": "array", "items": _CLAIM, "description": "What to bring (Kela card, EHIC, passport, insurance), if a source says so."},
                "message_fi": {"type": "string"},
                "message_en": {"type": "string"},
            },
        },
    },
]

STEP_LABEL = {
    "search_official": lambda a: f"Searching {', '.join(a.get('domains') or ['official sites'])} for “{a.get('query', '')}”",
    "search_private": lambda a: f"Checking private clinics for “{a.get('query', '')}”",
    "news_check": lambda a: f"Checking this month's news for “{a.get('query', '')}”",
    "read_page": lambda a: f"Reading {sources.domain(a.get('url', ''))} live",
}


def _profile(case: dict) -> str:
    now = datetime.now(ZoneInfo("Europe/Helsinki"))
    city = case.get("city", "").strip()
    region = REGIONS.get(city)
    lines = [
        f"Now in Finland: {now:%A %d %B %Y, %H:%M}.",
        f"Status: {STATUSES.get(case.get('status'), case.get('status', 'unknown'))}.",
        f"City: {city or 'not given'}.",
    ]
    if region:
        lines.append(f"Public healthcare provider: {region['county']}. Likely domains: {', '.join(region['domains'])} (confirm).")
    for flag, label in (("kela_card", "Has a Kela card"), ("travel_insurance", "Has travel insurance"), ("ehic", "Has an EHIC card")):
        if case.get(flag):
            lines.append(label + ".")
    if case.get("status") in STATUS_HINTS:
        lines.append("Where to look first (hint, verify): " + STATUS_HINTS[case["status"]])
    flags = red_flags(case.get("problem", ""))
    if flags:
        lines.append(f"Red flags detected in the description ({', '.join(flags)}): set urgency to emergency and make calling 112 the main option.")
    lines.append(f"\nIn their words: {case.get('problem', '').strip()}")
    return "\n".join(lines)


def _claims(answer: dict):
    """Yields (path, claim) for every cited fact in the answer."""
    for opt_i, opt in enumerate([answer.get("primary") or {}] + list(answer.get("alternatives") or [])):
        for i, c in enumerate(opt.get("facts") or []):
            yield (("primary",) if opt_i == 0 else ("alternatives", opt_i - 1)) + ("facts", i), c
    for key in ("costs", "heads_up", "bring"):
        for i, c in enumerate(answer.get(key) or []):
            yield (key, i), c


def verify_answer(answer: dict, reg: sources.Registry) -> list[str]:
    """Marks each claim verified or not. Returns problems to send back to the model."""
    problems = []
    for path, c in _claims(answer):
        src = reg.get(c.get("source_id", ""))
        if src is None:
            c["verified"] = "missing"
            problems.append(f"{'/'.join(map(str, path))}: source_id {c.get('source_id')!r} does not exist.")
            continue
        c["verified"] = check(c.get("quote", ""), src.text)
        if c["verified"] == "missing":
            problems.append(f"{'/'.join(map(str, path))}: quote not found in {src.id} ({src.domain}): {c.get('quote', '')[:120]!r}")
    return problems


def _drop_unverified(answer: dict) -> int:
    dropped = 0
    for opt in [answer.get("primary") or {}] + list(answer.get("alternatives") or []):
        keep = [c for c in opt.get("facts") or [] if c.get("verified") != "missing"]
        dropped += len(opt.get("facts") or []) - len(keep)
        opt["facts"] = keep
    for key in ("costs", "heads_up", "bring"):
        keep = [c for c in answer.get(key) or [] if c.get("verified") != "missing"]
        dropped += len(answer.get(key) or []) - len(keep)
        answer[key] = keep
    return dropped


async def run(case: dict, on_event: Event = _noop) -> dict:
    t0 = time.time()
    reg = sources.Registry()
    flags = red_flags(case.get("problem", ""))
    if flags:
        await on_event({"type": "emergency", "flags": flags})

    model = llm.make(SYSTEM, TOOLS, _profile(case))
    answer, retried, step = None, False, 0

    for turn in range(MAX_TURNS):
        final = turn >= SEARCH_TURNS  # after this many rounds of research, only submit_answer is allowed
        calls, refused = await model.step(final=final)
        if refused:
            await on_event({"type": "error", "text": "The model declined this request. Try describing it differently."})
            break
        if not calls:
            model.nudge("Please finish by calling submit_answer.")
            continue

        results: list[tuple[str, str, bool] | None] = [None] * len(calls)
        work = []
        for i, call in enumerate(calls):
            if call.name == "submit_answer":
                answer = json.loads(json.dumps(call.input))  # deep copy; we add 'verified' fields
                problems = verify_answer(answer, reg)
                if problems and not retried:
                    retried = True
                    await on_event({"type": "note", "text": f"{len(problems)} quote(s) didn't match their page. Asking the agent to fix them."})
                    results[i] = (call.id, "Some quotes are not on the cited page. Copy them exactly from the source text, cite another source, "
                                  "or remove the claim. Then call submit_answer again.\n- " + "\n- ".join(problems), True)
                    answer = None
                else:
                    results[i] = (call.id, "Answer received.", False)
                continue
            step += 1
            label = STEP_LABEL.get(call.name, lambda a: call.name)(call.input)
            await on_event({"type": "step", "id": step, "tool": call.name, "label": label, "status": "running"})
            work.append((i, call, step, label))

        async def do(i, call, sid, label):
            try:
                if call.name not in STEP_LABEL:
                    raise ValueError(f"unknown tool {call.name}")
                data = await sources.run_tool(reg, call.name, dict(call.input))
                err = "error" in data
            except Exception as e:  # tool failures go back to the model, not up the stack
                data, err = {"error": f"{type(e).__name__}: {e}"[:300]}, True
            ids = [r["source_id"] for r in data.get("results", [])] or ([data["source_id"]] if "source_id" in data else [])
            await on_event({"type": "step", "id": sid, "tool": call.name, "label": label, "status": "error" if err else "done",
                            "sources": [{"id": s.id, "domain": s.domain, "title": s.title} for s in map(reg.get, ids) if s]})
            results[i] = (call.id, json.dumps(data, ensure_ascii=False), err)

        await asyncio.gather(*(do(*w) for w in work))
        note = None
        if answer is None and turn + 1 >= SEARCH_TURNS:
            note = "Research time is up. Call submit_answer now with what you have; leave sections empty rather than guessing."
        model.add_results(results, note)
        if answer is not None:
            break
    else:
        await on_event({"type": "error", "text": "The agent took too many steps. Try again or simplify the question."})

    if answer is None:
        return {"answer": None, "sources": reg.public()}

    dropped = _drop_unverified(answer)
    if flags:
        answer["urgency"] = "emergency"
    cited = {c["source_id"] for _, c in _claims(answer)}
    used = [s for s in reg.public() if s["id"] in cited]
    total = sum(1 for _ in _claims(answer))
    p_in, p_out = llm.PRICES.get(model.name, (0.0, 0.0))
    stats = {
        "seconds": round(time.time() - t0, 1),
        "claims": total,
        "verified": total,  # unverified ones were dropped
        "dropped": dropped,
        "exa_calls": reg.exa_calls,
        "exa_cost": round(reg.exa_cost, 4),
        "llm_cost": round(model.tokens_in / 1e6 * p_in + model.tokens_out / 1e6 * p_out, 4),
        "pages_seen": len(reg.by_url),
        "model": model.name,
    }
    out = {"answer": answer, "sources": used, "stats": stats, "red_flags": flags}
    await on_event({"type": "answer", **out})
    return out
