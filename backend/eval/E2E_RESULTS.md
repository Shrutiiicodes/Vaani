# End-to-end results: audio to intent

Whisper large-v3 with the language hint, then `qwen/qwen3.8-27b`. Banking clips only; each is scored against the intent of the test case it was voiced from.

| Clip set | Clips | Mean CER | Intent accuracy |
|---|---:|---:|---:|
| synthetic+babble-snr10dB+phone | 32 | 18.9% | 23/32 (72%) |
| synthetic-edge-tts | 32 | 11.3% | 31/32 (97%) |

## Misses

| Clip set | Language | Case | Expected | Predicted | CER |
|---|---|---:|---|---|---:|
| synthetic-edge-tts | bengali | 72 | tax_certificate_request | account_opening | 35% |
| synthetic+babble-snr10dB+phone | marathi | 65 | nomination_update | other | 21% |
| synthetic+babble-snr10dB+phone | bengali | 38 | kyc_update | account_opening | 52% |
| synthetic+babble-snr10dB+phone | bengali | 72 | tax_certificate_request | cash_transaction | 48% |
| synthetic+babble-snr10dB+phone | tamil | 79 | debit_card_services | fd_rd_enquiry | 19% |
| synthetic+babble-snr10dB+phone | telugu | 86 | account_closure | complaint | 32% |
| synthetic+babble-snr10dB+phone | kannada | 50 | account_opening | loan_enquiry | 40% |
| synthetic+babble-snr10dB+phone | kannada | 91 | kyc_update | account_opening | 35% |
| synthetic+babble-snr10dB+phone | kannada | 94 | fund_transfer | cash_transaction | 9% |
| synthetic+babble-snr10dB+phone | gujarati | 99 | mudra_loan | cheque_services | 7% |
