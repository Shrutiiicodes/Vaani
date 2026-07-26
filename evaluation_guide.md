# Vaani — Evaluation Playbook for Resume/Portfolio Metrics

This guide gives you **concrete experiments to run** so you can write lines like *"Achieved 94% intent classification accuracy across 8 Indian languages"* on your resume.

---

## 1. Translation & Intent Accuracy (The #1 Metric)

This is the single most impactful number you can quote. You need a **gold-standard test set** and a scoring script.

### Step 1: Build a Test Dataset

Create a file `backend/eval/test_cases.json` with ~50–100 entries across your supported languages:

```json
[
  {
    "id": 1,
    "audio_text": "Mujhe ghar ke liye loan chahiye, 50 lakh ka",
    "source_lang": "hindi",
    "expected_english": "I want a home loan of 50 lakhs",
    "expected_intent": "loan_enquiry",
    "expected_entities": {"loan_type": "home", "amount": "5000000"},
    "expected_counter": "specialized_counter"
  },
  {
    "id": 2,
    "audio_text": "எனது கணக்கில் எவ்வளவு பணம் இருக்கிறது",
    "source_lang": "tamil",
    "expected_english": "How much money is in my account",
    "expected_intent": "balance_enquiry",
    "expected_entities": {},
    "expected_counter": "cash_counter"
  }
]
```

> [!TIP]
> Aim for **at least 8–10 examples per language** and cover all 15 intent categories. Ask native-speaking friends/family for natural sentences—or generate them with another LLM and hand-verify.

### Step 2: Write the Evaluation Script

Create `backend/eval/run_eval.py` that calls `translate_customer_speech()` for each test case and scores:

| Metric | How to Compute | Resume Phrasing |
|---|---|---|
| **Intent Accuracy** | `correct_intents / total` | *"94% intent classification accuracy across 15 banking categories"* |
| **Counter Accuracy** | `correct_counters / total` | *"91% counter-routing accuracy"* |
| **Entity Extraction F1** | Precision × Recall on entity key-value pairs | *"0.87 F1 on entity extraction (names, amounts, account numbers)"* |
| **Translation BLEU** | `sacrebleu` score of `english_translation` vs reference | *"38.2 BLEU score for multilingual→English banking translation"* |
| **Translation BERTScore** | Semantic similarity using `bert-score` | *"0.91 BERTScore F1 for cross-lingual translation"* |

> [!IMPORTANT]
> **BERTScore is better than BLEU for LLM translations.** BLEU is a surface-level n-gram match (scores tend to be low 30–40 for good translations). BERTScore measures semantic similarity and will give you a number in the 0.85–0.95 range that looks much stronger on a resume. **Use both** — BLEU for academic credibility, BERTScore for the impressive number.

### Quotable Result Format
> *"Built a Gen-AI multilingual voice assistant supporting 9 Indian languages; achieved **93% intent accuracy**, **0.89 entity extraction F1**, and **0.91 BERTScore** on a 100-sample evaluation set across Hindi, Tamil, Telugu, Marathi, Bengali, Gujarati, Kannada, Odia, and English."*

---

## 2. End-to-End Latency (Shows Engineering Quality)

Measure the full pipeline: `Audio → STT → LLM (translate + intent + entities) → TTS → Response`

### What to Measure

| Stage | How | Target |
|---|---|---|
| STT (Whisper) | Time `transcribe_audio()` | < 2s |
| LLM Processing | Time `translate_customer_speech()` | < 3s |
| TTS | Time `text_to_speech_base64()` | < 1s |
| **Total E2E** | **Sum of above** | **< 5s** |

### How to Measure

Add timing instrumentation in your eval script or directly in `main.py`:

```python
import time

start = time.perf_counter()
stt_result = await transcribe_audio(audio_bytes)
stt_time = time.perf_counter() - start

start = time.perf_counter()
data = await translate_customer_speech(raw_text, detected_lang, convo_history, active_form)
llm_time = time.perf_counter() - start

# ... etc
```

Run 20–30 requests, compute **P50 and P95 latency**.

### Quotable Result Format
> *"Achieved **< 4s end-to-end response latency** (P95) for the full STT → translation → intent detection → TTS pipeline."*

---

## 3. Language Coverage (Breadth Metric)

