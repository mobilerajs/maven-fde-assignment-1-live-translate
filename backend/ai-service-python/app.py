"""
FDE · Assignment 1 · Python AI Service  (this is the real assignment)
=====================================================================
A small FastAPI service that translates English → Mexican Spanish with:
  - an LLM call            (lib/llm.py)
  - a two-tier cache       (lib/cache.py)  — memory + SQLite
  - structured logging     (lib/logger.py) — provided, wired for you

The Node gateway forwards the browser's requests here. You implement the
TODOs so the widget lights up. Run:

    python -m venv .venv && source .venv/bin/activate
    pip install -r requirements.txt
    cp .env.example .env          # then add your API key
    uvicorn app:app --reload --port 8000
"""
import asyncio
import os
import time

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from lib.cache import TwoTierCache, _key
from lib.llm import translate_text
from lib.logger import get_logger

load_dotenv()

MODEL = os.getenv("MODEL", "claude-sonnet-4-6")
DB_PATH = os.getenv("TRANSLATION_DB_PATH", "translations.db")
LLM_CONCURRENCY = int(os.getenv("LLM_CONCURRENCY", "8"))

app = FastAPI(title="FDE Live Translate — AI Service")
log = get_logger("ai-service")
cache = TwoTierCache(DB_PATH)

_inflight: dict[str, asyncio.Lock] = {}       # single-flight lock per cache key
_llm_sem = asyncio.Semaphore(LLM_CONCURRENCY)  # cap concurrent provider calls

# request/response shapes ----------------------------------------------------
class TranslateIn(BaseModel):
    text: str
    target: str = "es-MX"

class BatchIn(BaseModel):
    texts: list[str]
    target: str = "es-MX"


@app.exception_handler(RequestValidationError)
async def validation_to_400(request: Request, exc: RequestValidationError):
    # contract: invalid input is 400 (FastAPI's default would be 422)
    return JSONResponse(status_code=400, content={"error": "invalid input", "detail": exc.errors()})


@app.on_event("startup")
async def startup():
    await cache.init()
    log.info("ai_service_started", extra={"model": MODEL, "db": DB_PATH})


# --- core: translate one string --------------------------------------------
async def translate_one(text: str, target: str) -> dict:
    """Translate a single string, using the cache first.

    Returns a dict shaped exactly like the widget expects:
        {"translated": str, "cached": bool, "latencyMs": int, "model": str}
    """
    text = (text or "").strip()
    if not text:
        return {"translated": "", "cached": False, "latencyMs": 0, "model": MODEL}

    t0 = time.perf_counter()

    # Hot path: warm memory-tier hits never touch a lock.
    translated = cache.peek_memory(text, target)
    if translated is not None:
        latency = int((time.perf_counter() - t0) * 1000)
        return {"translated": translated, "cached": True, "latencyMs": latency, "model": MODEL}

    # Single-flight: identical (text, target) requests share one lock, so a
    # burst of duplicates triggers at most ONE LLM call — the rest wait and
    # are then served from the cache the leader just populated. (A waiter's
    # latencyMs includes that wait: it is honest wall time for that request.)
    key = _key(text, target)
    lock = _inflight.setdefault(key, asyncio.Lock())
    try:
        async with lock:
            cached_value = await cache.get(text, target)
            if cached_value is not None:
                translated, was_cached = cached_value, True
            else:
                async with _llm_sem:
                    translated = await translate_text(text, target, model=MODEL)
                await cache.set(text, target, translated, model=MODEL)
                was_cached = False
    finally:
        # Locks are only useful while a translation is in flight; drop the
        # entry once uncontended so _inflight stays bounded. Late arrivals
        # get a fresh lock and immediately re-check the (now warm) cache.
        if not lock.locked():
            _inflight.pop(key, None)

    latency = int((time.perf_counter() - t0) * 1000)
    return {"translated": translated, "cached": was_cached, "latencyMs": latency, "model": MODEL}


def _request_id(request: Request) -> str:
    return request.headers.get("x-request-id", "-")


@app.post("/translate")
async def translate(body: TranslateIn, request: Request):
    req_id = _request_id(request)
    try:
        result = await translate_one(body.text, body.target)
    except Exception as exc:  # provider/LLM/storage failure — fail LOUD, never echo the input
        log.error("translate_failed", extra={"requestId": req_id, "error": str(exc), "chars": len(body.text)})
        raise HTTPException(status_code=502, detail=f"translation failed: {exc}")
    log.info(
        "translate",
        extra={
            "requestId": req_id,
            "cached": result["cached"],
            "latencyMs": result["latencyMs"],
            "chars": len(body.text),
        },
    )
    return result


@app.post("/translate/batch")
async def translate_batch(body: BatchIn, request: Request):
    req_id = _request_id(request)
    t0 = time.perf_counter()
    # translate concurrently — a page's worth of strings shouldn't serialize.
    # return_exceptions=True means every task runs to completion (no orphaned
    # coroutines still holding locks/semaphore slots after a failure).
    results = await asyncio.gather(
        *[translate_one(t, body.target) for t in body.texts], return_exceptions=True
    )
    errors = [r for r in results if isinstance(r, BaseException)]
    if errors:
        log.error(
            "translate_batch_failed",
            extra={"requestId": req_id, "error": str(errors[0]), "failedItems": len(errors), "count": len(body.texts)},
        )
        raise HTTPException(status_code=502, detail=f"translation failed: {errors[0]}")
    latency = int((time.perf_counter() - t0) * 1000)
    # one structured line per translation (AGENTS.md), plus a batch summary
    for text, r in zip(body.texts, results):
        log.info(
            "translate",
            extra={"requestId": req_id, "cached": r["cached"], "latencyMs": r["latencyMs"], "chars": len(text)},
        )
    hits = sum(1 for r in results if r["cached"])
    log.info(
        "translate_batch",
        extra={"requestId": req_id, "count": len(results), "hits": hits, "latencyMs": latency},
    )
    # widget expects {results: [{translated, cached}], latencyMs}
    return {"results": [{"translated": r["translated"], "cached": r["cached"]} for r in results], "latencyMs": latency}


@app.get("/health")
async def health():
    return {"status": "ok", "model": MODEL, "cacheSize": await cache.size()}


@app.get("/stats")
async def stats():
    return await cache.stats()
