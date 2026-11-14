# Where do I go? Build plan

Working name: **Hoito** (Finnish for "care").

An international in Finland says who they are, where they are and what's wrong. Hoito tells them **where to go right now**, **what it costs today**, **how much Kela pays back**, and **what to say when they get there**. Every fact links to the official page it came from, fetched live.

It never diagnoses. It only routes people to the right place.

---

## 1. How we're judged (20% each) and how the demo proves it

| Criterion | Our answer | What the judge sees |
|---|---|---|
| **Use of Exa** for info beyond training data | 2026 client fees, opening hours, local wait times, this week's news (strikes, closed ERs), private clinic prices. All are searched live on official domains. | Each fact has a "fetched 4 min ago" stamp and the page's published date |
| **Usefulness** to a specific group | About 500k foreign-language speakers in Finland, plus visitors. The rules differ by status (student / employee / EU visitor / non-EU visitor), and that's where people get lost. | Three real personas in the demo, plus the judge's own case |
| **Clarity of sources** | Every claim carries a numbered chip → source page → **the exact quoted sentence**. The backend checks each quote against the fetched page text and drops claims it can't verify. | Click a chip: the quote is highlighted, with the link and date |
| **Originality** | Exa's demo gallery is all business tools (lead enrichment, recruiting, market monitoring). Nothing covers healthcare routing that depends on your status. | — |
| **Working on live queries** | Deployed at a public URL and phone-friendly. No canned answers; a live step trace shows the searches as they happen. | The judge types "I'm visiting from the US and have a fever in Helsinki" |

---

## 2. Users and what they get

**Who:** international degree and exchange students, foreign employees, people who just moved here, and short-term visitors. They mostly read English and don't know which of Finland's several healthcare systems applies to them.

**Input (one screen, under 20 seconds):**
- Status chips: `Degree student` · `Exchange student` · `Employee` · `Moved here, not working` · `EU visitor (EHIC)` · `Non-EU visitor`
- City (autocomplete, mapped to the regional health authority behind it)
- Problem in free text, any language
- Optional: "it's urgent", "I have a Kela card", "I have travel insurance"

**Output: one answer card**
1. **Emergency check first.** If the text mentions red-flag symptoms, the card's top line is "Call 112". This is a fixed rule written in code, not an LLM judgment.
2. **Go here:** the best option for this status, with name, address, opening hours today and phone or booking link.
3. **Cost:** the fee from today's published price list, plus the Kela refund if private.
4. **Other options:** for example the 116117 medical helpline, private clinics with prices, or the student health service (FSHS).
5. **Heads-up from the news:** for example "HUS emergency departments congested this week" or "strike affecting health centres on 18 Nov". Shown only if found.
6. **What to bring / what to say:** a drafted booking message or reception summary in **Finnish + English**, with a copy button and a phone-call link. The user sends or says it themselves.

---

## 3. Sources

Seed domains: verify each one in Phase 0, and let the agent discover regional sites with Exa.

| Need | Domains |
|---|---|
| Kela refunds, eligibility, EHIC | `kela.fi` |
| Student health (FSHS) | `yths.fi` |
| Regional public care (health centres, emergency, fees) | `hel.fi` (Helsinki), `hus.fi` (hospital district), other regions' sites **discovered by search** ("wellbeing services county" + city) |
| Medical helpline, emergency rules | `116117.fi` |
| Guides for internationals | `infofinland.fi` |
| National fee rules | `stm.fi`, `thl.fi` |
| Residence status → entitlement | `migri.fi` |
| Private prices and availability | `mehilainen.fi`, `terveystalo.com`, `pihlajalinna.fi` |
| News | Exa `category: "news"`, last 30 days, Finnish + English queries |

Many official pages are only in Finnish. The agent searches in **both** Finnish and English, quotes the original text, and shows a translation next to it.

---

## 4. Architecture

```
Browser (one page)  ──SSE──  FastAPI  ──  Claude agent (tool runner)
                                           │
                                           ├─ classify_case        (pure code: status + city → region, red flags)
                                           ├─ search_official      → Exa /search, includeDomains, highlights, maxAgeHours
                                           ├─ read_page            → Exa /contents, text, maxAgeHours=0 for fee/hours pages
                                           ├─ find_private_options → Exa /search on private-clinic domains, price pages
                                           ├─ news_check           → Exa /search category=news, startPublishedDate=-30d, userLocation=FI
                                           └─ submit_answer        → structured answer: claims[] each {text, source_id, quote}
                                                   │
                                           citation verifier (pure code): quote must appear in the fetched page text
```

**Stack:** Python 3.12, FastAPI + uvicorn, `exa-py`, `anthropic`. This matches the Valio project. Frontend: one static `index.html` (vanilla JS or a small Preact file), served by FastAPI.

**Claude:**
- Model `claude-opus-5-5` with adaptive thinking at effort `medium`.
- Uses the SDK tool runner (`client.beta.messages.tool_runner` + `@beta_tool`).
- Streams step events to the UI.
- Server-side refusal fallback turned on (`fallbacks: "default"`).
- If live latency is too slow, the main lever is switching to `claude-sonnet-5-5`. That's your call.

