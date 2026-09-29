# Speech-to-text results

Groq `whisper-large-v3`, auto-detect, 154 clips. WER and CER are averaged per clip.
Synthetic clips are clean neural-TTS speech and overstate real-world accuracy.

## human-fleurs (90 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 10 | 71.0% | 30.3% | 10/10 |
| english | 10 | 5.2% | 3.0% | 10/10 |
| gujarati | 10 | 51.8% | 27.4% | 10/10 |
| hindi | 10 | 50.7% | 30.9% | 7/10 |
| kannada | 10 | 69.7% | 22.4% | 10/10 |
| marathi | 10 | 81.5% | 25.6% | 6/10 |
| odia | 10 | 109.0% | 93.5% | 0/10 |
| tamil | 10 | 52.9% | 14.2% | 10/10 |
| telugu | 10 | 61.0% | 29.2% | 9/10 |
| **all** | 90 | 61.4% | 30.7% | 72/90 |

## synthetic+babble-snr10dB+phone (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 111.3% | 81.1% | 1/4 |
| english | 4 | 4.5% | 0.5% | 4/4 |
| gujarati | 4 | 109.2% | 86.7% | 0/4 |
| hindi | 4 | 72.1% | 50.7% | 2/4 |
| kannada | 4 | 120.5% | 80.4% | 1/4 |
| marathi | 4 | 83.5% | 45.8% | 0/4 |
| tamil | 4 | 33.8% | 14.3% | 4/4 |
| telugu | 4 | 127.3% | 92.4% | 0/4 |
| **all** | 32 | 82.8% | 56.5% | 12/32 |

## synthetic-edge-tts (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 95.8% | 76.6% | 1/4 |
| english | 4 | 4.5% | 0.5% | 4/4 |
| gujarati | 4 | 92.5% | 67.1% | 1/4 |
| hindi | 4 | 8.1% | 5.5% | 4/4 |
| kannada | 4 | 79.3% | 41.7% | 3/4 |
| marathi | 4 | 72.9% | 50.1% | 1/4 |
| tamil | 4 | 8.3% | 6.5% | 4/4 |
| telugu | 4 | 81.8% | 47.0% | 2/4 |
| **all** | 32 | 55.4% | 36.9% | 20/32 |
