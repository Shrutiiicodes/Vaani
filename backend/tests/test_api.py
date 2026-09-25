"""HTTP-level tests. Groq and TTS are replaced with canned fakes; the DB is a temp SQLite."""
import json
import uuid

import pytest
from fastapi.testclient import TestClient

import main
import translate

LLM_RESULT = {
    "english_translation": "I need a home loan of 5 lakh for 20 years",
    "intent": "loan_enquiry", "confidence": 0.93, "suggested_counter": "specialized_counter",
    "entities": {"loan_type": "home", "amount": "5 lakh", "tenure_years": "20"},
    "calculation_inputs": {"type": "emi", "p": 500000, "n": 20, "loan_category": "home"},
    "needs_clarification": False,
}


@pytest.fixture(scope="module")
def client():
    with TestClient(main.app) as c:        # runs lifespan: create tables + seed admin
        yield c


@pytest.fixture(autouse=True)
def fake_ai(monkeypatch):
    state = {"llm": json.dumps(LLM_RESULT)}

    async def fake_stt(audio, filename="audio.webm", language=None):
        return {"text": "mujhe 5 lakh ka home loan chahiye 20 saal ke liye", "language": "hindi"}

    async def fake_chat(messages, json_mode=False, temperature=0.1):
        prompt = messages[-1]["content"]
        if "english_summary" in prompt:
            return json.dumps({"english_summary": "Customer wants a home loan.", "vernacular_summary": "गृह ऋण"})
        return state["llm"] if json_mode else "अनुवादित उत्तर"

    async def fake_tts(text, language):
        return "QUJD"

    monkeypatch.setattr(main, "transcribe_audio", fake_stt)
    monkeypatch.setattr(translate, "_chat", fake_chat)
    monkeypatch.setattr(main, "text_to_speech_base64", fake_tts)
    translate.translate_text.cache.clear()
    return state


