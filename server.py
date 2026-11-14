"""Web server: one page, one streaming endpoint.

Run: .venv/bin/uvicorn server:app --reload --port 8020
"""
import asyncio
import json
import os
import re
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from hoito import agent, llm
from hoito.config import REGIONS, STATUSES

UI = Path(__file__).resolve().parent / "ui"
# Every live run is saved here and can be replayed with ?replay=<name> (backup for bad venue Wi-Fi).
RECORDINGS = Path(os.getenv("HOITO_RECORDINGS", Path(__file__).resolve().parent / "recordings"))
app = FastAPI(title="Hoito")
_slots = asyncio.Semaphore(int(os.getenv("HOITO_MAX_PARALLEL", "6")))  # protects the API budget during judging


class Case(BaseModel):
    problem: str = Field(min_length=3, max_length=1500)
    status: str
    city: str = Field(max_length=60)
    kela_card: bool = False
    travel_insurance: bool = False
    ehic: bool = False
    replay: str | None = Field(default=None, max_length=80)


@app.get("/")
def index():
    return FileResponse(UI / "index.html")


@app.get("/api/health")
def health():
    return {"exa": bool(os.getenv("EXA_API_KEY")), "llm": llm.provider() != "none",
            "provider": llm.provider(), "model": llm.model_name()}


@app.get("/api/recordings")
def recordings():
    return sorted((p.stem for p in RECORDINGS.glob("*.jsonl")), reverse=True) if RECORDINGS.exists() else []


@app.get("/api/options")
def options():
    return {"statuses": STATUSES, "cities": sorted(REGIONS)}


@app.post("/api/ask")
async def ask(case: Case):
    if case.status not in STATUSES:
        return JSONResponse({"error": "unknown status"}, status_code=400)
    queue: asyncio.Queue = asyncio.Queue()
    log: list[dict] = []
    t0 = time.time()

    async def emit(e: dict) -> None:
        log.append({"t": round(time.time() - t0, 2), **e})
        await queue.put(e)

    async def replay(name: str):
        path = RECORDINGS / f"{re.sub(r'[^A-Za-z0-9_-]', '', name)}.jsonl"
        if not path.exists():
            await queue.put({"type": "error", "text": f"No recording called {name!r}."})
            return
        last = 0.0
        for line in path.read_text().splitlines()[1:]:
            e = json.loads(line)
            t = e.pop("t")
            await asyncio.sleep(min(t - last, 2.5) / 2)  # replay at double speed, long waits capped
            last = t
            await queue.put(e)

    async def work():
        try:
            if case.replay:
                await replay(case.replay)
                return
            async with _slots:
                await agent.run(case.model_dump(exclude={"replay"}), emit)
            if any(e["type"] == "answer" for e in log):
                RECORDINGS.mkdir(exist_ok=True)
                name = time.strftime("%Y%m%d-%H%M%S") + "-" + case.status
                header = json.dumps({"case": case.model_dump(exclude={"replay"})}, ensure_ascii=False)
                (RECORDINGS / f"{name}.jsonl").write_text("\n".join([header] + [json.dumps(e, ensure_ascii=False) for e in log]) + "\n")
        except Exception as e:
            await queue.put({"type": "error", "text": f"Something failed on our side ({type(e).__name__}). Please try again."})
            raise
        finally:
            await queue.put(None)

    task = asyncio.create_task(work())

    async def stream():
        yield ": open\n\n"
        while True:
            try:
                e = await asyncio.wait_for(queue.get(), timeout=15)
            except asyncio.TimeoutError:
                yield ": keep-alive\n\n"  # stops proxies from closing a quiet connection
                continue
            if e is None:
                break
            yield f"data: {json.dumps(e, ensure_ascii=False)}\n\n"
        yield "data: {\"type\": \"end\"}\n\n"

    return StreamingResponse(stream(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
