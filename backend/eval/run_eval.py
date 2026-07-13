"""
Vaani NLP-pipeline evaluation harness.

Scores translate_customer_speech() against a gold-standard test set:
  - Intent classification accuracy (overall / per-language / per-intent)
  - Counter-routing accuracy (soft metric — see README)
  - Entity extraction Precision / Recall / F1 over annotated slots
  - Follow-up clarification detection
  - Latency (mean / P50 / P95)  [LLM stage only — STT/TTS are NOT included]
  - Optional: translation BLEU (--bleu) and BERTScore (--bertscore)

IMPORTANT — what this measures:
  This feeds GOLD TEXT directly into translate_customer_speech(), bypassing the
  Whisper STT stage. So the numbers reflect translation + intent + entity +
  routing quality GIVEN a correct transcript. It does NOT measure STT accuracy.
  Be honest about that scope when you quote a number.

Requires GROQ_API_KEY (real Groq calls are made). Runs sequentially with a delay
to stay under free-tier rate limits.

Usage:
  python run_eval.py                      # full run, default delay
  python run_eval.py --lang hindi         # only one language
  python run_eval.py --limit 10           # first N cases (smoke test)
  python run_eval.py --delay 2.0          # slow down for rate limits
  python run_eval.py --bleu               # add corpus BLEU (needs sacrebleu)
  python run_eval.py --bertscore          # add BERTScore F1 (needs bert-score)
  python run_eval.py --strict-entities    # count extra predicted slots as FP
"""
import argparse
import asyncio
import json
import os
import re
import statistics
import sys
import time
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv

load_dotenv()  # picks up backend/.env or repo-root .env if present

HERE = os.path.dirname(os.path.abspath(__file__))

# Keys we treat as monetary → compared numerically via clean_number
AMOUNT_KEYS = {"amount", "loan_amount", "deposit_amount", "principal", "income", "p"}

# Alias map: canonical gold key -> alternate keys the LLM may emit.
# Mirrors the aliasing already used in translate.py so scoring stays fair.
ENTITY_ALIASES = {
    "full_name": ["name", "customer_name", "applicant_name"],
    "amount": ["loan_amount", "deposit_amount", "loan_value", "principal", "deposit_value"],
    "tenure_months": ["tenure", "duration", "period", "years", "months"],
    "mobile": ["phone", "contact", "mobile_number"],
    "account_type": ["acct_type", "account"],
    "loan_type": ["loan_category"],
    "nominee_relation": ["relation", "relationship"],
    "nominee_name": ["nominee"],
    "account_number": ["acc_no", "acct_number", "account_no"],
}


def _norm_key(k: str) -> str:
    return str(k).strip().lower().replace(" ", "_")


def _resolve(gold_key: str, pred: dict):
    """Return the predicted value for a gold key, checking aliases. None if absent."""
    gk = _norm_key(gold_key)
    npred = {_norm_key(k): v for k, v in pred.items()}
    if gk in npred:
        return npred[gk]
    for alt in ENTITY_ALIASES.get(gk, []):
        if _norm_key(alt) in npred:
            return npred[_norm_key(alt)]
    return None


def _values_match(gold_key: str, gold_val, pred_val) -> bool:
    if pred_val is None or str(pred_val).strip() == "":
        return False
    gk = _norm_key(gold_key)
    if gk in AMOUNT_KEYS or gk == "amount":
        from translate import clean_number
        return abs(clean_number(gold_val) - clean_number(pred_val)) < 1.0
    if gk in ("tenure_months",):
        from translate import clean_number
        # accept months given as-is; be lenient (e.g. "20 years" handled upstream sometimes)
        gv, pv = clean_number(gold_val), clean_number(pred_val)
        return gv == pv or (gv > 0 and (abs(gv - pv) < 1.0 or abs(gv - pv * 12) < 1.0 or abs(gv * 12 - pv) < 1.0))

    def clean_str(s):
        return re.sub(r"[^a-z0-9]", "", str(s).strip().lower())

    g, p = clean_str(gold_val), clean_str(pred_val)
    if not g:
        return False
    return g == p or g in p or p in g  # lenient containment for names/types


