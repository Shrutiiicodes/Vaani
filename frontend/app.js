let mediaRecorder = null;
let audioChunks = [];
let isRecording = false;
let currentLanguage = "hindi";
let conversation = [];
let currentActiveFormType = null;

// ── Union Bank of India — Reference Rates ──────────────────────────────────
const LOAN_RATES = [
    { label: "Home Loan", rate: 8.50, color: "blue" },
    { label: "Personal Loan", rate: 11.50, color: "blue" },
    { label: "Vehicle Loan", rate: 8.80, color: "teal" },
    { label: "Education Loan", rate: 8.50, color: "teal" },
    { label: "Gold Loan", rate: 9.00, color: "teal" },
    { label: "MSME / Business", rate: 9.50, color: "blue" },
    { label: "Mudra (Shishu)", rate: 9.50, color: "blue" },
    { label: "Kisan Credit", rate: 7.00, color: "teal" },
];
const MAX_LOAN_RATE = 15;

const FD_RATES = [
    { tenure: "7 – 14 days", general: "3.00%", senior: "3.50%" },
    { tenure: "15 – 29 days", general: "3.00%", senior: "3.50%" },
    { tenure: "30 – 45 days", general: "3.50%", senior: "4.00%" },
    { tenure: "46 – 90 days", general: "4.50%", senior: "5.00%" },
    { tenure: "91 – 179 days", general: "4.50%", senior: "5.00%" },
    { tenure: "180 – 364 days", general: "5.50%", senior: "6.00%" },
    { tenure: "1 year", general: "6.70%", senior: "7.20%" },
    { tenure: "1 – 2 years", general: "6.80%", senior: "7.30%" },
    { tenure: "2 – 3 years", general: "6.50%", senior: "7.00%" },
    { tenure: "3 – 5 years", general: "6.50%", senior: "7.00%" },
    { tenure: "5 – 10 years", general: "6.50%", senior: "7.00%" },
];

function showFinPanel(intent) {
    const panel = document.getElementById("fin-panel");
    const loanDiv = document.getElementById("fin-loan");
    const fdrdDiv = document.getElementById("fin-fdrd");

    if (intent === "loan_enquiry" || intent === "mudra_loan" || intent === "kisan_credit_card") {
        fdrdDiv.style.display = "none";
        loanDiv.style.display = "block";
        panel.style.display = "block";
        buildLoanTable();
    } else if (intent === "fd_rd_enquiry") {
        loanDiv.style.display = "none";
        fdrdDiv.style.display = "block";
        panel.style.display = "block";
        buildFdTable();
    } else {
        panel.style.display = "none";
    }
}

