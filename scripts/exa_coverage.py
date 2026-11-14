"""Phase 0: does Exa index the sites Hoito depends on, and can it fetch them live?

Run: .venv/bin/python scripts/exa_coverage.py   → writes notes/exa-coverage.md
"""
import asyncio
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from hoito import sources  # noqa: E402
from hoito.config import OFFICIAL, PRIVATE, REGIONS  # noqa: E402

PROBES = {
    "kela.fi": "doctor visit reimbursement private clinic",
    "yths.fi": "exchange students health care fee",
    "116117.fi": "when to call medical helpline",
    "infofinland.fi": "health services for foreigners emergency",
    "hus.fi": "emergency department päivystys",
    "stm.fi": "asiakasmaksut 2026",
    "thl.fi": "hoitoonpääsy terveyskeskus",
    "migri.fi": "residence permit health insurance",
    "suomi.fi": "health centre",
    **{d: "health centre fees opening hours" for d in PRIVATE},
}
for city, r in REGIONS.items():
    for d in r["domains"]:
        PROBES.setdefault(d, f"terveysasema päivystys {city}")


async def probe(d: str, q: str) -> dict:
    t = time.time()
    try:
        resp = await sources.exa_call("search", q, type="auto", include_domains=[d], user_location="FI",
                                            contents={"highlights": True})
        rs = resp.results
        row = {"domain": d, "results": len(rs), "newest": max((r.published_date or "")[:10] for r in rs) if rs else "",
               "sample": rs[0].url if rs else "", "secs": round(time.time() - t, 1)}
    except Exception as e:
        return {"domain": d, "results": -1, "newest": "", "sample": f"ERROR {e}"[:90], "secs": 0, "live": ""}
    if row["sample"]:
        t = time.time()
        try:
            c = await sources.exa_call("get_contents", [row["sample"]], text={"max_characters": 2000}, max_age_hours=0,
                                                    livecrawl_timeout=12000)
            row["live"] = f"ok {round(time.time() - t, 1)}s" if c.results and c.results[0].text else "empty"
        except Exception as e:
            row["live"] = f"fail: {e}"[:40]
    else:
        row["live"] = ""
    return row


async def main() -> None:
    rows = await asyncio.gather(*(probe(d, q) for d, q in PROBES.items()))
    lines = ["# Exa coverage of Hoito's sources", "", f"Run {time.strftime('%Y-%m-%d %H:%M')}.", "",
             "| Domain | Results | Newest published | Search s | Live fetch | Sample |", "|---|---|---|---|---|---|"]
    for r in sorted(rows, key=lambda r: (-r["results"], r["domain"])):
        lines.append(f"| {r['domain']} | {r['results']} | {r['newest']} | {r['secs']} | {r['live']} | {r['sample']} |")
    out = Path(__file__).resolve().parent.parent / "notes" / "exa-coverage.md"
    out.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