**Exa calls** (parameter names checked against the docs on 2026-11-14):
- `exa.search(query, type="auto", include_domains=[...], user_location="FI", contents={"highlights": ..., "max_age_hours": ...})` (Python SDK, snake_case). Confirm both keywords in Phase 0: the docs show `userLocation` only in REST, and don't state whether `maxAgeHours` sits inside `contents`.
- `exa.get_contents(urls, text=True, max_age_hours=0)` for pages where today's numbers matter. `max_age_hours=0` forces a fetch from the last 60 seconds.
- Use `type="lite"` (cheap, served from the index) for finding regional sites. Use `auto` for everything else. Avoid `deep` (4–15 s) unless a case gets stuck.
- Run searches in parallel. Exa allows 10 QPS for search and 100 for contents.
- Cost is roughly $0.05–0.10 in Exa per answer, so $50 covers about 500 test runs.

**Making the citations trustworthy:**
- Every claim in `submit_answer` must point to a fetched source and carry a quote of at most 25 words.
- The verifier normalises whitespace and checks that the quote appears in the page text. Claims that fail get one retry; if they fail again, they're dropped or shown as "unverified" in grey.
- The trace panel shows the share of claims verified, e.g. "12/12 claims verified".

**Caching:** cache Exa responses for 1 hour, keyed by query and domains. This keeps the live demo fast. Pages about fees and opening hours always skip the cache.

---

## 5. UI

One page that works at phone width:

- **Top:** the intake form (status chips, city, text box, "Find care" button).
- **While it works:** a live step list, e.g. "Searching kela.fi for refund rates…", "Reading hel.fi › health centres › Kallio…". Each step turns into a source chip once it returns. This is the main visual for both the "use of Exa" and "working implementation" criteria.
- **Answer card:** sections as in §2, with numbered chips `[1]`. Clicking a chip opens a side drawer with page title, domain, published and fetched dates, the highlighted quote, its translation, and "Open page".
- **Drafted message:** two tabs (Finnish / English), a copy button and a phone-call link.
- **Footer:** "Not medical advice. In an emergency call 112."

Visual style: calm, clinical and trustworthy. White background, one accent colour, large type, citation chips styled like footnotes.

---

## 6. Demo script (3 minutes)

1. **Exchange student, Espoo, Saturday 22:00, ear pain.**
   - Shows: is the student health service closed? → regional emergency or 116117 → fee today → Finnish message to read out.
2. **Software engineer, Tampere, employed, back pain for two weeks.**
   - Shows: occupational health first, then public care, then a private option with price and Kela refund.
3. **Judge's own case:** "I'm visiting from the US, fever, Helsinki."
   - Shows: private clinic price, what travel insurance needs, and the news heads-up if any.
4. Click any chip to show the quote, the date and the verified tick.

Backup: a screen recording of all three cases in case the venue Wi-Fi fails.

---

## 7. Evaluation (small, but real)

`eval/cases.yaml`: about 20 cases covering 6 statuses × 5 cities (Helsinki, Espoo, Vantaa, Tampere, Turku, Oulu) × urgency levels, each with the expected **route** (e.g. FSHS, health centre, occupational health, private, 112).

A script runs them all and reports:
- correct route
- share of claims verified
- median and p90 latency
- Exa + Claude cost per case

Targets: route correct ≥ 90%, claims verified ≥ 95%, median latency < 25 s.

---

## 8. Build order

| Phase | What | Time | Done when |
|---|---|---|---|
| 0 | API keys, `.env`, Exa smoke test on every seed domain (indexed? fresh? Finnish pages?) | 1.5 h | A table of which domains work, saved to `notes/exa-coverage.md` |
| 1 | Exa tool functions + `classify_case` + agent loop, working from the command line | 3 h | `python -m hoito "exchange student, Espoo, ear pain"` prints a cited answer |
| 2 | `submit_answer` schema + citation verifier + emergency rule | 2 h | Unverifiable claims get dropped; red-flag text returns 112 first |
| 3 | FastAPI SSE endpoint + one-page UI with step trace and chips | 4 h | The full flow works in a browser and on a phone |
| 4 | Eval cases + fixes | 2 h | Targets in §7 met or known gaps listed |
| 5 | Deploy to a public URL (Render or Fly), demo script, backup video, submission text | 2 h | A judge can open the link on their phone |
| Stretch | Exa Monitor: "notify me if ER congestion news appears for my city"; medication tab (idea #3) | 2 h each | — |

Total core: about 14.5 hours.

---

## 9. Risks

| Risk | Mitigation |
|---|---|
| Exa doesn't index some official `.fi` pages, or they're stale | Phase 0 finds this early. Fallback: `get_contents` on known URLs with `max_age_hours=0`, plus `subpages` crawl of the domain's health section |
| Private booking pages are JavaScript-only, so there's no "next free slot" | Show the price list and booking link instead. Don't promise live slots |
| Answer is too slow for a live demo | Parallel searches, `lite` for discovery, cache non-fee pages, stream steps so the wait feels active. Last resort: Sonnet 5.5 |
| Wrong fee or wrong route | The verifier blocks unquoted numbers; the eval set catches routing mistakes; the answer shows a date and source for every number |
| Medical safety | No diagnosis wording (enforced by the prompt and checked in the eval); emergency rule in code; 116117 always listed |
| Regional sites vary a lot | Region map in code for the 6 demo cities; the agent discovers others |

---

## 10. Questions for the Exa engineers on site

1. How well are `kela.fi`, `hel.fi`, `hus.fi` and `yths.fi` covered, and how often are they recrawled?
2. In the Python SDK, does `max_age_hours` go inside `contents=` for `search`? Is the keyword `user_location`?
3. Is `snapshotAsOf` (past page versions) available on the event credits? (Stretch: "fees changed since last year".)
4. Do they recommend a better pattern than search + get_contents for "fetch this exact official page live"?
