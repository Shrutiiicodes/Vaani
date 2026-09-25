// ── State ────────────────────────────────────────────────────────────────────
let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentLanguage = "hindi";
let turnCount = 0;
let currentActiveFormType = null;
let bankName = "Bank";
let authToken = sessionStorage.getItem("vaaniToken");
let sessionId = sessionStorage.getItem("bankingSessionId") || newSessionId();

function newSessionId() {
    const id = crypto.randomUUID();
    sessionStorage.setItem("bankingSessionId", id);
    return id;
}

const $ = (id) => document.getElementById(id);

// Everything that came from the customer, the LLM or the server is untrusted:
// it must pass through esc() before it touches innerHTML.
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const label = (s) => String(s || "").replace(/_/g, " ").toUpperCase();

// ── API ──────────────────────────────────────────────────────────────────────

async function api(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (authToken) headers["Authorization"] = "Bearer " + authToken;
    const res = await fetch(path, { ...options, headers });
    if (res.status === 401) {
        showLogin("Session expired — please log in again");
        throw new Error("Not logged in");
    }
    if (!res.ok) {
        let detail = res.statusText;
        try { detail = (await res.json()).detail || detail; } catch { /* not JSON */ }
        throw new Error(typeof detail === "string" ? detail : "Request failed");
    }
    return res;
}

// Minimal Server-Sent Events reader for a fetch() response body.
async function readEvents(res, onEvent) {
    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";
    for (;;) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        let split;
        while ((split = buffer.indexOf("\n\n")) >= 0) {
            const block = buffer.slice(0, split);
            buffer = buffer.slice(split + 2);
            let event = "message", data = "";
            for (const line of block.split("\n")) {
                if (line.startsWith("event: ")) event = line.slice(7);
                else if (line.startsWith("data: ")) data += line.slice(6);
            }
            onEvent(event, data ? JSON.parse(data) : {});
        }
    }
}

// ── Auth ─────────────────────────────────────────────────────────────────────

function showLogin(message = "") {
    authToken = null;
    sessionStorage.removeItem("vaaniToken");
    $("login-error").textContent = message;
    $("login-overlay").style.display = "flex";
    $("login-user").focus();
}

async function doLogin() {
    const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username: $("login-user").value.trim(), password: $("login-pw").value }),
    });
    if (!res.ok) {
        $("login-error").textContent = res.status === 429 ? "Too many attempts — wait a minute" : "Invalid username or password";
        return;
    }
    const body = await res.json();
    authToken = body.access_token;
    sessionStorage.setItem("vaaniToken", authToken);
    $("login-pw").value = "";
    $("login-overlay").style.display = "none";
    $("staff-name").textContent = body.username;
    restoreSession();
}

async function logout() {
    try { await api("/api/logout", { method: "POST" }); } catch { /* token already invalid */ }
    showLogin();
}

// ── Reference rates (served by the backend: one source of truth) ─────────────

async function loadRates() {
    const res = await fetch("/api/rates");
    const rates = await res.json();
    bankName = rates.bank_name;
    document.querySelectorAll(".bank-name").forEach((el) => { el.textContent = bankName; });
    document.title = `Vaani — ${bankName}`;

    $("loan-chart").innerHTML = `
        <table class="data-table">
            <thead><tr><th>Loan Type</th><th>Interest Rate</th></tr></thead>
            <tbody>${rates.loans.map((r) => `
                <tr><td>${esc(r.label)}</td><td class="highlight">${Number(r.rate).toFixed(2)}%</td></tr>`).join("")}
            </tbody>
        </table>`;

    $("fd-table").innerHTML = `
        <thead><tr><th>Tenure</th><th>General</th><th>Senior Citizen</th></tr></thead>
        <tbody>${rates.fd_slabs.map((r) => `
            <tr><td>${esc(r.label)}</td><td class="highlight">${Number(r.general).toFixed(2)}%</td>
                <td class="highlight">${Number(r.senior).toFixed(2)}%</td></tr>`).join("")}
        </tbody>`;
}

function showFinPanel(intent) {
    const loan = ["loan_enquiry", "mudra_loan", "kisan_credit_card"].includes(intent);
    const deposit = intent === "fd_rd_enquiry";
    $("fin-loan").style.display = loan ? "block" : "none";
    $("fin-fdrd").style.display = deposit ? "block" : "none";
    $("fin-panel").style.display = loan || deposit ? "block" : "none";
}

// ── Dashboard rendering ──────────────────────────────────────────────────────

function updateCounter(name) {
    $("counter-name").textContent = name || "";
    $("counter-badge").style.display = name ? "flex" : "none";
}

