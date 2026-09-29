# Vaani — Improvement Plan

Handoff document for implementation. Each item has: file(s), the problem, the fix. Do phases in order; each phase is independently shippable. Keep diffs minimal: no new abstractions, no new deps unless named here.

## What the project is

FastAPI backend + vanilla JS frontend. Bank staff logs in with one shared password, records a customer speaking in an Indian language. Pipeline per turn:

1. `/api/customer-speak`: audio → Groq Whisper (STT + language detect) → one LLaMA-3.3-70B call that translates, classifies into 15 intents, extracts entities, suggests a counter, and emits calculation inputs → Python computes EMI / FD / RD / eligibility from hardcoded rates → optional second LLM call + gTTS for a clarification question or a calculation readout.
2. `/api/staff-reply`: English text → LLM translate → gTTS audio in the customer's language.
3. `/api/summary`: LLM summary of the turn history stored in SQLite.
4. JWT auth (single "staff" subject, in-memory revocation), SlowAPI rate limits, an eval harness with 60 gold cases (intent 98%, entity F1 0.62), 16 unit tests.

Current state: tests pass. Uncommitted work-in-progress: `DATABASE_URL` support in `backend/database.py`, `vercel.json` + `api/index.py` for Vercel, dev deps split into `requirements-dev.txt`.

---

## Phase 0 — Hygiene and security (do first)

| # | File | Problem | Fix |
|---|------|---------|-----|
| 0.1 | `frontend/index.html` | Staff password is hardcoded as the login input's default a real password as its `value`. | Remove the `value` attribute. Rotate the password in `.env`. |
| 0.2 | `backend/banking_sessions.db` | Real session data is tracked in git. | `git rm --cached`, add `*.db` to `.gitignore`. |
| 0.3 | `frontend/app.js` (`addLog`, `renderForm`, guide steps, `printForm`) | Transcript, translation and LLM entity values are injected via `innerHTML` and attribute interpolation. STT and LLM output are untrusted, so this is stored XSS. | Build nodes with `textContent`; set `input.value` in JS instead of inside the template string. Add one `escapeHtml` helper and use it in `printForm`. |
| 0.4 | `backend/main.py` | `allow_origins=["*"]` with bearer auth. | Read `ALLOWED_ORIGINS` env (comma list), default `http://localhost:8000`. |
| 0.5 | `backend/main.py` | Every handler does `except Exception → HTTPException(500, detail=str(e))`, leaking internals. | Remove the blanket handlers. Add one global exception handler that logs the traceback and returns `{"detail": "internal error"}`. Keep the 400 in `/api/summary`. |
| 0.6 | `backend/main.py` `/api/customer-speak` | No upload size limit. A huge upload is read into memory and shipped to Groq (cost + memory DoS). | Reject with 413 if `len(audio_bytes) > 10 * 1024 * 1024`. Reject if `audio.content_type` does not start with `audio/`. |
| 0.7 | `backend/main.py` | `/api/staff-reply` and `/api/summary` have no rate limit; each costs an LLM call. | Add `@limiter.limit("30/minute")` to both (they need a `request: Request` param). |
| 0.8 | `requirements.txt` | Unpinned; `aiosqlite` unused. | Pin every version from the working venv, drop `aiosqlite`. |
| 0.9 | `docker-compose.yml`, `backend/database.py` | Compose mounts the file `./banking_sessions.db`, which does not exist at repo root, so Docker creates a directory and SQLite fails. The new default DB path is the OS temp dir, not `/app/backend`. | Mount a directory `./data:/app/data` and set `DATABASE_URL=sqlite:////app/data/banking_sessions.db` in compose `environment`. |
| 0.10 | `backend/database.py` | `connect_args={"check_same_thread": False}` crashes on Postgres. | Pass it only when `DATABASE_URL.startswith("sqlite")`. |
| 0.11 | `evaluation_guide.md` | Reads as advice on gaming resume numbers ("the impressive number"). A recruiter opening the repo sees it. | Delete it. Replace with an honest `backend/eval/README.md`: what is measured, what is not (STT is bypassed), dataset size, how to reproduce. |
| 0.12 | `README.md` | Lists endpoints that do not exist (`/api/translate-text`, `/api/counters`, `/api/session-history`); MIT badge but no `LICENSE` file; app title still "PS6". | Fix the endpoint table to match `main.py`, add `LICENSE`, rename the title in `main.py` and `index.html` to "Vaani". |
| 0.13 | whole repo | "Union Bank of India" branding in prompts, UI and print forms. Trademark risk on a public portfolio. | Make `BANK_NAME` an env var (default "Demo Bank"); use it in the system prompt, header, and print form. |

