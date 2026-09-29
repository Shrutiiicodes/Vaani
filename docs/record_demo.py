"""Record a real customer turn in the dashboard and save docs/demo.gif.

Makes real Groq calls (uses GROQ_API_KEY from .env). Needs `pip install playwright`;
it drives an installed Edge or Chrome (BROWSER_CHANNEL=msedge|chrome), so no browser download.

    python docs/record_demo.py
"""
import base64
import io
import os
import subprocess
import sys
import tempfile
import time
import urllib.request

from PIL import Image
from playwright.sync_api import sync_playwright

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PASSWORD = "demo-recording-pass"
CLIP = os.path.join(REPO, "backend", "eval", "audio", "hindi_home_loan.mp3")
PORT = 8010

db = os.path.join(tempfile.mkdtemp(), "demo.db").replace("\\", "/")
env = {**os.environ, "DATABASE_URL": f"sqlite:///{db}", "STAFF_USERNAME": "priya",
       "STAFF_PASSWORD": PASSWORD, "RATE_LIMIT_ENABLED": "false", "BANK_NAME": "Demo Bank"}
server = subprocess.Popen([sys.executable, "-m", "uvicorn", "main:app", "--port", str(PORT)],
                          cwd=os.path.join(REPO, "backend"), env=env,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
for _ in range(40):
    try:
        urllib.request.urlopen(f"http://localhost:{PORT}/health", timeout=1)
        break
    except Exception:
        time.sleep(0.5)

frames = []   # (image, duration ms)


def snap(page, ms):
    frames.append((Image.open(io.BytesIO(page.screenshot())).convert("RGB"), ms))


try:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel=os.getenv("BROWSER_CHANNEL", "msedge"))
        page = browser.new_page(viewport={"width": 1280, "height": 820})
        page.goto(f"http://localhost:{PORT}/")
        page.wait_for_selector("#login-user")
        page.fill("#login-user", "priya")
        page.fill("#login-pw", PASSWORD)
        snap(page, 1200)
        page.click("form.login-content button[type=submit]")
        page.wait_for_selector("#login-overlay", state="hidden")
        page.wait_for_timeout(600)
        snap(page, 1400)

        # Feed a recorded clip through the same code path the microphone uses.
        clip_b64 = base64.b64encode(open(CLIP, "rb").read()).decode()
        page.evaluate("""(b64) => {
            const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
            processCustomerAudio(new Blob([bytes], {type: 'audio/mpeg'}), 'clip.mp3');
        }""", clip_b64)

        # Capture the stream arriving: each change of status or text boxes is a frame.
        last = None
        deadline = time.time() + 60
        while time.time() < deadline:
            status = page.inner_text("#status")
            key = (status[:14], page.inner_text("#english-translation")[:20], page.inner_text("#customer-transcript")[:20])
            if key != last:
                last = key
                snap(page, 1000)
            if status.startswith("Ready ·") or status.startswith("Error"):
                break
            page.wait_for_timeout(100)
        page.wait_for_timeout(400)
        snap(page, 2600)

        # Scroll to the pre-filled form and the rates table.
        page.mouse.wheel(0, 420)
        page.wait_for_timeout(400)
        snap(page, 2400)
        page.mouse.wheel(0, -420)
        page.wait_for_timeout(300)

        # Staff replies in English; the customer hears Hindi.
        page.fill("#staff-reply", "Please bring your last 3 salary slips and your PAN card.")
        snap(page, 1200)
        page.click(".send-btn")
        page.wait_for_function("document.getElementById('reply-translated').textContent.length > 0", timeout=30000)
        page.wait_for_timeout(300)
        snap(page, 2600)

        page.click("text=History")
        page.wait_for_selector(".history-row", timeout=10000)
        page.wait_for_timeout(300)
        snap(page, 2200)
        browser.close()
finally:
    server.terminate()

W = 960
out = [(img.resize((W, round(img.height * W / img.width)), Image.LANCZOS)
        .quantize(colors=128, method=Image.MEDIANCUT, dither=Image.NONE), ms) for img, ms in frames]
gif = os.path.join(REPO, "docs", "demo.gif")
out[0][0].save(gif, save_all=True, append_images=[f for f, _ in out[1:]],
               duration=[ms for _, ms in out], loop=0, optimize=True)
print(len(out), "frames,", os.path.getsize(gif) // 1024, "KB ->", gif)
