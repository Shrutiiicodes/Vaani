"""
Make a "busy branch" version of the synthetic banking clips for the STT eval.

Each synthetic clip (banking sentence, neural TTS voice) gets:
  - background babble: 3 overlapping real speakers from the FLEURS sample, mixed in at a
    chosen signal-to-noise ratio (default 10 dB, a noisy counter)
  - phone-microphone band limiting to 300-3400 Hz

The voice is still synthetic; only the conditions are realistic. Results are reported
under their own source label. Needs fetch_fleurs.py to have run (babble comes from it).

Usage:
  python backend/eval/make_noisy.py            # 10 dB SNR
  python backend/eval/make_noisy.py --snr 5
"""
import argparse
import glob
import json
import os

import numpy as np
import soundfile as sf

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
SR = 16000


def load_16k(path: str) -> np.ndarray:
    audio, sr = sf.read(path, dtype="float64", always_2d=True)
    audio = audio.mean(axis=1)
    if sr != SR:   # linear interpolation is plenty for speech going into Whisper
        audio = np.interp(np.arange(0, len(audio), sr / SR), np.arange(len(audio)), audio)
    return audio


def phone_band(audio: np.ndarray) -> np.ndarray:
    spectrum = np.fft.rfft(audio)
    freqs = np.fft.rfftfreq(len(audio), 1 / SR)
    spectrum[(freqs < 300) | (freqs > 3400)] = 0
    return np.fft.irfft(spectrum, len(audio))


def babble(pool: list, length: int, rng: np.random.Generator) -> np.ndarray:
    mix = np.zeros(length)
    for path in rng.choice(pool, size=3, replace=False):
        voice = load_16k(path)
        voice = np.tile(voice, length // len(voice) + 1)
        start = rng.integers(0, len(voice) - length + 1)
        mix += voice[start:start + length] / (np.std(voice) + 1e-9)
    return mix


def main():
    ap = argparse.ArgumentParser(description="Noisy-branch variant of the synthetic STT clips")
    ap.add_argument("--snr", type=float, default=10.0, help="speech-to-babble ratio in dB")
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args()

    pool = sorted(glob.glob(os.path.join(AUDIO, "fleurs", "*", "*.wav")))
    if len(pool) < 3:
        raise SystemExit("Run fetch_fleurs.py first: babble is made from real FLEURS speakers.")
    with open(os.path.join(AUDIO, "manifest.json"), encoding="utf-8") as f:
        clean = [m for m in json.load(f) if m["source"] == "synthetic-edge-tts"]

    rng = np.random.default_rng(args.seed)
    tag = f"snr{args.snr:g}"
    out_dir = os.path.join(AUDIO, f"noisy_{tag}")
    os.makedirs(out_dir, exist_ok=True)
    manifest = []
    for m in clean:
        speech = load_16k(os.path.join(AUDIO, m["file"]))
        noise = babble(pool, len(speech), rng)
        noise *= np.std(speech) / (np.std(noise) * 10 ** (args.snr / 20))
        mixed = phone_band(speech + noise)
        mixed *= 0.9 / (np.max(np.abs(mixed)) + 1e-9)
        name = os.path.splitext(os.path.basename(m["file"]))[0] + ".ogg"
        sf.write(os.path.join(out_dir, name), mixed, SR, format="OGG", subtype="VORBIS")
        manifest.append({**m, "file": f"noisy_{tag}/{name}", "source": f"synthetic+babble-{tag}dB+phone"})
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(manifest)} noisy clips at {args.snr:g} dB SNR -> {out_dir}")


if __name__ == "__main__":
    main()