Commit the pending `DATABASE_URL` / Vercel work as part of this phase after 0.9 and 0.10.

---

## Phase 1 — Correctness bugs

| # | File | Problem | Fix |
|---|------|---------|-----|
| 1.1 | `backend/translate.py` `_is_money_ambiguous` | Second rule: any utterance of six words or fewer containing a money keyword forces clarification regardless of intent or confidence. "Withdraw 5000 rupees" at 0.95 confidence still gets asked "loan, cash or FD?". The keyword list also contains junk (`돈` is Korean, `హಣ` is a mixed-script typo). | Require `intent == "other" or confidence < 0.55` for both rules. Remove foreign keywords; add correct Kannada `ಹಣ`, Telugu `డబ్బు`, Hindi/Marathi `पैसे`, Bengali `টাকা`, Gujarati `પૈસા`, Odia `ଟଙ୍କା`. |
| 1.2 | `backend/translate.py` `perform_calculations` | Prompt tells the LLM to emit `kisan`; the rates table has `kcc`, so KCC loans fall to the 10% default. FD tier `fd_3yr` is unreachable (24–59 months all use `fd_2yr`). | Add an alias map (`kisan`, `kisan_credit_card` → `kcc`; `home` → `home_loan`, etc.) before lookup. Add a 36–59 month tier using `fd_3yr`. |
| 1.3 | `backend/translate.py` | Entity recall is 0.48. The misses in `eval_results.json` are systematic: LLM returns `tenure_years` instead of `tenure_months`, never returns `account_type`, returns `nominee` instead of `nominee_relation`. | (a) List `account_type`, `nominee_name`, `nominee_relation`, `tenure_months` explicitly in the prompt's entity schema. (b) Post-process: if `tenure_years` is present and `tenure_months` absent, set `tenure_months = years * 12`; same for `calculation_inputs.n`. (c) Extend the `aliases` dict with `account_type` and `nominee_relation`. Re-run eval; target entity F1 ≥ 0.85. |
| 1.4 | `backend/translate.py` eligibility | README claims eligibility uses "income and existing obligations"; code is `income * 60` and ignores existing EMIs. | Prompt: add `existing_emi` to `calculation_inputs`. Code: `disposable = income * 0.5 - existing_emi`; `max_loan = disposable * 60`; `suggested_emi_limit = disposable`. Add a unit test. |
| 1.5 | `backend/crud.py` `update_session_language` | Never commits; it relies on a later `add_turn` commit in the same DB session. | Add `db.commit()`. |
| 1.6 | `backend/database.py` | `conversation_turns.session_id` has no index or FK, and `get_turns` runs on every request. Timestamps mix naive `utcnow` and tz-aware `datetime.now(timezone.utc)`. | `Column(String, ForeignKey("sessions.id"), index=True)`. Use `datetime.now(timezone.utc)` everywhere. |
| 1.7 | `frontend/app.js` `renderCalculations` | `html` is assigned without declaration (implicit global). | `let html = "";` |
| 1.8 | `frontend/app.js`, `backend/main.py` | Client sends its own `conversation` array and a `session_id`; the backend ignores the array when `session_id` is present. Two sources of truth. | Drop the `conversation` form field and the fallback branch. Make `session_id` required. |
| 1.9 | `backend/main.py` `/api/session/{id}` | Any valid token can read any session by ID. Harmless with one staff account; becomes an IDOR once 5.3 adds multiple staff. | Fix together with 5.3: store `staff_id` on `BankingSession` and filter by it. |

---

## Phase 2 — Scalability and latency

This phase has the biggest measurable win. Take before/after numbers using the tooling from Phase 3.

