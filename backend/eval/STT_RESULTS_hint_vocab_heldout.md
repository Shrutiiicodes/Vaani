# Speech-to-text results

Groq `whisper-large-v3`, language hint + banking vocabulary prompt, 64 clips. WER and CER are averaged per clip.
Synthetic clips are clean neural-TTS speech and overstate real-world accuracy.

## heldout-synthetic (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 41.4% | 11.4% | 4/4 |
| english | 4 | 0.0% | 0.0% | 4/4 |
| gujarati | 4 | 22.6% | 10.6% | 4/4 |
| hindi | 4 | 5.0% | 1.1% | 4/4 |
| kannada | 4 | 51.9% | 11.6% | 4/4 |
| marathi | 4 | 33.8% | 9.4% | 4/4 |
| tamil | 4 | 10.0% | 2.9% | 4/4 |
| telugu | 4 | 5.0% | 1.0% | 4/4 |
| **all** | 32 | 21.2% | 6.0% | 32/32 |

## heldout-synthetic+babble-snr10dB+phone (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 87.1% | 38.6% | 4/4 |
| english | 4 | 5.0% | 1.0% | 4/4 |
| gujarati | 4 | 38.9% | 32.2% | 4/4 |
| hindi | 4 | 9.2% | 3.0% | 4/4 |
| kannada | 4 | 85.0% | 43.4% | 4/4 |
| marathi | 4 | 45.1% | 15.3% | 4/4 |
| tamil | 4 | 28.1% | 8.9% | 4/4 |
| telugu | 4 | 67.1% | 23.5% | 4/4 |
| **all** | 32 | 45.7% | 20.7% | 32/32 |
