"""
Speech-to-text evaluation: Groq Whisper on audio clips listed in audio/manifest.json.

Reports per language: word error rate (WER), character error rate (CER, fairer for
agglutinative Indic languages) and language-identification accuracy.

Manifest entries: {"file": "synthetic/hindi_16.mp3", "language": "hindi", "text": "...", "source": "..."}
  source = "synthetic-edge-tts" for generated clips, "human" for real recordings.
  Results are always split by source: synthetic TTS audio is clean studio speech and
  flatters Whisper, so only the human numbers say anything about a real branch.

Usage:
  python run_stt_eval.py --synthesize 3     # add 3 synthetic clips per language, then evaluate
  python run_stt_eval.py                    # evaluate whatever the manifest lists
  python run_stt_eval.py --hint             # pass the known language to Whisper instead of auto-detect

Odia is skipped: Whisper has no Odia language and no TTS voice exists for it.
"""
import argparse
import asyncio
import json
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIO = os.path.join(HERE, "audio")
MANIFEST = os.path.join(AUDIO, "manifest.json")
sys.path.insert(0, os.path.join(HERE, ".."))

_PUNCT = re.compile(r"[\s!\"#$%&'()*+,\-./:;<=>?@\[\\\]^_`{|}~।॥“”‘’…]+")
VOICE_B = {  # second voice per language, so clips are not all one speaker
    "hindi": "hi-IN-MadhurNeural", "tamil": "ta-IN-ValluvarNeural", "telugu": "te-IN-MohanNeural",
    "marathi": "mr-IN-ManoharNeural", "bengali": "bn-IN-BashkarNeural", "gujarati": "gu-IN-NiranjanNeural",
    "kannada": "kn-IN-GaganNeural", "english": "en-IN-PrabhatNeural",
}


def normalise(text: str) -> str:
    # Only punctuation is stripped: Indic vowel signs are combining marks, so \w-based
    # cleaning would delete them.
    return _PUNCT.sub(" ", text.lower()).strip()


def load_manifest() -> list:
    manifest = []
    if os.path.exists(MANIFEST):
        with open(MANIFEST, encoding="utf-8") as f:
            manifest = json.load(f)
    return manifest + discover_human_clips({m["file"] for m in manifest})


def discover_human_clips(known: set) -> list:
    """Recordings dropped into audio/human/ as <language>_<case id>.<ext> need no manifest entry:
    the reference text is taken from that case in test_cases.json."""
    folder = os.path.join(AUDIO, "human")
    if not os.path.isdir(folder):
        return []
    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = {c["id"]: c for c in json.load(f)}
    found = []
    for name in sorted(os.listdir(folder)):
        m = re.fullmatch(r"([a-z]+)_(\d+)\.(m4a|mp3|wav|webm|ogg|aac|flac)", name.lower())
        rel = f"human/{name}"
        if not m or rel in known or int(m.group(2)) not in cases:
            continue
        case = cases[int(m.group(2))]
        found.append({"file": rel, "language": m.group(1), "text": case["audio_text"],
                      "source": "human", "case_id": case["id"]})
    return found