function renderCalculations(calc) {
    const container = $("calc-container");
    if (!calc || calc.type === "none") {
        container.style.display = "none";
        return;
    }
    const money = (v) => (v === undefined || v === null ? "---" : "₹" + Number(v).toLocaleString("en-IN"));
    const item = (name, value) =>
        `<div class="calc-item"><span class="calc-label">${name}</span><span class="calc-value">${esc(value)}</span></div>`;
    const rate = calc.rate_used ? `${calc.rate_used}%` : "---";

    let title = "", icon = "", items = "";
    if (calc.type === "emi") {
        [title, icon] = ["EMI Estimate", "calculate"];
        items = item("Monthly EMI", money(calc.emi)) + item("Interest Rate", rate) +
            item("Total Payment", money(calc.total_payment)) + item("Total Interest", money(calc.total_interest));
    } else if (calc.type === "fd" || calc.type === "rd") {
        [title, icon] = [`${calc.type.toUpperCase()} Maturity`, "event_available"];
        items = item("Maturity Amount", money(calc.maturity)) + item("Interest Earned", money(calc.interest_earned)) +
            item("Rate Applied", rate);
    } else if (calc.type === "eligibility") {
        [title, icon] = ["Loan Eligibility", "verified_user"];
        items = item("Max Eligible Loan", money(calc.max_loan)) + item("Suggested EMI Cap", money(calc.suggested_emi_limit)) +
            item("Assumed Rate", rate);
    } else {
        container.style.display = "none";
        return;
    }
    container.innerHTML = `
        <div class="calc-card">
            <div class="calc-title"><span class="material-symbols-outlined">${icon}</span> ${title}</div>
            <div class="calc-grid">${items}</div>
        </div>`;
    container.style.display = "grid";
}

function renderForm(template) {
    const container = $("form-container");
    const grid = $("form-fields-grid");

    if (!template) {
        container.style.display = "none";
        currentActiveFormType = null;
        return;
    }

    // Same form already open: update only fields the staff hasn't edited by hand.
    if (container.style.display === "block" && currentActiveFormType === template.type) {
        for (const [field, val] of Object.entries(template.prefill || {})) {
            const fieldDiv = grid.querySelector(`[data-field="${CSS.escape(field)}"]`);
            if (!val || !fieldDiv || fieldDiv.classList.contains("manually-edited")) continue;
            const input = fieldDiv.querySelector("input");
            if (input.value !== String(val)) {
                input.value = val;
                fieldDiv.classList.add("prefilled", "new-extract");
                setTimeout(() => fieldDiv.classList.remove("new-extract"), 2000);
            }
        }
        return;
    }

    currentActiveFormType = template.type;
    $("form-type-name").textContent = label(template.type);
    container.style.display = "block";
    container.classList.remove("collapsed");
    grid.innerHTML = template.fields.map((field) => {
        const val = (template.prefill || {})[field] || "";
        return `
            <div class="form-field ${val ? "prefilled" : ""}" data-field="${esc(field)}">
                <label>${esc(label(field))}</label>
                <input type="text" value="${esc(val)}" placeholder="Required..."
                    onchange="this.parentElement.classList.add('manually-edited')">
            </div>`;
    }).join("");
}

function toggleFormCollapse() {
    $("form-container").classList.toggle("collapsed");
}

function printForm() {
    const fields = [...document.querySelectorAll("#form-fields-grid .form-field")].map((div) => ({
        name: div.querySelector("label").textContent,
        value: div.querySelector("input").value,
    }));
    const type = $("form-type-name").textContent;
    const w = window.open("", "_blank");
    w.document.write(`
        <html><head><title>${esc(bankName)} - ${esc(type)}</title>
        <style>
            body { font-family: sans-serif; padding: 40px; }
            .header { text-align: center; border-bottom: 2px solid #000; margin-bottom: 30px; }
            .field { margin-bottom: 15px; border-bottom: 1px dotted #ccc; display: flex; justify-content: space-between; }
            .label { font-weight: bold; color: #555; }
            .value { font-family: monospace; font-size: 1.1em; }
        </style></head>
        <body>
            <div class="header"><h1>${esc(bankName.toUpperCase())}</h1><h3>${esc(type)}</h3></div>
            ${fields.map((f) => `<div class="field"><span class="label">${esc(f.name)}</span>
                <span class="value">${esc(f.value) || "________________"}</span></div>`).join("")}
        </body></html>`);
    w.document.close();
    w.print();
}

