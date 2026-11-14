# The Internet Butler / Your Personal Assistant — by Exa

## The Challenge

Build an agent that takes tedious tasks in people's lives off their hands.

## Introduction

Everyone has pain points in their day to day which require hours of digging and research like checking whether a rent increase is legal, or finding out which benefits a family qualifies for, which vegan restaurant to pick for an anniversary date, and more. The answers exist, but they are buried across the web. Exa is the search engine built for AI. It can find, read and compare information from across the web and pull it back as structured data, so your agent can do the digging and the task can be handed off completely.

## The challenge

Develop a personal agent that helps people get stuff done. Your agent should find what matters across the web, work out what needs to happen and get the task as close to done as it can, leaving the final approval to the user if needed. **Demo on a real case.**

**Areas of interest:** General tasks. Examples: planning special occasions, handling daily living errands, rent, missed benefits, business information, travel disruption, etc.

## How we judge

- How well they use Exa to get information that could not have come from a model's training data alone
- How useful they are to a specific group of real people
- How clearly they show their sources
- Originality
- Whether the demo works on live queries, including ones the judges try themselves

## Judging criteria (from the Junction challenge page, 20% each)

| Criterion | What it means |
|---|---|
| **Use of Exa** (20%) | Use of Exa to retrieve information that could not have come from a model's training data alone |
| **Usefulness** (20%) | Usefulness to a specific group of real people |
| **Clarity** (20%) | Clarity in showing sources |
| **Originality** (20%) | How original the idea is |
| **Working implementation** (20%) | Whether the demo works on live queries, including ones the judges try themselves |

## Prizes

- **1st:** $2,500 cash, $5,000 Exa credits, Exa hoodie per person, Exa-branded TRMNL dashboard
- **2nd:** $1,500 cash, $3,000 Exa credits, Exa hoodie per person, Exa-branded macropad
- **3rd:** $500 cash, $1k Exa credits, Exa hoodie per person
- **Everyone:** $50 Exa credits

## About Exa

Exa is a search engine built for AI. It indexes the web by meaning, so AI applications can find information by describing what they need, and returns clean, structured content that models can use directly. Companies such as Cursor, Cognition, HubSpot and AWS use Exa to connect their products to the web. Exa is joining Junction to meet builders, see new ideas for what AI can do with access to the whole web, and keep supporting promising teams after the event.

## Resources

Every participant gets **$50 in Exa credits** and access to the full API for the event:

- **Search API** with fast, balanced and deep research modes
- **Contents API** for full page text, highlights, summaries and crawling a site's subpages
- Filter results by date, domain and category (news, research papers, companies, people, personal websites), request results as structured JSON, and retrieve past versions of web pages
- **Websets** for building verified lists of people, companies and opportunities
- **Monitors** for recurring searches
- Hosted **MCP server**, plus Python and JavaScript SDKs
- Demo gallery at **demos.exa.ai** with working examples to build from

Exa engineers are on site throughout the event for technical questions and project ideas, plus a Discord channel for async advice.

**Free $50 Exa credits:** `EXA50JUNCTION` (redeem at dashboard.exa.ai/billing)

---

# Hoito: our build

**Live: https://hoito.onrender.com** · Plan: [PLAN.md](PLAN.md) · Demo script and submission text: [DEMO.md](DEMO.md)

## Run it

```bash
cp .env.example .env        # then fill in EXA_API_KEY and OPENAI_API_KEY (or ANTHROPIC_API_KEY)
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/uvicorn server:app --reload --port 8020   # open http://localhost:8020
```

- Command line: `.venv/bin/python -m hoito --status exchange_student --city Espoo "ear pain since this morning"`
- Exa coverage check (Phase 0): `.venv/bin/python scripts/exa_coverage.py` → `notes/exa-coverage.md`
- Tests without keys: `.venv/bin/python -m pytest -q tests`
- Eval (costs about $0.15–0.30 per case): `.venv/bin/python eval/run.py` → `eval/results.md`
- Every live answer is saved in `recordings/`. Replay one without Wi-Fi or keys: `http://localhost:8020/?replay=<name>` (list: `/api/recordings`).
- Deploy: `render.yaml` (Render Blueprint, Docker). Set EXA_API_KEY and OPENAI_API_KEY in the dashboard.

## Layout

| Path | What |
|---|---|
| `hoito/agent.py` | Tool loop, answer schema, quote verification and retry |
| `hoito/llm.py` | Model back-ends: OpenAI (Chat Completions) or Claude, same interface |
| `hoito/sources.py` | Exa tools (official search, private clinics, news, live page read) and the source registry |
| `hoito/verify.py` | Quote checker: exact or near match, numbers must match exactly |
| `hoito/safety.py` | Red-flag rule (EN/FI/SV) that puts "Call 112" first |
| `hoito/config.py` | Seed domains, city → wellbeing services county, statuses |
| `server.py` | FastAPI: page, streaming `/api/ask`, recording and replay |
| `ui/index.html` | The one-page app |
