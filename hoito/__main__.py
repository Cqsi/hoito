"""Command line: python -m hoito --status exchange_student --city Espoo "ear pain since yesterday"."""
import argparse
import asyncio
import json

from .agent import run
from .config import STATUSES


async def _print(e: dict) -> None:
    if e["type"] == "step":
        mark = {"running": "…", "done": "✓", "error": "✗"}[e["status"]]
        extra = " " + " ".join(f"[{s['id']} {s['domain']}]" for s in e.get("sources", [])) if e["status"] != "running" else ""
        print(f"{mark} {e['label']}{extra}")
    elif e["type"] in ("note", "error"):
        print(f"! {e['text']}")
    elif e["type"] == "emergency":
        print(f"!!! Red flags: {', '.join(e['flags'])}. Call 112.")


def main() -> None:
    p = argparse.ArgumentParser(prog="hoito")
    p.add_argument("problem")
    p.add_argument("--status", choices=list(STATUSES), default="degree_student")
    p.add_argument("--city", default="Helsinki")
    p.add_argument("--kela-card", action="store_true")
    p.add_argument("--travel-insurance", action="store_true")
    p.add_argument("--json", action="store_true", help="print the full answer as JSON")
    a = p.parse_args()
    case = {"problem": a.problem, "status": a.status, "city": a.city, "kela_card": a.kela_card, "travel_insurance": a.travel_insurance}
    out = asyncio.run(run(case, _print))
    if not out.get("answer"):
        return
    if a.json:
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return
    ans = out["answer"]
    print(f"\n[{ans['urgency']}] {ans['headline']}\n{ans['summary']}")
    for opt in [ans["primary"], *ans["alternatives"]]:
        print(f"\n• {opt['title']} ({opt['kind']}): {opt['when']}")
        for c in opt["facts"]:
            print(f"    - {c['text']} [{c['source_id']}, {c['verified']}]")
    for key in ("costs", "heads_up", "bring"):
        if ans[key]:
            print(f"\n{key}:")
            for c in ans[key]:
                print(f"    - {c['text']} [{c['source_id']}, {c['verified']}]")
    print("\nSources:")
    for s in out["sources"]:
        print(f"  {s['id']} {s['domain']} – {s['title'][:70]} {'(live)' if s['live'] else ''}")
    print(f"\n{json.dumps(out['stats'])}")


if __name__ == "__main__":
    main()
