# Speech-to-text results

Groq `whisper-large-v3`, language hint, 64 clips. WER and CER are averaged per clip.
Synthetic clips are clean neural-TTS speech and overstate real-world accuracy.

## heldout-synthetic (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 54.2% | 16.2% | 4/4 |
| english | 4 | 0.0% | 0.0% | 4/4 |
| gujarati | 4 | 20.3% | 8.6% | 4/4 |
| hindi | 4 | 7.5% | 4.4% | 4/4 |
| kannada | 4 | 34.4% | 11.7% | 4/4 |
| marathi | 4 | 43.8% | 10.8% | 4/4 |
| tamil | 4 | 10.0% | 2.9% | 4/4 |
| telugu | 4 | 13.6% | 2.7% | 4/4 |
| **all** | 32 | 23.0% | 7.2% | 32/32 |

## heldout-synthetic+babble-snr10dB+phone (32 clips)

| Language | Clips | WER | CER | Language ID |
|---|---:|---:|---:|---:|
| bengali | 4 | 92.2% | 41.4% | 4/4 |
| english | 4 | 5.0% | 1.0% | 4/4 |
| gujarati | 4 | 46.6% | 33.2% | 4/4 |
| hindi | 4 | 16.7% | 7.5% | 4/4 |
| kannada | 4 | 87.5% | 41.1% | 4/4 |
| marathi | 4 | 52.0% | 16.5% | 4/4 |
| tamil | 4 | 23.1% | 4.0% | 4/4 |
| telugu | 4 | 77.1% | 23.9% | 4/4 |
| **all** | 32 | 50.0% | 21.1% | 32/32 |
