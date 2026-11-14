# Demo script and submission

## Before the demo

1. Open https://hoito.onrender.com on a phone and on the laptop a few minutes early (the free plan sleeps after 15 idle minutes). Check that the pill top right says **Live · Exa + GPT**.
2. Run the three demo cases once, so Exa's cache is warm and you have recordings to fall back on.
3. If the venue Wi-Fi fails: open `/?replay=<recording name>` (names at `/api/recordings`). It replays a real earlier run.

## The 3-minute demo

**0:00 The problem (20 s)**
"Finland has about half a million foreign-language speakers and more visitors every year. If you get sick here, the right door depends on who you are: a student, an employee, an EU visitor or a tourist each go to a different place and pay different fees. That information exists, but it's spread across Finnish-language sites from Kela, 21 regional health authorities and private clinics."

**0:20 Case 1, live (60 s)**: tap the example *Exchange student, ear pain on Saturday night*.
- Point at the step list: "These are real Exa searches running now on kela.fi, the student health service, the Espoo region's site and this month's news."
- Answer: where to go tonight, today's fee, and the Finnish message to read out at reception.
- Click a citation chip: "Every fact has the exact sentence from the page. Our code checks that the sentence is actually on the page; if it isn't, the fact is dropped. 'See it on the page' highlights it on the live site."

**1:20 Hand it to a judge (60 s)**: "Type your own case." Suggest: *"I'm visiting from the US, fever, Helsinki."*

**2:20 Why it's trustworthy (30 s)**
- The footer line: "N of N facts matched word-for-word on their source page".
- The "Call 112" rule is plain code, not the model: type "chest pain" to show it.

**2:50 Close (10 s)**
"Hoito: where to go, what it costs and what to say, from the live web, with a quote for every fact."

## Submission text

**Hoito: where do I go?**

Try it: https://hoito.onrender.com · Code: https://github.com/Cqsi/hoito

Healthcare in Finland for internationals. Tell Hoito who you are (student, employee, EU or non-EU visitor), where you are and what's wrong, in any language. It tells you where to go right now, what it costs today, what Kela pays back, and gives you a message in Finnish and English to read out at reception.

**How it uses Exa:** an LLM agent (GPT-4.1 via function calling) plans the searches. Exa's Search API runs them on official domains (Kela, the student health service, 116117, InfoFinland, HUS and each regional wellbeing services county), on private clinic chains, and on news from the last 30 days, using domain filters, Finnish location and date filters. The Contents API then fetches the pages it will cite live (`maxAgeHours: 0`), so fees and opening hours are today's, not what a model remembers.

**How it shows sources:** every fact carries a numbered citation with the exact sentence from the page, in its original language. Before anything is shown, our code checks each quote against the fetched page text; numbers must match exactly. Quotes that don't match go back to the agent once to be fixed, then are dropped. "See it on the page" opens the source with the sentence highlighted.

**Who it's for:** international students, workers and visitors in Finland, who face different rules depending on their status and mostly can't read the Finnish-only pages.

**Tested:** on 16 realistic cases across 6 statuses and 8 cities, Hoito answered all 16 and picked the right place every time. All 88 cited facts matched word-for-word on their source page. A typical answer takes 16 s and costs about $0.17 (Exa + OpenAI). Full table: `eval/results.md`.

**Safety:** Hoito routes and never diagnoses. A fixed rule (English, Finnish and Swedish) puts "Call 112" first for red-flag symptoms.

**Stack:** Python, FastAPI, Exa (`exa-py`), OpenAI GPT-4.1 with function calling (Claude also supported), and a single-page web app.