def auth(client, username="admin", password="admin-password") -> dict:
    r = client.post("/api/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def speak(client, headers, session_id, **extra):
    return client.post("/api/customer-speak", headers=headers,
                       data={"session_id": session_id, **extra},
                       files={"audio": ("clip.webm", b"fake-audio", "audio/webm")})


def sse_events(body: str) -> list:
    events = []
    for block in body.strip().split("\n\n"):
        fields = dict(line.split(": ", 1) for line in block.splitlines())
        events.append((fields["event"], json.loads(fields["data"])))
    return events


# ── Basics & auth ─────────────────────────────────────────────────────────────

def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_rates_are_served_from_backend(client):
    body = client.get("/api/rates").json()
    assert {"bank_name", "loans", "fd_slabs", "languages"} <= body.keys()
    assert any(loan["category"] == "home_loan" for loan in body["loans"])


def test_wrong_password_and_unknown_user_are_rejected(client):
    assert client.post("/api/login", json={"username": "admin", "password": "nope"}).status_code == 401
    assert client.post("/api/login", json={"username": "ghost", "password": "nope"}).status_code == 401


def test_protected_route_needs_token(client):
    assert client.get("/api/sessions").status_code == 401
    assert client.get("/api/sessions", headers={"Authorization": "Bearer junk"}).status_code == 401


def test_logout_revokes_token(client):
    headers = auth(client)
    assert client.post("/api/logout", headers=headers).status_code == 200
    assert client.get("/api/sessions", headers=headers).status_code == 401


def test_request_id_header(client):
    r = client.get("/api/rates", headers={"X-Request-ID": "abc123"})
    assert r.headers["X-Request-ID"] == "abc123"


# ── Customer turn ─────────────────────────────────────────────────────────────

def test_customer_turn_streams_stages_and_persists(client):
    headers, sid = auth(client), str(uuid.uuid4())
    r = speak(client, headers, sid)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/event-stream")

    events = sse_events(r.text)
    assert [name for name, _ in events] == ["transcript", "analysis", "audio", "done"]
    transcript, analysis, audio, done = (data for _, data in events)
    assert transcript["detected_language"] == "hindi"
    assert analysis["entities"]["tenure_months"] == "240"
    assert analysis["calculation_results"]["rate_used"] == 8.5
    assert analysis["form_template"]["prefill"]["loan_amount"] == "500000"
    assert audio["kind"] == "calculation" and audio["audio_base64"] == "QUJD"
    assert {"stt_ms", "llm_ms", "total_ms"} <= done.keys()

    turns = client.get(f"/api/session/{sid}", headers=headers).json()["turns"]
    assert len(turns) == 1 and turns[0]["intent"] == "loan_enquiry"
    listed = {s["session_id"]: s for s in client.get("/api/sessions", headers=headers).json()["sessions"]}
    assert listed[sid]["intent"] == "loan_enquiry" and listed[sid]["turns"] == 1


def test_unparseable_llm_output_degrades_gracefully(client, fake_ai):
    fake_ai["llm"] = "not json at all"
    events = sse_events(speak(client, auth(client), str(uuid.uuid4())).text)
    analysis = dict(events)["analysis"]
    assert analysis["intent"] == "other"
    assert analysis["english_translation"]         # falls back to the transcript
    assert events[-1][0] == "done"


def test_rejects_non_audio_upload(client):
    r = client.post("/api/customer-speak", headers=auth(client), data={"session_id": str(uuid.uuid4())},
                    files={"audio": ("x.txt", b"hello", "text/plain")})
    assert r.status_code == 415


def test_rejects_oversized_upload(client):
    r = client.post("/api/customer-speak", headers=auth(client), data={"session_id": str(uuid.uuid4())},
                    files={"audio": ("big.webm", b"0" * (main.MAX_AUDIO_BYTES + 1), "audio/webm")})
    assert r.status_code == 413


def test_rejects_bad_language_hint_and_session_id(client):
    headers = auth(client)
    assert speak(client, headers, str(uuid.uuid4()), language="xx").status_code == 400
    assert speak(client, headers, "../../etc").status_code == 422


# ── Staff reply & summary ─────────────────────────────────────────────────────

def test_staff_reply_and_summary(client):
    headers, sid = auth(client), str(uuid.uuid4())
    assert client.post("/api/summary", headers=headers, json={"session_id": sid}).status_code == 404

    speak(client, headers, sid)
    r = client.post("/api/staff-reply", headers=headers,
                    json={"reply_text": "Please bring your salary slip", "target_language": "hindi", "session_id": sid})
    assert r.status_code == 200
    assert r.json()["translated_reply"] == "अनुवादित उत्तर" and r.json()["tts_supported"] is True

    turns = client.get(f"/api/session/{sid}", headers=headers).json()["turns"]
    assert [t["role"] for t in turns] == ["customer", "staff"]

    summary = client.post("/api/summary", headers=headers, json={"session_id": sid}).json()
    assert summary["english_summary"] == "Customer wants a home loan."
    listed = {s["session_id"]: s for s in client.get("/api/sessions", headers=headers).json()["sessions"]}
    assert listed[sid]["summary"]["english_summary"] == "Customer wants a home loan."


# ── Multi-staff ownership ─────────────────────────────────────────────────────

def test_staff_cannot_see_each_others_sessions(client):
    admin = auth(client)
    r = client.post("/api/staff", headers=admin, json={"username": "alice", "password": "alice-password"})
    assert r.status_code == 201
    assert client.post("/api/staff", headers=admin,
                       json={"username": "alice", "password": "alice-password"}).status_code == 409
    alice = auth(client, "alice", "alice-password")

    admin_sid = str(uuid.uuid4())
    speak(client, admin, admin_sid)
    assert client.get(f"/api/session/{admin_sid}", headers=alice).status_code == 404
    assert speak(client, alice, admin_sid).status_code == 404
    assert all(s["session_id"] != admin_sid
               for s in client.get("/api/sessions", headers=alice).json()["sessions"])

    alice_sid = str(uuid.uuid4())
    speak(client, alice, alice_sid)
    assert client.get(f"/api/session/{alice_sid}", headers=admin).status_code == 200   # admin sees all


def test_only_admin_can_create_staff(client):
    admin = auth(client)
    client.post("/api/staff", headers=admin, json={"username": "bob", "password": "bob-password"})
    bob = auth(client, "bob", "bob-password")
    r = client.post("/api/staff", headers=bob, json={"username": "eve", "password": "eve-password"})
    assert r.status_code == 403