def score_entities(gold: dict, pred: dict, strict: bool):
    """Slot-level TP/FP/FN. See README for the exact definition.
    Non-strict (default): only annotated gold slots are scored.
      TP = gold slot predicted with matching value
      FN = gold slot missing/empty in pred
      FP = gold slot predicted with a WRONG non-empty value
    Strict: additionally counts predicted keys NOT in gold as FP.
    """
    tp = fp = fn = 0
    for gk, gv in gold.items():
        pv = _resolve(gk, pred)
        if pv is None or str(pv).strip() == "":
            fn += 1
        elif _values_match(gk, gv, pv):
            tp += 1
        else:
            fp += 1
    if strict:
        # keys predicted that map to no gold slot
        gold_norm = {_norm_key(k) for k in gold}
        gold_norm |= {_norm_key(a) for k in gold for a in ENTITY_ALIASES.get(_norm_key(k), [])}
        for pk, pv in pred.items():
            if str(pv).strip() == "":
                continue
            if _norm_key(pk) not in gold_norm:
                fp += 1
    return tp, fp, fn


def prf(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) else 0.0
    r = tp / (tp + fn) if (tp + fn) else 0.0
    f = 2 * p * r / (p + r) if (p + r) else 0.0
    return p, r, f


async def evaluate(args):
    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)

    if args.lang:
        cases = [c for c in cases if c["source_lang"] == args.lang]
    if args.limit:
        cases = cases[: args.limit]
    if not cases:
        print("No cases match the filter.")
        return

    if not os.getenv("GROQ_API_KEY"):
        print("ERROR: GROQ_API_KEY not set. Put it in backend/.env or export it.")
        sys.exit(1)

    from translate import translate_customer_speech

    intent_ok = 0
    counter_ok = 0
    ent_tp = ent_fp = ent_fn = 0
    clar_ok = clar_total = 0
    latencies = []
    per_lang = defaultdict(lambda: [0, 0])      # lang -> [intent_correct, total]
    per_intent = defaultdict(lambda: [0, 0])    # intent -> [correct, total]
    details = []
    hypotheses, references = [], []             # for BLEU/BERTScore

    for idx, case in enumerate(cases, 1):
        try:
            t0 = time.perf_counter()
            result = await translate_customer_speech(case["audio_text"], case["source_lang"])
            dt = time.perf_counter() - t0
        except Exception as e:
            print(f"[{idx}/{len(cases)}] id={case['id']} ERROR: {e}")
            details.append({"id": case["id"], "error": str(e)})
            await asyncio.sleep(args.delay)
            continue

        latencies.append(dt)
        pred_intent = result.get("intent", "other")
        pred_counter = result.get("suggested_counter")
        pred_entities = result.get("entities", {}) or {}

        i_ok = pred_intent == case["expected_intent"]
        c_ok = pred_counter == case["expected_counter"]
        intent_ok += i_ok
        counter_ok += c_ok
        per_lang[case["source_lang"]][0] += i_ok
        per_lang[case["source_lang"]][1] += 1
        per_intent[case["expected_intent"]][0] += i_ok
        per_intent[case["expected_intent"]][1] += 1

        tp, fp, fn = score_entities(case.get("expected_entities", {}), pred_entities, args.strict_entities)
        ent_tp += tp; ent_fp += fp; ent_fn += fn

        if case.get("expect_clarification"):
            clar_total += 1
            clar_ok += bool(result.get("needs_clarification"))

        hypotheses.append(result.get("english_translation", ""))
        references.append(case["expected_english"])

        details.append({
            "id": case["id"], "lang": case["source_lang"],
            "intent_expected": case["expected_intent"], "intent_pred": pred_intent, "intent_ok": i_ok,
            "counter_expected": case["expected_counter"], "counter_pred": pred_counter, "counter_ok": c_ok,
            "entities_expected": case.get("expected_entities", {}), "entities_pred": pred_entities,
            "ent_tp": tp, "ent_fp": fp, "ent_fn": fn,
            "english_pred": result.get("english_translation", ""),
            "latency_s": round(dt, 3),
        })

        flag = "OK " if i_ok else "XX "
        print(f"[{idx}/{len(cases)}] {flag} {case['source_lang']:<8} "
              f"exp={case['expected_intent']:<22} got={pred_intent:<22} {dt:.2f}s")
        await asyncio.sleep(args.delay)

    n = len([d for d in details if "error" not in d])
    if n == 0:
        print("\nAll cases errored — check API key / rate limits.")
        return

    ep, er, ef = prf(ent_tp, ent_fp, ent_fn)
    lat_sorted = sorted(latencies)
    p50 = statistics.median(lat_sorted)
    p95 = lat_sorted[min(len(lat_sorted) - 1, int(0.95 * len(lat_sorted)))]

    print("\n" + "=" * 60)
    print(f"  RESULTS  ({n} cases scored)")
    print("=" * 60)
    print(f"  Intent accuracy   : {intent_ok/n:.1%}   ({intent_ok}/{n})")
    print(f"  Counter accuracy  : {counter_ok/n:.1%}   ({counter_ok}/{n})   [soft — LLM-suggested]")
    print(f"  Entity  Precision : {ep:.3f}")
    print(f"  Entity  Recall    : {er:.3f}")
    print(f"  Entity  F1        : {ef:.3f}   (slots: tp={ent_tp} fp={ent_fp} fn={ent_fn})")
    if clar_total:
        print(f"  Clarification det.: {clar_ok}/{clar_total} ambiguous cases flagged")
    print(f"  Latency mean/P50/P95 (LLM stage): {statistics.mean(latencies):.2f} / {p50:.2f} / {p95:.2f}s")

    print("\n  Per-language intent accuracy:")
    for lang, (ok, tot) in sorted(per_lang.items()):
        print(f"    {lang:<10} {ok/tot:.0%}  ({ok}/{tot})")

    print("\n  Per-intent accuracy:")
    for it, (ok, tot) in sorted(per_intent.items()):
        print(f"    {it:<24} {ok/tot:.0%}  ({ok}/{tot})")

    summary = {
        "n_scored": n,
        "intent_accuracy": intent_ok / n,
        "counter_accuracy": counter_ok / n,
        "entity_precision": ep, "entity_recall": er, "entity_f1": ef,
        "entity_slots": {"tp": ent_tp, "fp": ent_fp, "fn": ent_fn},
        "latency_llm_stage": {"mean": statistics.mean(latencies), "p50": p50, "p95": p95},
        "per_language_intent": {k: {"correct": v[0], "total": v[1]} for k, v in per_lang.items()},
        "per_intent": {k: {"correct": v[0], "total": v[1]} for k, v in per_intent.items()},
        "note": "LLM-stage only; STT (Whisper) not included. Counter accuracy is a soft metric.",
    }

    if args.bleu:
        try:
            import sacrebleu
            bleu = sacrebleu.corpus_bleu(hypotheses, [references]).score
            summary["bleu"] = bleu
            print(f"\n  Translation BLEU  : {bleu:.1f}")
        except ImportError:
            print("\n  (BLEU skipped — `pip install sacrebleu`)")

    if args.bertscore:
        try:
            from bert_score import score as bertscore
            _, _, F1 = bertscore(hypotheses, references, lang="en", verbose=False)
            val = float(F1.mean())
            summary["bertscore_f1"] = val
            print(f"  Translation BERTScore F1: {val:.3f}")
        except ImportError:
            print("  (BERTScore skipped — `pip install bert-score`)")

    out_path = os.path.join(HERE, "eval_results.json")
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump({"summary": summary, "details": details}, f, ensure_ascii=False, indent=2)
    print(f"\n  Full per-case results written to {out_path}")
    print("=" * 60)


def main():
    ap = argparse.ArgumentParser(description="Vaani NLP evaluation harness")
    ap.add_argument("--lang", help="filter to one source language")
    ap.add_argument("--limit", type=int, help="only run first N cases")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between calls (rate-limit guard)")
    ap.add_argument("--bleu", action="store_true", help="compute corpus BLEU (needs sacrebleu)")
    ap.add_argument("--bertscore", action="store_true", help="compute BERTScore F1 (needs bert-score)")
    ap.add_argument("--strict-entities", action="store_true", help="count extra predicted slots as FP")
    args = ap.parse_args()
    asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()