function buildLoanTable() {
    const container = document.getElementById("loan-chart");
    container.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Loan Type</th>
                    <th>Fixed Interest Rate</th>
                </tr>
            </thead>
            <tbody>
                ${LOAN_RATES.map(r => `
                <tr>
                    <td>${r.label}</td>
                    <td class="highlight">${r.rate.toFixed(2)}%</td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

function buildFdTable() {
    const table = document.getElementById("fd-table");
    table.innerHTML = `
        <table class="data-table">
            <thead>
                <tr>
                    <th>Tenure</th>
                    <th>General</th>
                    <th>Senior Citizen</th>
                </tr>
            </thead>
            <tbody>
                ${FD_RATES.map(r => `
                <tr>
                    <td>${r.tenure}</td>
                    <td class="highlight">${r.general}</td>
                    <td class="highlight">${r.senior}</td>
                </tr>`).join("")}
            </tbody>
        </table>`;
}

// ── New Features: Counter, Calculations, Forms ─────────────────────────────

function updateCounter(name) {
    const badge = document.getElementById("counter-badge");
    const nameSpan = document.getElementById("counter-name");
    if (name) {
        nameSpan.textContent = name;
        badge.style.display = "flex";
    } else {
        badge.style.display = "none";
    }
}

function renderCalculations(calc) {
    const container = document.getElementById("calc-container");
    if (!calc || calc.type === "none") {
        container.style.display = "none";
        return;
    }

    container.style.display = "grid";
    const fNum = (v) => v !== undefined && v !== null ? v.toLocaleString('en-IN') : "---";

    if (calc.type === "emi") {
        html = `
            <div class="calc-card">
                <div class="calc-title"><span class="material-symbols-outlined">calculate</span> EMI Estimate</div>
                <div class="calc-grid">
                    <div class="calc-item"><span class="calc-label">Monthly EMI</span><span class="calc-value">₹${fNum(calc.emi)}</span></div>
                    <div class="calc-item"><span class="calc-label">Interest Rate</span><span class="calc-value">${calc.rate_used || "---"}%</span></div>
                    <div class="calc-item"><span class="calc-label">Total Payment</span><span class="calc-value">₹${fNum(calc.total_payment)}</span></div>
                    <div class="calc-item"><span class="calc-label">Total Interest</span><span class="calc-value">₹${fNum(calc.total_interest)}</span></div>

                </div>
            </div>
        `;
    } else if (calc.type === "fd" || calc.type === "rd") {
        html = `
            <div class="calc-card">
                <div class="calc-title"><span class="material-symbols-outlined">event_available</span> ${(calc.type || "").toUpperCase()} Maturity</div>
                <div class="calc-grid">
                    <div class="calc-item"><span class="calc-label">Maturity Amount</span><span class="calc-value">₹${fNum(calc.maturity)}</span></div>
                    <div class="calc-item"><span class="calc-label">Interest Earned</span><span class="calc-value">₹${fNum(calc.interest_earned)}</span></div>
                    <div class="calc-item"><span class="calc-label">Rate Applied</span><span class="calc-value">${calc.rate_used || "---"}%</span></div>
                </div>
            </div>
        `;
    } else if (calc.type === "eligibility") {
        html = `
            <div class="calc-card">
                <div class="calc-title"><span class="material-symbols-outlined">verified_user</span> Loan Eligibility</div>
                <div class="calc-grid">
                    <div class="calc-item"><span class="calc-label">Max Eligible Loan</span><span class="calc-value">₹${fNum(calc.max_loan)}</span></div>
                    <div class="calc-item"><span class="calc-label">Suggested EMI Cap</span><span class="calc-value">₹${fNum(calc.suggested_emi_limit)}</span></div>
                </div>
            </div>
        `;
    }

    container.innerHTML = html;
}

function renderForm(template) {
    const container = document.getElementById("form-container");
    const grid = document.getElementById("form-fields-grid");
    const typeNameSpan = document.getElementById("form-type-name");

    if (!template) {
        container.style.display = "none";
        currentActiveFormType = null;
        return;
    }

    const newType = (template.type || "Form").replace(/_/g, " ").toUpperCase();
    const currentType = typeNameSpan.textContent;

    // ── CASE A: Same form is already visible: Precision Update ──
    if (container.style.display === "block" && currentType === newType) {
        for (const [field, val] of Object.entries(template.prefill)) {
            if (!val) continue;

            const fieldDiv = grid.querySelector(`[data-field="${field}"]`);
            if (fieldDiv) {
                const input = fieldDiv.querySelector("input");
                // Only update if current value is empty or not manually edited
                if (!input.value || !fieldDiv.classList.contains("manually-edited")) {
                    const isNewlyChanged = input.value !== val.toString();
                    input.value = val;
                    fieldDiv.classList.add("prefilled");
                    if (isNewlyChanged) {
                        fieldDiv.classList.add("new-extract");
                        // remove class after animation so it can re-trigger later
                        setTimeout(() => fieldDiv.classList.remove("new-extract"), 2000);
                    }
                }
            }
        }
        return; // DONE: Smoothly updated existing inputs
    }

    // ── CASE B: New form type or initial load: full render ──
    currentActiveFormType = template.type;
    container.style.display = "block";
    container.classList.remove("collapsed");
    typeNameSpan.textContent = newType;

    grid.innerHTML = template.fields.map(field => {
        const val = template.prefill[field] || "";
        const labelText = field.replace(/_/g, " ").toUpperCase();
        const isPrefilled = val !== "";
        return `
            <div class="form-field ${isPrefilled ? 'prefilled' : ''}" data-field="${field}">
                <label>${labelText}</label>
                <input type="text" value="${val}" placeholder="Required..." onchange="this.parentElement.classList.add('manually-edited')">
            </div>
        `;
    }).join("");
}

function toggleFormCollapse() {
    document.getElementById("form-container").classList.toggle("collapsed");
}

function printForm() {
    const type = document.getElementById("form-type-name").textContent;
    const inputs = document.querySelectorAll("#form-fields-grid input");
    const labels = document.querySelectorAll("#form-fields-grid label");

    let printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <html>
            <head>
                <title>Union Bank - ${type}</title>
                <style>
                    body { font-family: sans-serif; padding: 40px; }
                    .header { text-align: center; border-bottom: 2px solid #000; margin-bottom: 30px; }
                    .field { margin-bottom: 15px; border-bottom: 1px dotted #ccc; display: flex; justify-content: space-between; }
                    .label { font-weight: bold; color: #555; }
                    .value { font-family: monospace; font-size: 1.1em; }
                </style>
            </head>
            <body>
                <div class="header">
                    <h1>UNION BANK OF INDIA</h1>
                    <h3>${type}</h3>
                </div>
                ${Array.from(inputs).map((input, i) => `
                    <div class="field">
                        <span class="label">${labels[i].textContent}</span>
                        <span class="value">${input.value || '________________'}</span>
                    </div>
                `).join("")}
            </body>
        </html>
    `);
    printWindow.document.close();
    printWindow.print();
}

// ── Core Audio Logic ───────────────────────────────────────────────────────

async function toggleRecording() {
    if (!isRecording) await startRecording();
    else await stopRecording();
}

async function startRecording() {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    mediaRecorder = new MediaRecorder(stream);
    audioChunks = [];
    mediaRecorder.ondataavailable = e => audioChunks.push(e.data);
    mediaRecorder.start();
    isRecording = true;
    const btn = document.getElementById("mic-btn");
    btn.innerHTML = '<span class="material-symbols-outlined">stop_circle</span> Stop Recording';
    btn.classList.add("recording");
    setStatus("Recording...");
    document.getElementById("clarification-box").style.display = "none";
}

async function stopRecording() {
    return new Promise(resolve => {
        mediaRecorder.onstop = async () => {
            const blob = new Blob(audioChunks, { type: "audio/webm" });
            await processCustomerAudio(blob);
            resolve();
        };
        mediaRecorder.stop();
        mediaRecorder.stream.getTracks().forEach(t => t.stop());
        isRecording = false;
        const btn = document.getElementById("mic-btn");
        btn.innerHTML = '<span class="material-symbols-outlined">mic</span> Hold to Speak';
        btn.classList.remove("recording");
        setStatus("Processing...");
    });
}

async function processCustomerAudio(blob) {
    const formData = new FormData();
    formData.append("audio", blob, "audio.webm");
    formData.append("conversation", JSON.stringify(conversation));
    if (currentActiveFormType) {
        formData.append("active_form", currentActiveFormType);
    }
    document.getElementById("status").className = "status processing";

    try {
        const res = await fetch("/api/customer-speak", { method: "POST", body: formData });
        const data = await res.json();

        if (data.detail) {
            throw new Error(data.detail);
        }

        currentLanguage = data.detected_language || "hindi";
        document.getElementById("detected-lang").textContent =
            `Language: ${(data.detected_language || "").toUpperCase()}`;
        document.getElementById("customer-transcript").textContent = data.original_text || "";
        document.getElementById("english-translation").textContent = data.english_translation || "";

        const clarBox = document.getElementById("clarification-box");

        // ── 1. Handle Clarification ──
        if (data.needs_clarification && data.follow_up_question) {
            document.getElementById("clarification-q-en").textContent = data.follow_up_question;
            document.getElementById("clarification-q-vern").textContent = data.follow_up_question_translated || "";
            clarBox.style.display = "block";
            if (data.follow_up_audio) {
                new Audio(`data:audio/mp3;base64,${data.follow_up_audio}`).play();
            }
            document.getElementById("intent-box").style.display = "none";
            document.getElementById("process-guide").style.display = "none";
            updateCounter(null);
            renderCalculations(null);
            renderForm(null);
            showFinPanel(null);
        } else {
            clarBox.style.display = "none";

            // ── 2. Handle Intent & Guide ──
            if (data.intent && data.intent !== "other") {
                document.getElementById("intent-box").style.display = "block";
                document.getElementById("intent-text").textContent = (data.intent || "").replace(/_/g, " ").toUpperCase();
            } else {
                document.getElementById("intent-box").style.display = "none";
            }

            if (data.process_guide && data.process_guide.length > 0) {
                document.getElementById("process-guide").style.display = "block";
                const steps = document.getElementById("guide-steps");
                steps.innerHTML = data.process_guide.map(s => `<li>${s}</li>`).join("");
            } else {
                document.getElementById("process-guide").style.display = "none";
            }

            // ── 3. Handle Counter ──
            updateCounter(data.counter_name);

            // ── 4. Handle Calculations ──
            renderCalculations(data.calculation_results);
            if (data.calculation_tts_audio) {
                new Audio(`data:audio/mp3;base64,${data.calculation_tts_audio}`).play();
            }

            // ── 5. Handle Forms ──
            renderForm(data.form_template);

            // ── 6. Reference Panel ──
            showFinPanel(data.intent);
        }

        // ── 7. Logging ──
        conversation.push({ role: "customer", text: data.original_text, language: data.detected_language });
        addLog("customer", data.detected_language, data.original_text, data.english_translation);
        document.getElementById("status").className = "status";
        setStatus("Ready");

    } catch (err) {
        document.getElementById("status").className = "status error";
        setStatus("Error: " + err.message);
    }
}

async function sendReply() {
    const replyText = document.getElementById("staff-reply").value.trim();
    if (!replyText) return;
    document.getElementById("status").className = "status processing";
    setStatus("Translating...");
    try {
        const res = await fetch("/api/staff-reply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ reply_text: replyText, target_language: currentLanguage })
        });
        const data = await res.json();
        document.getElementById("reply-translated").textContent = `Translated: ${data.translated_reply}`;
        new Audio(`data:audio/mp3;base64,${data.audio_base64}`).play();
        conversation.push({ role: "staff", text: replyText, language: "english" });
        addLog("staff", "english", replyText, data.translated_reply);
        document.getElementById("staff-reply").value = "";
        document.getElementById("status").className = "status";
        setStatus("Ready");
    } catch (err) {
        document.getElementById("status").className = "status error";
        setStatus("Error: " + err.message);
    }
}

