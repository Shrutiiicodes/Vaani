"""
Concurrent load test for /api/customer-speak. Makes REAL Groq calls.

Fires N simultaneous customer turns (fresh session each) at every concurrency
level and reports time-to-transcript (first SSE event) and total time.
Also works against the pre-streaming JSON endpoint, where only total is known.

With no --clip it synthesises a Hindi home-loan request with edge-tts, which
exercises the full path: STT -> LLM -> EMI calculation -> translated readout -> TTS.

Keep levels modest on Groq's free tier (8k tokens/min per model, and one turn is
~1.5k tokens); beyond that you are measuring Groq's 429 back-off, not the app.

Usage:
  python backend/eval/load_test.py --user admin --password ... --levels 1 5
"""
import argparse
import asyncio
import os
import sys
import time
import uuid

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

CLIP_TEXT = "मुझे बीस साल के लिए पचास लाख का होम लोन चाहिए"
DEFAULT_CLIP = os.path.join(HERE, "audio", "hindi_home_loan.mp3")


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else float("nan")


async def ensure_clip(path: str) -> bytes:
    if not os.path.exists(path):
        from tts import _edge
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "wb") as f:
            f.write(await _edge(CLIP_TEXT, "hi-IN-SwaraNeural"))
    with open(path, "rb") as f:
        return f.read()


async def one_turn(client: httpx.AsyncClient, headers: dict, clip: bytes, filename: str) -> dict:
    start = time.perf_counter()
    first = None
    body = ""
    async with client.stream(
        "POST", "/api/customer-speak", headers=headers,
        data={"session_id": str(uuid.uuid4())},
        files={"audio": (filename, clip, "audio/mpeg")},
    ) as r:
        async for chunk in r.aiter_text():
            body += chunk
            if first is None and "event: transcript" in body:
                first = time.perf_counter() - start
        status = r.status_code
    total = time.perf_counter() - start
    streamed_ok = "event: done" in body and "event: error" not in body
    json_ok = body.lstrip().startswith("{") and '"original_text"' in body   # old non-streaming API
    return {"ok": status == 200 and (streamed_ok or json_ok), "status": status,
            "ttft": first, "total": total, "body": body[:200]}


async def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="http://localhost:8000")
    ap.add_argument("--user", default="admin")
    ap.add_argument("--password", required=True)
    ap.add_argument("--clip", default=DEFAULT_CLIP)
    ap.add_argument("--levels", type=int, nargs="+", default=[1, 5])
    ap.add_argument("--pause", type=float, default=65, help="seconds between levels (Groq per-minute limits)")
    args = ap.parse_args()

    clip = await ensure_clip(args.clip)
    async with httpx.AsyncClient(base_url=args.url, timeout=180) as client:
        r = await client.post("/api/login", json={"username": args.user, "password": args.password})
        r.raise_for_status()
        headers = {"Authorization": f"Bearer {r.json()['access_token']}"}

        rows = []
        for i, n in enumerate(args.levels):
            if i:
                await asyncio.sleep(args.pause)
            results = await asyncio.gather(*(one_turn(client, headers, clip, os.path.basename(args.clip))
                                             for _ in range(n)))
            good = [x for x in results if x["ok"]]
            for bad in (x for x in results if not x["ok"]):
                print(f"  failed: status={bad['status']} body={bad['body']!r}")
            ttft = [x["ttft"] for x in good if x["ttft"] is not None]
            total = [x["total"] for x in good]
            rows.append((n, len(good), pct(ttft, .5), pct(ttft, .95), pct(total, .5), pct(total, .95)))
            print(f"N={n}: {len(good)}/{n} ok")

    print("\n| Concurrent | OK | Transcript p50 | Transcript p95 | Total p50 | Total p95 |")
    print("|---:|---:|---:|---:|---:|---:|")
    for n, ok, t50, t95, a50, a95 in rows:
        print(f"| {n} | {ok}/{n} | {t50:.2f}s | {t95:.2f}s | {a50:.2f}s | {a95:.2f}s |")


if __name__ == "__main__":
    asyncio.run(main())