| # | File | Problem | Fix |
|---|------|---------|-----|
| 2.1 | `backend/translate.py`, `backend/stt.py` | `Groq()` is the **sync** client, called from `async def` handlers. Every STT / LLM call (2–5 s) blocks the event loop, so the server effectively handles one request at a time. This is the single biggest scalability bug. | Switch to `AsyncGroq` and `await client.chat.completions.create(...)`. In STT, pass `("audio.webm", audio_bytes)` as the `file` argument instead of writing a temp file. |
| 2.2 | `backend/tts.py`, `backend/main.py` | gTTS makes a blocking HTTP call inside async handlers. | Wrap with `await run_in_threadpool(text_to_speech_base64, ...)` from `fastapi.concurrency`. (Superseded if 5.2 lands.) |
| 2.3 | `backend/main.py` `/api/customer-speak` | Serial chain: STT → LLM → translate follow-up → TTS. The money follow-up question is the same sentence every time, yet it is re-translated and re-synthesised on every request. | Add a dict cache in `translate_text` keyed on `(text, lang)` and one in `text_to_speech_base64` keyed the same way (`functools.lru_cache` is enough). The follow-up path then costs zero network calls after the first hit per language. Calc readouts contain varying amounts, so they stay uncached. |
| 2.4 | `backend/translate.py` | JSON is coaxed via "respond only with JSON" plus fence stripping. Parse failures silently degrade to `intent = other`. | Pass `response_format={"type": "json_object"}` on the main call and on `generate_summary`. Keep `_strip_fences` as a fallback. Log every fallback with the raw text so failures are visible. |
| 2.5 | `backend/main.py`, `Dockerfile` | No health endpoint for Docker, Vercel or uptime checks. | `GET /health` → `{"status": "ok"}`. Add a `HEALTHCHECK` line to the Dockerfile. |
| 2.6 | `backend/auth.py` | Revocation store is in-process; on Vercel every invocation may be a fresh process, so logout is a no-op there. | Acceptable for the demo. Document it in the README deployment notes. Do not add Redis just for this. |
| 2.7 | `backend/database.py`, deploy | SQLite in `/tmp` on Vercel loses all sessions on every cold start. | Provision a free Postgres (Neon or Supabase), set `DATABASE_URL`, add `psycopg[binary]`. `create_all` on startup is fine; skip Alembic until the schema actually changes. Docker keeps SQLite. |

Expected outcome: p95 for `/api/customer-speak` under 10 concurrent requests drops from serialised (roughly 10× single-request time) to about the single-request latency.

---

## Phase 3 — Tests, CI, observability

| # | File | What | Why |
|---|------|------|-----|
| 3.1 | `backend/tests/test_api.py` (new) | FastAPI `TestClient` tests: login, bad token, `/api/customer-speak` with Groq and TTS monkeypatched to canned outputs, `/api/staff-reply`, `/api/summary` 400 on empty. Use a temp SQLite via `DATABASE_URL`. | Only the pure-math functions are tested today; HTTP, auth and persistence have zero coverage. |
| 3.2 | `backend/tests/test_postprocess.py` (new) | Split `translate_customer_speech` so the post-LLM logic is a pure function `postprocess(parsed: dict, text: str, active_form: str | None) -> dict`. Test 1.1, 1.2, 1.3 against it with canned dicts. | Makes the highest-value logic testable without an API key. |
| 3.3 | `.github/workflows/ci.yml` (new) | On push/PR: install `requirements-dev.txt`, `ruff check`, `pytest`. Add `ruff` to dev requirements with a minimal `[tool.ruff]` block in `pyproject.toml`. | Green CI badge that proves the tests are real. |
| 3.4 | `backend/main.py` | One structured log line per request: request id, route, `stt_ms`, `llm_ms`, `tts_ms`, `total_ms`. Stdlib `logging` with a small JSON formatter, no new dep. Return an `X-Request-ID` header. | Gives honest per-stage latency numbers for the README and for the Phase 2 before/after. |
| 3.5 | `backend/eval/load_test.py` (new, ~30 lines) | Fire N concurrent `/api/customer-speak` requests with a fixed clip using `httpx.AsyncClient`. Print p50/p95 for N = 1, 5, 10. | Produces the "N concurrent sessions at p95 X s" number. |

---

## Phase 4 — Accuracy and evaluation