async function generateSummary() {
    if (conversation.length === 0) return alert("No conversation yet.");
    setStatus("Generating summary...");
    try {
        const res = await fetch("/api/summary", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ conversation, customer_language: currentLanguage })
        });
        const data = await res.json();
        document.getElementById("summary-english").textContent = data.english_summary;
        document.getElementById("summary-vernacular").textContent = data.vernacular_summary;
        document.getElementById("summary-lang-label").textContent =
            currentLanguage.charAt(0).toUpperCase() + currentLanguage.slice(1);
        document.getElementById("summary-modal").style.display = "flex";
        setStatus("Ready");
    } catch (err) { setStatus("Error: " + err.message); }
}

function closeSummary() { document.getElementById("summary-modal").style.display = "none"; }

function addLog(role, language, original, translation) {
    const entry = document.createElement("div");
    entry.className = `log-entry ${role}`;
    entry.innerHTML = `
    <span class="log-role"><span class="material-symbols-outlined">${role === "customer" ? "person" : "badge"}</span> ${role === "customer" ? "Customer" : "Staff"}</span>
    <span class="log-lang">[${language}]</span>
    <span class="log-text">${original}</span>
    <span class="log-translation">→ ${translation}</span>
  `;
    document.getElementById("log-entries").appendChild(entry);
}

function setStatus(msg) { document.getElementById("status").textContent = msg; }