You already support 9 languages in [tts.py](file:///c:/Users/asus/Projects/Vaani-Main/backend/tts.py). Validate each one works by running your test set per-language and reporting per-language accuracy.

### Quotable Result Format
> *"Supports **9 Indian languages** (Hindi, Tamil, Telugu, Marathi, Bengali, Gujarati, Kannada, Odia, English) with automatic language detection via Whisper Large V3."*

---

## 4. Financial Calculation Accuracy (Domain Expertise)

You already have unit tests in [test_calculations.py](file:///c:/Users/asus/Projects/Vaani-Main/backend/tests/test_calculations.py). Expand them and quote the pass rate.

### Expand Your Test Suite

Add test cases for:
- All loan types (home, personal, vehicle, gold, education, msme, kcc, mudra)
- All FD tenure brackets (< 24m, 24–59m, ≥ 60m)
- RD calculations
- Edge cases: zero amounts, very large amounts, boundary tenures

### Quotable Result Format
> *"100% accuracy on financial calculations (EMI, FD maturity, RD maturity, loan eligibility) validated against **30+ unit tests** covering 8 loan types and 3 FD brackets."*

---

## 5. Robustness & Input Handling

Test `clean_number()` and the LLM's JSON parsing with adversarial inputs:

| Test Category | Examples |
|---|---|
| Malformed numbers | `"₹50,000"`, `"1,00,000"`, `"50k"`, `"2l"`, `"abc"`, `None` |
| Ambiguous intents | `"Mujhe paisa chahiye"` (money — but for what?) |
| Incomplete info | Customer says amount but not tenure |
| Mixed languages | Hindi-English code-switching |
| Empty/garbage audio | Silence, background noise |

### Quotable Result Format
> *"Robust input handling with graceful degradation: handles currency shorthand (50k, 2L, ₹-prefixed), Indian comma formatting, ambiguous intents with follow-up clarification, and malformed LLM outputs via Pydantic validation."*

---

## 6. Quick-Start: Evaluation Script Skeleton

Here's the minimal script structure to get your numbers:

```python
# backend/eval/run_eval.py
import json, asyncio, time, sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from translate import translate_customer_speech

async def evaluate():
    with open("test_cases.json") as f:
        cases = json.load(f)

    intent_correct = 0
    counter_correct = 0
    total = len(cases)
    latencies = []

    for case in cases:
        start = time.perf_counter()
        result = await translate_customer_speech(
            case["audio_text"], case["source_lang"]
        )
        elapsed = time.perf_counter() - start
        latencies.append(elapsed)

        if result["intent"] == case["expected_intent"]:
            intent_correct += 1
        if result.get("suggested_counter") == case.get("expected_counter"):
            counter_correct += 1

    print(f"Intent Accuracy:  {intent_correct/total:.1%}")
    print(f"Counter Accuracy: {counter_correct/total:.1%}")
    print(f"Avg Latency:      {sum(latencies)/len(latencies):.2f}s")
    print(f"P95 Latency:      {sorted(latencies)[int(0.95*len(latencies))]:.2f}s")

asyncio.run(evaluate())
```

---

## 7. Priority Ranking — What to Do First

| Priority | Metric | Effort | Resume Impact |
|---|---|---|---|
| 🥇 **1** | Intent + Entity Accuracy | ~3 hours (build test set + script) | ⭐⭐⭐⭐⭐ |
| 🥈 **2** | Language Coverage Table | ~1 hour (per-language breakdown) | ⭐⭐⭐⭐ |
| 🥉 **3** | E2E Latency | ~30 min (add timers) | ⭐⭐⭐⭐ |
| 4 | Calculation Unit Tests | ~1 hour (expand existing) | ⭐⭐⭐ |
| 5 | BERTScore / BLEU | ~2 hours (install libs, run) | ⭐⭐⭐ |
| 6 | Robustness Tests | ~1 hour | ⭐⭐ |

---

## 8. Resume Bullet Point Templates

Pick and fill in your actual numbers:

1. > Built **Vaani**, a Gen-AI multilingual voice assistant for bank branch desks, supporting **9 Indian languages** with real-time STT (Whisper V3), LLM-powered intent detection (LLaMA 3.3 70B), and TTS — achieving **X% intent accuracy** and **< Ys E2E latency**.

2. > Engineered an NLP pipeline that extracts **15 banking intents** and structured entities (names, amounts, account numbers) from multilingual speech with **X% accuracy** and **F1 = Y** on entity extraction.

3. > Designed a financial computation engine handling EMI, FD/RD maturity, and loan eligibility calculations across **8 loan types** with **100% unit test pass rate** on Z+ test cases.

4. > Implemented session persistence, JWT authentication, rate limiting, and Docker containerization for a production-grade FastAPI backend serving real-time voice translation.

---

## 9. Portfolio Demo Tips

Beyond metrics, a great portfolio entry needs a **demo**:

- **Screen recording**: Record a 60–90 second video of you speaking in Hindi → the system translating → staff replying → TTS playing back in Hindi
- **Architecture diagram**: Show the STT → LLM → TTS pipeline with Groq/Whisper/gTTS logos
- **GitHub README**: Add a "Results" section with a table of your metrics + a GIF demo
- **Live deployment**: Deploy on Railway/Render with a public URL (free tier)

> [!CAUTION]
> Do NOT quote metrics you haven't actually measured. Interviewers will ask you to explain how you got a number. Run the eval, get real numbers, and be ready to discuss the methodology.