| # | What | Why / how |
|---|------|-----------|
| 4.1 | Grow `test_cases.json` from 60 to about 150, balanced: at least 12 per language, every intent at least 5 cases, at least 15 `other` / ambiguous cases, at least 10 code-mixed Hinglish. Keep the `needs_native_review` flag and get non-English cases checked by native speakers where possible. | Three Odia cases and two cases for most intents cannot support a claimed accuracy. Ambiguous cases are where the model actually fails (case 29). |
| 4.2 | Add a real STT eval: `backend/eval/audio/` with 20–30 short recorded clips (phone mic, some background noise) plus transcripts. `run_stt_eval.py` computes WER per language with `jiwer` (dev dep) and language-detection accuracy. | The current eval bypasses Whisper entirely. An end-to-end number on 25 real clips is far more credible than 98% on gold text. |
| 4.3 | Extend `run_eval.py`: intent confusion matrix, a `--mock` flag that replays `eval_results.json` for CI smoke, and a markdown results table the README embeds. | Reproducible and CI-checkable. |
| 4.4 | Language hint: a dropdown in the UI (default "auto") passed to Whisper as `language=`. | Whisper mis-detects short Hinglish clips; the hint is a one-liner and improves the STT number. |
| 4.5 | Re-run the full eval after 1.3 and record before/after entity F1 in the README. | The jump from 0.62 to about 0.85 is a concrete, honest improvement story. |

---

## Phase 5 — Features that raise impact

Do 5.1 and 5.2 at minimum; 5.3 to 5.5 are optional.

| # | What | Why / how |
|---|------|-----------|
| 5.1 | **Streaming pipeline (SSE)**: `/api/customer-speak` returns a `StreamingResponse` emitting events `transcript` (after STT), `analysis` (after LLM), `audio` (after TTS). Frontend reads it with `fetch` + `ReadableStream` (multipart upload rules out `EventSource`). | Staff sees the transcript about 1.5 s earlier. Time-to-first-transcript is a headline metric. Small change because the pipeline is already staged. |
| 5.2 | **Replace gTTS with `edge-tts`** (free Microsoft neural voices: hi, ta, te, bn, gu, kn, mr, en; no Odia). Keep gTTS as fallback for languages edge-tts lacks. Function signature unchanged. | gTTS scrapes Google Translate, breaks periodically, sounds robotic and is blocking. edge-tts is async and noticeably better. |
| 5.3 | **Multiple staff accounts**: `staff` table (username, bcrypt hash, role); `/api/login` takes username + password; JWT `sub` = username; `BankingSession.staff_id`; session endpoints filtered by owner. Seed one admin from env. Fixes 1.9. | Turns "shared password" into "RBAC + audit trail", and makes session ownership real. |
| 5.4 | **`GET /api/rates`** serving `BANK_RATES`; frontend fetches it instead of its own `LOAN_RATES` / `FD_RATES`. | The two copies already disagree (frontend 6.70% vs backend 6.8 for 1-year FD). |
| 5.5 | **Session history page**: list past sessions with intent, language, summary, from the data already in the DB. | Shows the product is more than a single-turn demo. |

Skip: vector DB / RAG, LangChain, microservices, Kubernetes, Redis. None are needed and each is an interview liability if you cannot justify it.

---

## Phase 6 — Portfolio polish

- README: 30-second demo GIF at the top, live URL, the existing mermaid diagram, an honest metrics table with dataset size and what is and is not measured, a per-stage latency table, and a "what I'd do next" section.
- Deploy: Docker on Render or a small VPS with persistent SQLite is simpler and more honest than Vercel serverless for this workload (long requests, TTS). Keep `vercel.json` only if it works end-to-end after 2.7.
- Rename "PS6" everywhere.

---

## Resume bullets you can honestly write after this plan

- Built a multilingual voice assistant (FastAPI, Groq Whisper, LLaMA-3.3-70B) for bank branch desks covering 9 Indian languages: 15-intent classification, entity extraction, counter routing, EMI/FD/RD calculation, vernacular TTS.
- Achieved X% intent accuracy and 0.YY entity F1 on a 150-case multilingual benchmark; measured Z% WER on recorded audio across N languages. *(fill from Phase 4)*
- Cut p95 latency under 10 concurrent sessions from A s to B s by moving to async Groq clients, thread-pooled TTS, JSON-mode structured output and response caching; streamed stage results over SSE to cut time-to-first-transcript by C s. *(fill from 3.4 / 3.5)*
- Shipped JWT auth with per-user accounts, rate limiting, input validation, CI with lint and API tests, structured per-stage latency logging, and Docker deployment.

## Order of work for the executor

0 → 1 → 2 → 3 → 4 → 5.1 → 5.2 → 6, then 5.3 to 5.5 if time allows. Run `pytest backend/tests -q` after every phase. Re-run `python backend/eval/run_eval.py` after Phase 1 and Phase 4 and record the numbers.
