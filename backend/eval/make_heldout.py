"""
Build a HELD-OUT banking audio set, for measuring fixes that were tuned on the dev clips.

Picks N test-case sentences per language that have never been voiced (so they share
nothing with the 32 dev clips used for tuning), voices them with neural TTS, and makes
a noisy copy of each with babble from a different random seed.

  audio/heldout/              clean clips          source "heldout-synthetic"
  audio/heldout_noisy_snr10/  same + babble + phone-band  source "heldout-synthetic+babble-snr10dB+phone"

Needs fetch_fleurs.py first (the babble is real FLEURS speakers).

Usage:
  python backend/eval/make_heldout.py
"""
import argparse
import asyncio
import json
import os
import sys
from collections import defaultdict

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
sys.path.insert(0, os.path.join(HERE, ".."))
sys.path.insert(0, HERE)

from make_noisy import SR, babble, load_16k, phone_band  # noqa: E402
from run_stt_eval import VOICE_B  # noqa: E402


async def main(args):
    from tts import VOICES, _edge

    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = json.load(f)
    with open(os.path.join(AUDIO, "manifest.json"), encoding="utf-8") as f:
        used = {m["case_id"] for m in json.load(f)}

    by_lang = defaultdict(list)
    for c in cases:
        if c["source_lang"] in VOICES and not c.get("code_mixed") and c["id"] not in used:
            by_lang[c["source_lang"]].append(c)

    clean_dir, noisy_dir = os.path.join(AUDIO, "heldout"), os.path.join(AUDIO, f"heldout_noisy_snr{args.snr:g}")
    os.makedirs(clean_dir, exist_ok=True)
    os.makedirs(noisy_dir, exist_ok=True)
    pool = sorted(os.path.join(AUDIO, "fleurs", lang, f) for lang in os.listdir(os.path.join(AUDIO, "fleurs"))
                  if os.path.isdir(os.path.join(AUDIO, "fleurs", lang))
                  for f in os.listdir(os.path.join(AUDIO, "fleurs", lang)))
    rng = np.random.default_rng(args.seed)
    clean, noisy = [], []
    for lang, lang_cases in sorted(by_lang.items()):
        step = max(1, len(lang_cases) // args.per_language)
        for i, case in enumerate(lang_cases[::step][: args.per_language]):
            voice = VOICES[lang] if i % 2 == 0 else VOICE_B[lang]
            audio = await _edge(case["audio_text"], voice)
            name = f"{lang}_{case['id']}"
            with open(os.path.join(clean_dir, name + ".mp3"), "wb") as f:
                f.write(audio)
            entry = {"language": lang, "text": case["audio_text"], "voice": voice, "case_id": case["id"]}
            clean.append({**entry, "file": f"heldout/{name}.mp3", "source": "heldout-synthetic"})

            speech = load_16k(os.path.join(clean_dir, name + ".mp3"))
            noise = babble(pool, len(speech), rng)
            noise *= np.std(speech) / (np.std(noise) * 10 ** (args.snr / 20))
            mixed = phone_band(speech + noise)
            mixed *= 0.9 / (np.max(np.abs(mixed)) + 1e-9)
            sf.write(os.path.join(noisy_dir, name + ".ogg"), mixed, SR, format="OGG", subtype="VORBIS")
            noisy.append({**entry, "file": f"{os.path.basename(noisy_dir)}/{name}.ogg",
                          "source": f"heldout-synthetic+babble-snr{args.snr:g}dB+phone"})
            print(f"{name} ({voice})", flush=True)

    for folder, manifest in ((clean_dir, clean), (noisy_dir, noisy)):
        with open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(clean)} held-out clips, clean and noisy")


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Held-out banking audio set")
    ap.add_argument("--per-language", type=int, default=4)
    ap.add_argument("--snr", type=float, default=10.0)
    ap.add_argument("--seed", type=int, default=2026, help="different from make_noisy.py's dev seed (7)")
    asyncio.run(main(ap.parse_args()))
