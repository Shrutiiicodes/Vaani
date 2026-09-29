"""
Fetch a small sample of real human speech from Google's FLEURS dataset for the STT eval.

FLEURS (https://huggingface.co/datasets/google/fleurs, CC-BY 4.0) is native speakers
reading Wikipedia sentences aloud. It covers every Vaani language, including Odia.
The sentences are general text, not banking requests: this measures Whisper on real
voices, not on banking vocabulary.

Each language's test audio is a ~250 MB .tar.gz. It is streamed and the connection is
closed after N clips, so only a few MB per language are downloaded. Clips go to
audio/fleurs/ (git-ignored) with their own manifest, which run_stt_eval.py picks up.

Usage:
  python backend/eval/fetch_fleurs.py            # 10 test clips per language
  python backend/eval/fetch_fleurs.py --per-language 20
"""
import argparse
import csv
import io
import json
import os
import sys
import tarfile

import httpx

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "audio", "fleurs")
BASE = "https://huggingface.co/datasets/google/fleurs/resolve/main/data"

CONFIGS = {  # Vaani language -> FLEURS config
    "hindi": "hi_in", "tamil": "ta_in", "telugu": "te_in", "marathi": "mr_in", "bengali": "bn_in",
    "gujarati": "gu_in", "kannada": "kn_in", "odia": "or_in",
    "english": "en_us",   # FLEURS has no Indian English; US speakers
}


class _Stream(io.RawIOBase):
    """File-like view over an HTTP byte stream, so tarfile can read it sequentially."""

    def __init__(self, response):
        self._chunks = response.iter_bytes(64 * 1024)
        self._buf = b""
        self.downloaded = 0

    def readable(self):
        return True

    def readinto(self, b):
        while not self._buf:
            try:
                self._buf = next(self._chunks)
                self.downloaded += len(self._buf)
            except StopIteration:
                return 0
        n = min(len(b), len(self._buf))
        b[:n] = self._buf[:n]
        self._buf = self._buf[n:]
        return n


def fetch_language(client: httpx.Client, lang: str, config: str, n: int) -> list:
    tsv = client.get(f"{BASE}/{config}/test.tsv", follow_redirects=True)
    tsv.raise_for_status()
    # Columns: id, file name, raw transcription, normalised transcription, chars, samples, gender
    rows = {r[1]: r for r in csv.reader(io.StringIO(tsv.text), delimiter="\t", quoting=csv.QUOTE_NONE) if len(r) >= 3}

    os.makedirs(os.path.join(OUT, lang), exist_ok=True)
    entries = []
    with client.stream("GET", f"{BASE}/{config}/audio/test.tar.gz", follow_redirects=True) as r:
        r.raise_for_status()
        stream = _Stream(r)
        with tarfile.open(fileobj=io.BufferedReader(stream, 1 << 20), mode="r|gz") as tar:
            for member in tar:
                name = os.path.basename(member.name)
                if not member.isfile() or name not in rows:
                    continue
                data = tar.extractfile(member).read()
                rel = f"fleurs/{lang}/{name}"
                with open(os.path.join(HERE, "audio", rel), "wb") as f:
                    f.write(data)
                row = rows[name]
                entries.append({"file": rel, "language": lang, "text": row[2], "source": "human-fleurs",
                                "fleurs_id": row[0], "gender": row[6] if len(row) > 6 else None})
                if len(entries) >= n:
                    break
        mb = stream.downloaded / 1e6
    print(f"{lang:<9} {len(entries)} clips, {mb:.1f} MB downloaded", flush=True)
    return entries


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Fetch FLEURS clips for the STT eval")
    ap.add_argument("--per-language", type=int, default=10)
    args = ap.parse_args()

    manifest = []
    with httpx.Client(timeout=120) as client:
        for lang, config in CONFIGS.items():
            manifest += fetch_language(client, lang, config, args.per_language)
    with open(os.path.join(OUT, "manifest.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    print(f"{len(manifest)} clips -> {OUT}")


if __name__ == "__main__":
    main()