function addLog(role, language, original, translation) {
    const entry = document.createElement("div");
    entry.className = `log-entry ${role === "customer" ? "customer" : "staff"}`;
    entry.innerHTML = `
        <span class="log-role"><span class="material-symbols-outlined">${role === "customer" ? "person" : "badge"}</span>
            ${role === "customer" ? "Customer" : "Staff"}</span>
        <span class="log-lang">[${esc(language)}]</span>
        <span class="log-text">${esc(original)}</span>
        <span class="log-translation">→ ${esc(translation)}</span>`;
    $("log-entries").appendChild(entry);
    turnCount++;
}

function setStatus(msg, kind = "") {
    $("status").textContent = msg;
    $("status").className = "status" + (kind ? " " + kind : "");
}

function playAudio(b64) {
    if (b64) new Audio(`data:audio/mp3;base64,${b64}`).play().catch(() => { /* autoplay blocked */ });
}

// ── Recording ────────────────────────────────────────────────────────────────

async function toggleRecording() {
    if (!isRecording) await startRecording();
    else await stopRecording();
}

async function startRecording() {
    let stream;
    try {
        stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    } catch {
        setStatus("Microphone access denied", "error");
        return;
    }
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = (e) => audioChunks.push(e.data);
    mediaRecorder.start();
    isRecording = true;
    $("mic-btn").innerHTML = '<span class="material-symbols-outlined">stop_circle</span> Stop Recording';
    $("mic-btn").classList.add("recording");
    setStatus("Recording...");
    $("clarification-box").style.display = "none";
}

async function stopRecording() {
    return new Promise((resolve) => {
        mediaRecorder.onstop = async () => {
            // Chrome/Firefox record webm/ogg, Safari mp4; Whisper needs a matching extension.
            const type = mediaRecorder.mimeType || "audio/webm";
            const ext = type.includes("mp4") ? "m4a" : type.includes("ogg") ? "ogg" : "webm";
            await processCustomerAudio(new Blob(audioChunks, { type }), `audio.${ext}`);
            resolve();
        };
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach((t) => t.stop());
        isRecording = false;
        $("mic-btn").innerHTML = '<span class="material-symbols-outlined">mic</span> Tap to Speak';
        $("mic-btn").classList.remove("recording");
        setStatus("Transcribing...", "processing");
    });
}

// ── Customer turn (streamed: transcript → analysis → audio → done) ───────────

async function processCustomerAudio(blob, filename = "audio.webm") {
    const form = new FormData();
    form.append("session_id", sessionId);
    form.append("audio", blob, filename);
    if (currentActiveFormType) form.append("active_form", currentActiveFormType);
    if ($("lang-hint").value) form.append("language", $("lang-hint").value);

    let transcript = null;
    try {
        const res = await api("/api/customer-speak", { method: "POST", body: form });
        await readEvents(res, (event, data) => {
            if (event === "transcript") {
                transcript = data;
                currentLanguage = data.detected_language || "hindi";
                $("detected-lang").textContent = `Language: ${label(currentLanguage)}`;
                $("customer-transcript").textContent = data.original_text || "";
                $("english-translation").textContent = "Translating...";
                setStatus("Understanding...", "processing");
            } else if (event === "analysis") {
                renderAnalysis(data);
                addLog("customer", currentLanguage, transcript?.original_text, data.english_translation);
                if (!transcript?.tts_supported) setStatus(`Voice not available for ${currentLanguage}`);
            } else if (event === "audio") {
                if (data.kind === "follow_up") $("clarification-q-vern").textContent = data.text || "";
                playAudio(data.audio_base64);
            } else if (event === "done") {
                setStatus(`Ready · ${(data.total_ms / 1000).toFixed(1)}s`);
            } else if (event === "error") {
                throw new Error(`${data.detail} (ref ${data.request_id})`);
            }
        });
    } catch (err) {
        setStatus("Error: " + err.message, "error");
    }
}

function renderAnalysis(data) {
    $("english-translation").textContent = data.english_translation || "";

    if (data.needs_clarification && data.follow_up_question) {
        $("clarification-q-en").textContent = data.follow_up_question;
        $("clarification-q-vern").textContent = "";
        $("clarification-box").style.display = "block";
        $("intent-box").style.display = "none";
        $("process-guide").style.display = "none";
        updateCounter(null);
        renderCalculations(null);
        renderForm(null);
        showFinPanel(null);
        return;
    }

    $("clarification-box").style.display = "none";
    if (data.intent && data.intent !== "other") {
        const pct = data.confidence ? ` (${Math.round(data.confidence * 100)}%)` : "";
        $("intent-text").textContent = label(data.intent) + pct;
        $("intent-box").style.display = "block";
    } else {
        $("intent-box").style.display = "none";
    }

    const steps = data.process_guide || [];
    $("guide-steps").innerHTML = steps.map((s) => `<li>${esc(s)}</li>`).join("");
    $("process-guide").style.display = steps.length ? "block" : "none";

    updateCounter(data.counter_name);
    renderCalculations(data.calculation_results);
    renderForm(data.form_template);
    showFinPanel(data.intent);
}

