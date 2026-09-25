"""
Vaani NLP-pipeline evaluation harness.

Scores translate_customer_speech() against the gold set in test_cases.json:
  - Intent accuracy (overall, per language, per intent, code-mixed) + confusion pairs
  - Counter-routing accuracy (soft: the LLM suggests the counter)
  - Entity extraction precision / recall / F1 over annotated slots
  - Clarification: recall on ambiguous cases, false alarms on clear ones
  - Latency of the LLM stage (mean / P50 / P95)
  - Optional translation BLEU (--bleu) and BERTScore (--bertscore)

Scope: this feeds GOLD TEXT into the pipeline, bypassing Whisper. It measures
translation + intent + entities + routing given a correct transcript, not STT
(see run_stt_eval.py for that).

Usage:
  python run_eval.py                       # full run (real Groq calls, slow on free tier)
  python run_eval.py --limit 10 --delay 2  # smoke test
  python run_eval.py --lang tamil
  python run_eval.py --model qwen/qwen3.8-27b --out eval_results_qwen.json
  python run_eval.py --mock                # re-score saved results, no API calls (CI)
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, ".."))

NUMERIC_KEYS = {"amount", "monthly_income", "tenure_months"}


def _clean(s) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s).strip().lower())


def values_match(key: str, gold, pred) -> bool:
    from translate import clean_number
    if pred is None or str(pred).strip() == "":
        return False
    if key in NUMERIC_KEYS:
        return abs(clean_number(gold) - clean_number(pred)) < 1.0
    g, p = _clean(gold), _clean(pred)
    return bool(g) and (g == p or g in p or p in g)   # lenient containment for names / types


def score_entities(gold: dict, pred: dict) -> tuple[int, int, int]:
    """Slot-level, on the pipeline's canonical keys (it normalises aliases itself).
    TP = gold slot predicted with a matching value; FN = gold slot missing;
    FP = gold slot predicted with a wrong value. Extra predicted keys are not scored."""
    tp = fp = fn = 0
    for key, gold_val in gold.items():
        pred_val = pred.get(key)
        if pred_val is None or str(pred_val).strip() == "":
            fn += 1
        elif values_match(key, gold_val, pred_val):
            tp += 1
        else:
            fp += 1
    return tp, fp, fn


def prf(tp, fp, fn):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def pct(values, q):
    s = sorted(values)
    return s[min(len(s) - 1, int(q * len(s)))] if s else 0.0


def summarise(cases_by_id: dict, details: list, model: str) -> dict:
    scored = [d for d in details if "error" not in d]
    n = len(scored)
    if not n:
        raise SystemExit("No scored cases.")

    def acc(rows):
        return sum(r["intent_ok"] for r in rows) / len(rows) if rows else None

    by_lang, by_intent = defaultdict(list), defaultdict(list)
    for d in scored:
        by_lang[d["lang"]].append(d)
        by_intent[d["intent_expected"]].append(d)

    ent = [sum(d[k] for d in scored) for k in ("ent_tp", "ent_fp", "ent_fn")]
    ep, er, ef = prf(*ent)
    known = [d for d in scored if d.get("clarification_pred") is not None]
    ambiguous = [d for d in known if cases_by_id[d["id"]].get("expect_clarification")]
    clear = [d for d in known if not cases_by_id[d["id"]].get("expect_clarification")]
    mixed = [d for d in scored if cases_by_id[d["id"]].get("code_mixed")]
    original = [d for d in scored if d["id"] <= 60]
    orig_ent = [sum(d[k] for d in original) for k in ("ent_tp", "ent_fp", "ent_fn")]
    lat = [d["latency_s"] for d in scored if d.get("latency_s") is not None]
    confusions = Counter((d["intent_expected"], d["intent_pred"]) for d in scored if not d["intent_ok"])

    return {
        "model": model,
        "n_scored": n,
        "n_errors": len(details) - n,
        "intent_accuracy": acc(scored),
        "counter_accuracy": sum(d["counter_ok"] for d in scored) / n,
        "entity_precision": ep, "entity_recall": er, "entity_f1": ef,
        "entity_slots": dict(zip(("tp", "fp", "fn"), ent, strict=True)),
        "clarification_recall": (sum(d["clarification_pred"] for d in ambiguous) / len(ambiguous)) if ambiguous else None,
        "clarification_false_alarm_rate": (sum(d["clarification_pred"] for d in clear) / len(clear)) if clear else None,
        "code_mixed_intent_accuracy": acc(mixed),
        "original_60": {"n": len(original), "intent_accuracy": acc(original), "entity_f1": prf(*orig_ent)[2]},
        "latency_llm_stage": {"mean": statistics.mean(lat), "p50": pct(lat, .5), "p95": pct(lat, .95)} if lat else None,
        "per_language_intent": {k: {"correct": sum(r["intent_ok"] for r in v), "total": len(v)} for k, v in sorted(by_lang.items())},
        "per_intent": {k: {"correct": sum(r["intent_ok"] for r in v), "total": len(v)} for k, v in sorted(by_intent.items())},
        "top_confusions": [{"expected": e, "predicted": p, "count": c} for (e, p), c in confusions.most_common(10)],
        "note": "Gold-text input: STT (Whisper) is not included. Counter accuracy is a soft metric.",
    }


def print_summary(s: dict):
    print("\n" + "=" * 64)
    print(f"  RESULTS  model={s['model']}  ({s['n_scored']} scored, {s['n_errors']} errors)")
    print("=" * 64)
    print(f"  Intent accuracy        : {s['intent_accuracy']:.1%}")
    print(f"  Counter accuracy       : {s['counter_accuracy']:.1%}   [soft]")
    print(f"  Entity P / R / F1      : {s['entity_precision']:.3f} / {s['entity_recall']:.3f} / {s['entity_f1']:.3f}   {s['entity_slots']}")
    if s["clarification_recall"] is not None:
        print(f"  Clarification recall   : {s['clarification_recall']:.1%}   false alarms: {s['clarification_false_alarm_rate']:.1%}")
    if s["code_mixed_intent_accuracy"] is not None:
        print(f"  Code-mixed intent acc. : {s['code_mixed_intent_accuracy']:.1%}")
    o = s["original_60"]
    if o["n"]:
        print(f"  Original 60 cases      : intent {o['intent_accuracy']:.1%}, entity F1 {o['entity_f1']:.3f}")
    if s["latency_llm_stage"]:
        lat = s["latency_llm_stage"]
        print(f"  LLM latency mean/P50/P95: {lat['mean']:.2f} / {lat['p50']:.2f} / {lat['p95']:.2f}s")
    print("\n  Per-language intent accuracy:")
    for lang, v in s["per_language_intent"].items():
        print(f"    {lang:<10} {v['correct'] / v['total']:.0%}  ({v['correct']}/{v['total']})")
    print("\n  Per-intent accuracy:")
    for it, v in s["per_intent"].items():
        print(f"    {it:<24} {v['correct'] / v['total']:.0%}  ({v['correct']}/{v['total']})")
    if s["top_confusions"]:
        print("\n  Most common confusions (expected -> predicted):")
        for c in s["top_confusions"]:
            print(f"    {c['expected']:<24} -> {c['predicted']:<24} x{c['count']}")


def write_markdown(s: dict, path: str):
    lat = s["latency_llm_stage"] or {}
    lines = [
        "# Evaluation results",
        "",
        f"Model `{s['model']}` on {s['n_scored']} gold-text cases ({s['n_errors']} errored). "
        "Whisper is bypassed, so this measures the language pipeline given a correct transcript.",
        "Non-English cases were written by the author and are flagged for native-speaker review.",
        "",
        "| Metric | Value |",
        "|---|---:|",
        f"| Intent accuracy | {s['intent_accuracy']:.1%} |",
        f"| Counter routing accuracy (soft) | {s['counter_accuracy']:.1%} |",
        f"| Entity precision / recall / F1 | {s['entity_precision']:.2f} / {s['entity_recall']:.2f} / {s['entity_f1']:.2f} |",
    ]
    if s["clarification_recall"] is not None:
        lines.append(f"| Clarification recall (ambiguous requests) | {s['clarification_recall']:.0%} |")
        lines.append(f"| Clarification false-alarm rate | {s['clarification_false_alarm_rate']:.1%} |")
    if s["code_mixed_intent_accuracy"] is not None:
        lines.append(f"| Code-mixed (Hinglish) intent accuracy | {s['code_mixed_intent_accuracy']:.1%} |")
    if lat:
        lines.append(f"| LLM stage latency p50 / p95 | {lat['p50']:.2f}s / {lat['p95']:.2f}s |")
    lines += ["", "## Per language", "", "| Language | Intent accuracy | Cases |", "|---|---:|---:|"]
    lines += [f"| {k} | {v['correct'] / v['total']:.0%} | {v['total']} |" for k, v in s["per_language_intent"].items()]
    lines += ["", "## Per intent", "", "| Intent | Accuracy | Cases |", "|---|---:|---:|"]
    lines += [f"| {k} | {v['correct'] / v['total']:.0%} | {v['total']} |" for k, v in s["per_intent"].items()]
    if s["top_confusions"]:
        lines += ["", "## Most common confusions", "", "| Expected | Predicted | Count |", "|---|---|---:|"]
        lines += [f"| {c['expected']} | {c['predicted']} | {c['count']} |" for c in s["top_confusions"]]
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write("\n".join(lines) + "\n")


def detail_for(case: dict, result: dict, latency: float | None) -> dict:
    pred_entities = result.get("entities") or {}
    tp, fp, fn = score_entities(case.get("expected_entities", {}), pred_entities)
    return {
        "id": case["id"], "lang": case["source_lang"],
        "intent_expected": case["expected_intent"], "intent_pred": result.get("intent", "other"),
        "intent_ok": result.get("intent") == case["expected_intent"],
        "counter_expected": case["expected_counter"], "counter_pred": result.get("suggested_counter"),
        "counter_ok": result.get("suggested_counter") == case["expected_counter"],
        "entities_expected": case.get("expected_entities", {}), "entities_pred": pred_entities,
        "ent_tp": tp, "ent_fp": fp, "ent_fn": fn,
        "clarification_pred": result.get("needs_clarification"),   # None = not recorded (old runs)
        "english_pred": result.get("english_translation", ""),
        "latency_s": round(latency, 3) if latency is not None else None,
    }


async def run_live(cases: list, args) -> list:
    from translate import translate_customer_speech
    details = []
    for idx, case in enumerate(cases, 1):
        try:
            t0 = time.perf_counter()
            result = await translate_customer_speech(case["audio_text"], case["source_lang"])
            dt = time.perf_counter() - t0
        except Exception as e:
            print(f"[{idx}/{len(cases)}] id={case['id']} ERROR: {str(e)[:200]}")
            details.append({"id": case["id"], "error": str(e)[:500]})
            await asyncio.sleep(args.delay * 3)
            continue
        d = detail_for(case, result, dt)
        details.append(d)
        print(f"[{idx}/{len(cases)}] {'OK' if d['intent_ok'] else 'XX'} {case['source_lang']:<8} "
              f"exp={case['expected_intent']:<23} got={d['intent_pred']:<23} {dt:.2f}s", flush=True)
        await asyncio.sleep(args.delay)
    return details


def replay(cases_by_id: dict, path: str) -> tuple[list, str]:
    """Re-score saved predictions with the current scoring code (no API calls)."""
    with open(path, encoding="utf-8") as f:
        saved = json.load(f)
    details = []
    for d in saved["details"]:
        if "error" in d or d["id"] not in cases_by_id:
            continue
        result = {"intent": d["intent_pred"], "suggested_counter": d["counter_pred"],
                  "entities": d["entities_pred"], "needs_clarification": d.get("clarification_pred"),
                  "english_translation": d.get("english_pred", "")}
        details.append(detail_for(cases_by_id[d["id"]], result, d.get("latency_s")))
    return details, saved["summary"].get("model", "unknown")


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Vaani NLP evaluation harness")
    ap.add_argument("--lang", help="only this source language")
    ap.add_argument("--limit", type=int, help="only the first N cases")
    ap.add_argument("--delay", type=float, default=9.0,
                    help="seconds between calls; ~9s keeps one model under Groq's 8k tokens/min free tier")
    ap.add_argument("--model", help="override LLM_MODEL for this run")
    ap.add_argument("--out", default="eval_results.json", help="results file (in backend/eval/)")
    ap.add_argument("--markdown", default="RESULTS.md", help="markdown summary file; '' to skip")
    ap.add_argument("--mock", action="store_true", help="re-score an existing results file instead of calling the API")
    ap.add_argument("--bleu", action="store_true", help="corpus BLEU (needs sacrebleu)")
    ap.add_argument("--bertscore", action="store_true", help="BERTScore F1 (needs bert-score)")
    args = ap.parse_args()

    if args.model:
        os.environ["LLM_MODEL"] = args.model

    from dotenv import load_dotenv
    load_dotenv()

    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    if args.lang:
        cases = [c for c in cases if c["source_lang"] == args.lang]
    if args.limit:
        cases = cases[: args.limit]
    cases_by_id = {c["id"]: c for c in cases}
    out_path = os.path.join(HERE, args.out)

    if args.mock:
        details, model = replay(cases_by_id, out_path)
        print_summary(summarise(cases_by_id, details, model))
        return

    if not os.getenv("GROQ_API_KEY"):
        raise SystemExit("GROQ_API_KEY not set. Put it in .env or export it.")
    from translate import MODEL
    details = asyncio.run(run_live(cases, args))
    summary = summarise(cases_by_id, details, MODEL)

    scored = [d for d in details if "error" not in d]
    hyps = [d["english_pred"] for d in scored]
    refs = [cases_by_id[d["id"]]["expected_english"] for d in scored]
    if args.bleu:
        try:
            import sacrebleu
            summary["bleu"] = sacrebleu.corpus_bleu(hyps, [refs]).score
        except ImportError:
            print("(BLEU skipped: pip install sacrebleu)")
    if args.bertscore:
        try:
            from bert_score import score as bertscore
            summary["bertscore_f1"] = float(bertscore(hyps, refs, lang="en", verbose=False)[2].mean())
        except ImportError:
            print("(BERTScore skipped: pip install bert-score)")

    print_summary(summary)
    for key, name in (("bleu", "Translation BLEU"), ("bertscore_f1", "BERTScore F1")):
        if key in summary:
            print(f"  {name}: {summary[key]:.3f}")
    with open(out_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
    if args.markdown:
        write_markdown(summary, os.path.join(HERE, args.markdown))
        if "bleu" in summary:
            with open(os.path.join(HERE, args.markdown), "a", encoding="utf-8") as f:
                f.write(f"\nCorpus BLEU against the reference translations: {summary['bleu']:.1f}\n")
    print(f"\n  Results written to {out_path}")


if __name__ == "__main__":
    main()
