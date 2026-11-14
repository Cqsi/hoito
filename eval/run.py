"""Runs every case in eval/cases.yaml and writes eval/results.md.

Run: .venv/bin/python eval/run.py [--only id1,id2] [--parallel 4]
Costs money: about $0.15-0.30 per case (Exa + Claude).
"""
import argparse
import asyncio
import json
import statistics
import sys
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from hoito.agent import run  # noqa: E402


async def one(case: dict, sem: asyncio.Semaphore) -> dict:
    async with sem:
        t = time.time()
        try:
            out = await run({k: case.get(k) for k in ("problem", "status", "city", "kela_card", "travel_insurance", "ehic")})
        except Exception as e:
            return {"id": case["id"], "ok": False, "error": f"{type(e).__name__}: {e}"[:200], "secs": round(time.time() - t, 1)}
    ans = out.get("answer")
    if not ans:
        return {"id": case["id"], "ok": False, "error": "no answer", "secs": round(time.time() - t, 1)}
    st = out["stats"]
    runs = ROOT / "eval" / "runs"
    runs.mkdir(exist_ok=True)
    (runs / f"{case['id']}.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
    return {"id": case["id"], "ok": True, "kind": ans["primary"]["kind"], "route_ok": ans["primary"]["kind"] in case["expect"],
            "headline": ans["headline"], "claims": st["claims"], "dropped": st["dropped"], "secs": st["seconds"],
            "cost": st["exa_cost"] + st["llm_cost"], "exa_calls": st["exa_calls"], "sources": len(out["sources"])}


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--only")
    p.add_argument("--parallel", type=int, default=4)
    a = p.parse_args()
    cases = yaml.safe_load((ROOT / "eval" / "cases.yaml").read_text())
    if a.only:
        cases = [c for c in cases if c["id"] in a.only.split(",")]
    sem = asyncio.Semaphore(a.parallel)
    rows = await asyncio.gather(*(one(c, sem) for c in cases))

    done = [r for r in rows if r["ok"]]
    claims = sum(r["claims"] for r in done)
    dropped = sum(r["dropped"] for r in done)
    secs = sorted(r["secs"] for r in done)
    lines = ["# Eval results", "", f"Run {time.strftime('%Y-%m-%d %H:%M')}, {len(rows)} cases.", ""]
    if done:
        lines += [
            f"- Answered: **{len(done)}/{len(rows)}**",
            f"- Route correct: **{sum(r['route_ok'] for r in done)}/{len(done)}**",
            f"- Claims verified on their page: **{claims}/{claims + dropped}** ({dropped} dropped by the verifier)",
            f"- Latency: median **{statistics.median(secs):.0f} s**, slowest {secs[-1]:.0f} s",
            f"- Cost per case: median **${statistics.median(r['cost'] for r in done):.2f}**",
            "",
        ]
    lines += ["| Case | Route | Kind | Claims | Dropped | Sources | Secs | $ | Headline |", "|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        if r["ok"]:
            lines.append(f"| {r['id']} | {'✓' if r['route_ok'] else '✗'} | {r['kind']} | {r['claims']} | {r['dropped']} | {r['sources']} | {r['secs']} | {r['cost']:.2f} | {r['headline']} |")
        else:
            lines.append(f"| {r['id']} | ✗ | – | – | – | – | {r['secs']} | – | {r['error']} |")
    (ROOT / "eval" / "results.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    asyncio.run(main())
