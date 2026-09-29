# Speech-to-text results

Groq `whisper-large-v3`, language hint, 154 clips. WER and CER are averaged per clip.
Synthetic clips are clean neural-TTS speech and overstate real-world accuracy.

## human-fleurs (90 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 10 | 71.0% | 30.3% | 10/10 |
| english | 10 | 5.2% | 3.0% | 10/10 |
| gujarati | 10 | 51.8% | 27.4% | 10/10 |
| hindi | 10 | 24.8% | 9.4% | 10/10 |
| kannada | 10 | 69.7% | 22.4% | 10/10 |
| marathi | 10 | 80.7% | 25.3% | 10/10 |
| odia | 10 | 109.0% | 93.5% | 0/10 |
| tamil | 10 | 54.2% | 23.1% | 10/10 |
| telugu | 10 | 59.9% | 26.2% | 10/10 |
| **all** | 90 | 58.5% | 29.0% | 80/90 |

## synthetic+babble-snr10dB+phone (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 68.5% | 36.0% | 4/4 |
| english | 4 | 4.5% | 0.5% | 4/4 |
| gujarati | 4 | 39.2% | 11.3% | 4/4 |
| hindi | 4 | 32.8% | 21.0% | 4/4 |
| kannada | 4 | 77.1% | 29.5% | 4/4 |
| marathi | 4 | 66.8% | 21.4% | 4/4 |
| tamil | 4 | 33.8% | 14.3% | 4/4 |
| telugu | 4 | 65.4% | 17.2% | 4/4 |
| **all** | 32 | 48.5% | 18.9% | 32/32 |

## synthetic-edge-tts (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 57.3% | 26.3% | 4/4 |
| english | 4 | 4.5% | 0.5% | 4/4 |
| gujarati | 4 | 19.4% | 5.6% | 4/4 |
| hindi | 4 | 8.1% | 5.5% | 4/4 |
| kannada | 4 | 62.6% | 17.8% | 4/4 |
| marathi | 4 | 43.0% | 15.2% | 4/4 |
| tamil | 4 | 8.3% | 6.5% | 4/4 |
| telugu | 4 | 50.5% | 13.0% | 4/4 |
| **all** | 32 | 31.7% | 11.3% | 32/32 |
