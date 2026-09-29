"""
End-to-end check: from audio to intent.

Takes the Whisper transcripts saved by `run_stt_eval.py --hint` for the banking clips
(clean synthetic and noisy), runs each through the full language pipeline, and scores
the intent against the test case the clip was made from. This is the number that
matters for a branch: does the app still understand the request after speech
recognition errors?

Usage:
  python backend/eval/run_stt_eval.py --hint     # first, to produce stt_results_hint.json
  python backend/eval/run_e2e_eval.py
"""
import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))


async def run(args):
    from translate import MODEL, translate_customer_speech

    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)}
    with open(os.path.join(HERE, args.stt_results), encoding="utf-8") as f:
        rows = [r for r in json.load(f) if r.get("case_id") in cases]

    results = []
    for i, r in enumerate(rows, 1):
        case = cases[r["case_id"]]
        out = await translate_customer_speech(r["hypothesis"] or "", r["detected"] or r["language"])
        ok = out["intent"] == case["expected_intent"]
        results.append({"source": r["source"], "language": r["language"], "case_id": case["id"],
                        "cer": r["cer"], "expected": case["expected_intent"], "predicted": out["intent"], "ok": ok})
        print(f"[{i}/{len(rows)}] {'OK' if ok else 'XX'} {r['source'][:22]:<22} {r['language']:<9} "
              f"CER={r['cer']:.2f} exp={case['expected_intent']:<22} got={out['intent']}", flush=True)
        await asyncio.sleep(args.delay)

    by = defaultdict(list)
    for x in results:
        by[x["source"]].append(x)
    lines = ["# End-to-end results: audio to intent", "",
             f"Whisper large-v3 with the language hint, then `{MODEL}`. Banking clips only; each is scored "
             "against the intent of the test case it was voiced from.", "",
             "| Clip set | Clips | Mean CER | Intent accuracy |", "|---|---:|---:|---:|"]
    for source, xs in sorted(by.items()):
        lines.append(f"| {source} | {len(xs)} | {sum(x['cer'] for x in xs) / len(xs):.1%} | "
                     f"{sum(x['ok'] for x in xs)}/{len(xs)} ({sum(x['ok'] for x in xs) / len(xs):.0%}) |")
    misses = [x for x in results if not x["ok"]]
    if misses:
        lines += ["", "## Misses", "", "| Clip set | Language | Case | Expected | Predicted | CER |", "|---|---|---:|---|---|---:|"]
        lines += [f"| {x['source']} | {x['language']} | {x['case_id']} | {x['expected']} | {x['predicted']} | {x['cer']:.0%} |"
                  for x in misses]
    report = "\n".join(lines) + "\n"
    print("\n" + report)
    with open(os.path.join(HERE, "E2E_RESULTS.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(report)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Audio-to-intent evaluation")
    ap.add_argument("--stt-results", default="stt_results_hint.json")
    ap.add_argument("--delay", type=float, default=9.0, help="seconds between LLM calls (Groq free tier)")
    args = ap.parse_args()
    from dotenv import load_dotenv
    load_dotenv()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