// ── Staff reply, summary ─────────────────────────────────────────────────────

async function sendReply() {
    const replyText = $("staff-reply").value.trim();
    if (!replyText) return;
    setStatus("Translating...", "processing");
    try {
        const res = await api("/api/staff-reply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reply_text: replyText, target_language: currentLanguage, session_id: sessionId }),
        });
        const data = await res.json();
        $("reply-translated").textContent = `Translated: ${data.translated_reply}`;
        playAudio(data.audio_base64);
        addLog("staff", "english", replyText, data.translated_reply);
        $("staff-reply").value = "";
        setStatus(data.audio_base64 ? "Ready" : `Reply translated — voice not available for ${currentLanguage}`);
    } catch (err) {
        setStatus("Error: " + err.message, "error");
    }
}

async function generateSummary() {
    if (turnCount === 0) return alert("No conversation yet.");
    setStatus("Generating summary...", "processing");
    try {
        const res = await api("/api/summary", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ session_id: sessionId }),
        });
        const data = await res.json();
        $("summary-english").textContent = data.english_summary;
        $("summary-vernacular").textContent = data.vernacular_summary;
        $("summary-lang-label").textContent = label(currentLanguage);
        $("summary-modal").style.display = "flex";
        setStatus("Ready");
    } catch (err) {
        setStatus("Error: " + err.message, "error");
    }
}

function closeSummary() { $("summary-modal").style.display = "none"; }

// ── Sessions: restore, new customer, history ─────────────────────────────────

function resetDashboard() {
    turnCount = 0;
    currentActiveFormType = null;
    $("log-entries").innerHTML = "";
    $("customer-transcript").textContent = "Customer speech will appear here...";
    $("english-translation").textContent = "Translation will appear here...";
    $("detected-lang").textContent = "Waiting for customer...";
    $("reply-translated").textContent = "";
    ["clarification-box", "intent-box", "process-guide"].forEach((id) => { $(id).style.display = "none"; });
    updateCounter(null);
    renderCalculations(null);
    renderForm(null);
    showFinPanel(null);
}

function newCustomer() {
    sessionId = newSessionId();
    resetDashboard();
    setStatus("New customer session");
}

async function restoreSession() {
    resetDashboard();
    try {
        const res = await api(`/api/session/${encodeURIComponent(sessionId)}`);
        const data = await res.json();
        data.turns.forEach((t) => addLog(t.role, t.language, t.text, t.translated || ""));
        const lastCustomer = data.turns.filter((t) => t.role === "customer").pop();
        if (lastCustomer) currentLanguage = lastCustomer.language;
        if (data.turns.length) setStatus(`Session restored (${data.turns.length} turns)`);
    } catch {
        // New session (404) or not logged in; nothing to restore.
    }
}

async function openHistory() {
    $("history-modal").style.display = "flex";
    $("history-body").innerHTML = `<tr><td colspan="5">Loading...</td></tr>`;
    try {
        const { sessions } = await (await api("/api/sessions")).json();
        $("history-body").innerHTML = sessions.length ? sessions.map((s) => `
            <tr class="history-row" data-id="${esc(s.session_id)}">
                <td>${esc(s.updated_at ? new Date(s.updated_at).toLocaleString() : "")}</td>
                <td>${esc(label(s.customer_language))}</td>
                <td>${esc(label(s.intent || "—"))}</td>
                <td>${esc(s.turns)}</td>
                <td>${esc(s.summary?.english_summary || "")}</td>
            </tr>`).join("") : `<tr><td colspan="5">No sessions yet.</td></tr>`;
        document.querySelectorAll(".history-row").forEach((row) => {
            row.onclick = () => {
                sessionId = row.dataset.id;
                sessionStorage.setItem("bankingSessionId", sessionId);
                closeHistory();
                restoreSession();
            };
        });
    } catch (err) {
        $("history-body").innerHTML = `<tr><td colspan="5">${esc(err.message)}</td></tr>`;
    }
}

function closeHistory() { $("history-modal").style.display = "none"; }

// ── Boot ─────────────────────────────────────────────────────────────────────

window.addEventListener("DOMContentLoaded", () => {
    loadRates().catch(() => { /* reference panel stays empty */ });
    if (authToken) {
        try {   // display only; the server verifies the token on every call
            const b64 = authToken.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
            $("staff-name").textContent = JSON.parse(atob(b64)).sub;
        } catch { /* malformed token: the first API call will 401 */ }
        $("login-overlay").style.display = "none";
        restoreSession();
    } else {
        showLogin();
    }
});