async def synthesize(per_language: int):
    from tts import VOICES, _edge
    with open(os.path.join(HERE, "test_cases.json"), encoding="utf-8") as f:
        cases = [c for c in json.load(f) if c["source_lang"] in VOICES and not c.get("code_mixed")]
    manifest = load_manifest()
    have = {m["file"] for m in manifest}
    by_lang = defaultdict(list)
    for c in cases:
        by_lang[c["source_lang"]].append(c)
    os.makedirs(os.path.join(AUDIO, "synthetic"), exist_ok=True)
    for lang, lang_cases in by_lang.items():
        # Spread picks across the language's cases rather than taking the first N.
        step = max(1, len(lang_cases) // per_language)
        for i, case in enumerate(lang_cases[::step][:per_language]):
            rel = f"synthetic/{lang}_{case['id']}.mp3"
            if rel in have:
                continue
            voices = [VOICES[lang], VOICE_B[lang]][:: 1 if i % 2 == 0 else -1]
            for voice in voices:    # the service occasionally returns nothing; try the other voice
                try:
                    audio = await _edge(case["audio_text"], voice)
                    break
                except Exception as e:
                    print(f"  {voice} failed for case {case['id']}: {e}")
            else:
                continue
            with open(os.path.join(AUDIO, rel), "wb") as f:
                f.write(audio)
            manifest.append({"file": rel, "language": lang, "text": case["audio_text"],
                             "source": "synthetic-edge-tts", "voice": voice, "case_id": case["id"]})
            with open(MANIFEST, "w", encoding="utf-8", newline="\n") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            print(f"synthesised {rel} ({voice})")


async def evaluate(args):
    import jiwer

    from banking_context import LANGUAGES
    from stt import transcribe_audio

    manifest = load_manifest()
    if not manifest:
        raise SystemExit("No clips. Record some (see docstring) or run with --synthesize N.")

    rows = []
    for i, m in enumerate(manifest, 1):
        with open(os.path.join(AUDIO, m["file"]), "rb") as f:
            audio = f.read()
        hint = LANGUAGES.get(m["language"]) if args.hint else None
        try:
            out = await transcribe_audio(audio, os.path.basename(m["file"]), hint)
        except Exception as e:
            print(f"[{i}/{len(manifest)}] {m['file']} ERROR {str(e)[:150]}")
            await asyncio.sleep(args.delay * 3)
            continue
        ref, hyp = normalise(m["text"]), normalise(out["text"] or "")
        row = {**m, "hypothesis": out["text"], "detected": out["language"],
               "lang_ok": out["language"] == m["language"],
               "wer": jiwer.wer(ref, hyp) if hyp else 1.0, "cer": jiwer.cer(ref, hyp) if hyp else 1.0}
        rows.append(row)
        print(f"[{i}/{len(manifest)}] {m['language']:<9} detected={out['language']:<9} "
              f"WER={row['wer']:.2f} CER={row['cer']:.2f} | {out['text'][:60]}", flush=True)
        await asyncio.sleep(args.delay)

    groups = defaultdict(list)
    for r in rows:
        groups[(r["source"], r["language"])].append(r)
    mode = "language hint" if args.hint else "auto-detect"
    lines = ["# Speech-to-text results", "",
             f"Groq `whisper-large-v3`, {mode}, {len(rows)} clips. WER and CER are averaged per clip.",
             "Synthetic clips are clean neural-TTS speech and overstate real-world accuracy.", ""]
    for source in sorted({r["source"] for r in rows}):
        sel = [r for r in rows if r["source"] == source]
        lines += [f"## {source} ({len(sel)} clips)", "",
                  "| Language | Clips | WER | CER | Language ID |", "|---|---:|---:|---:|---:|"]
        for (src, lang), g in sorted(groups.items()):
            if src != source:
                continue
            lines.append(f"| {lang} | {len(g)} | {sum(r['wer'] for r in g) / len(g):.1%} | "
                         f"{sum(r['cer'] for r in g) / len(g):.1%} | {sum(r['lang_ok'] for r in g)}/{len(g)} |")
        lines.append(f"| **all** | {len(sel)} | {sum(r['wer'] for r in sel) / len(sel):.1%} | "
                     f"{sum(r['cer'] for r in sel) / len(sel):.1%} | {sum(r['lang_ok'] for r in sel)}/{len(sel)} |")
        lines.append("")
    report = "\n".join(lines)
    print("\n" + report)
    suffix = "_hint" if args.hint else ""
    with open(os.path.join(HERE, f"STT_RESULTS{suffix}.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(report)
    with open(os.path.join(HERE, f"stt_results{suffix}.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(rows, f, ensure_ascii=False, indent=2)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Whisper STT evaluation")
    ap.add_argument("--synthesize", type=int, metavar="N", help="first add N synthetic clips per language")
    ap.add_argument("--hint", action="store_true", help="pass the known language to Whisper")
    ap.add_argument("--delay", type=float, default=3.0, help="seconds between calls (Whisper free tier: 20/min)")
    args = ap.parse_args()

    from dotenv import load_dotenv
    load_dotenv()
    if args.synthesize:
        asyncio.run(synthesize(args.synthesize))
    asyncio.run(evaluate(args))


if __name__ == "__main__":
    main()
