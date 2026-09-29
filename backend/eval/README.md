# Evaluation

Three independent measurements. Each says exactly what it covers.

| Script | Measures | Needs |
|---|---|---|
| `run_eval.py` | Language pipeline on gold text: translation, intent, entities, counter, clarification | `GROQ_API_KEY` |
| `run_stt_eval.py` | Whisper speech-to-text: WER, CER, language identification | `GROQ_API_KEY` |
| `load_test.py` | End-to-end latency under concurrent load, against a running server | a running server |

## Language pipeline (`run_eval.py`)

`test_cases.json` holds 150 cases across 9 languages (12 per regional language, 27 English, 39 Hindi including 13 code-mixed Hinglish). Every intent has at least 6 cases, and 8 cases are deliberately vague money requests that should trigger a clarifying question.

Honest limits:

- **Whisper is bypassed.** Gold text goes straight into the pipeline, so this is accuracy *given a correct transcript*.
- **The author wrote the non-English cases.** They are flagged `needs_native_review` and have not yet been checked by native speakers.
- **Counter accuracy mostly mirrors intent.** The counter now comes from a routing table keyed by intent. The LLM only picks it for "other", and some requests could reasonably go to two counters.
- **Entity scoring only covers annotated slots.** Extra predicted keys are not penalised.

```bash
python backend/eval/run_eval.py              # ~25 min; one full run uses most of a model's free daily token quota
python backend/eval/run_eval.py --limit 10 --delay 2
python backend/eval/run_eval.py --model openai/gpt-oss-120b --out eval_results_gptoss.json --markdown RESULTS_gptoss.md
python backend/eval/run_eval.py --mock       # re-score saved results offline (used in CI)
```

Results land in `RESULTS.md` and `eval_results.json` (default model, Qwen). `RESULTS_gptoss.md` and `eval_results_gptoss.json` hold the gpt-oss-120b run. New runs also save each raw model output, so `--mock` re-runs the current post-processing on it and rule changes can be measured without API calls. `baseline_llama33_60cases.json` is the original 60-case run on the retired `llama-3.3-70b-versatile`, kept for comparison. Re-score it with `--mock --out baseline_llama33_60cases.json`.

## Speech-to-text (`run_stt_eval.py`)

Three clip sets are scored and reported separately:

| Set | What it is | How to get it |
|---|---|---|
| `human-fleurs` | 90 real native speakers, 10 per language including Odia, reading general Wikipedia sentences. From Google's [FLEURS](https://huggingface.co/datasets/google/fleurs) test split, CC-BY 4.0. | `python backend/eval/fetch_fleurs.py` streams only the first clips of each archive, about 54 MB. |
| `synthetic-edge-tts` | 32 banking sentences from the test set, voiced by neural TTS with two voices per language. Clean studio audio. | Committed; `run_stt_eval.py --synthesize N` adds more |
| `synthetic+babble-snr10dB+phone` | The same 32 banking clips with background chatter from 3 real FLEURS speakers at 10 dB SNR, band-limited to 300-3400 Hz like a phone mic. | `python backend/eval/make_noisy.py`, seeded and reproducible |

FLEURS measures Whisper on real voices, but not on banking vocabulary. The synthetic sets measure banking sentences, but not real voices. Neither is a real branch recording. The FLEURS and noisy audio is not committed; both scripts regenerate it.

To add real recordings, follow the checklist in [audio/human/README.md](audio/human/README.md). It gives 27 sentences with a filename for each. A clip saved as `audio/human/<language>_<case id>.<ext>` is picked up automatically, with its reference text taken from that test case.

Native-speaker review: fill in [native_review.csv](native_review.csv), which opens in Excel or Google Sheets. It has one row per non-English case, with columns for whether the sentence sounds natural and whether its meaning is right.

```bash
python backend/eval/run_stt_eval.py          # auto-detect language
python backend/eval/run_stt_eval.py --hint   # pass the known language, as the UI's language picker does
python backend/eval/run_stt_eval.py --synthesize 4   # add 4 more synthetic clips per language
```

Only FLEURS includes Odia. Whisper has no Odia language, so there is no hint to pass, and it cannot transcribe Odia correctly.

## Load (`load_test.py`)

This fires N simultaneous customer turns at a running server. With no clip given, it synthesises a Hindi home-loan request, which exercises every stage: speech-to-text, LLM, EMI calculation, translated readout and TTS.

```bash
python backend/eval/load_test.py --password "$STAFF_PASSWORD" --levels 1 4
```

Keep concurrency at 4 or below on Groq's free tier. Beyond that you are measuring Groq's rate-limit back-off, not the app. Restart the server between runs: translations and speech are cached, so a repeated clip gets faster and the numbers stop being honest.
