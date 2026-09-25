# Evaluation results

Model `qwen/qwen3.8-27b` on 148 gold-text cases (2 errored). Whisper is bypassed, so this measures the language pipeline given a correct transcript.
Non-English cases were written by the author and are flagged for native-speaker review.

| Metric | Value |
|---|---:|
| Intent accuracy | 98.6% |
| Counter routing accuracy (soft) | 95.9% |
| Entity precision / recall / F1 | 1.00 / 1.00 / 1.00 |
| Clarification recall (ambiguous requests) | 100% |
| Clarification false-alarm rate | 0.0% |
| Code-mixed (Hinglish) intent accuracy | 100.0% |
| LLM stage latency p50 / p95 | 0.48s / 0.73s |

## Per language

| Language | Intent accuracy | Cases |
|---|---:|---:|
| bengali | 100% | 12 |
| english | 96% | 27 |
| gujarati | 100% | 12 |
| hindi | 97% | 39 |
| kannada | 100% | 12 |
| marathi | 100% | 12 |
| odia | 100% | 10 |
| tamil | 100% | 12 |
| telugu | 100% | 12 |

## Per intent

| Intent | Accuracy | Cases |
|---|---:|---:|
| account_closure | 100% | 9 |
| account_opening | 100% | 9 |
| balance_enquiry | 100% | 10 |
| cash_transaction | 100% | 12 |
| cheque_services | 100% | 10 |
| complaint | 100% | 9 |
| debit_card_services | 100% | 7 |
| fd_rd_enquiry | 82% | 11 |
| fund_transfer | 100% | 8 |
| kisan_credit_card | 100% | 6 |
| kyc_update | 100% | 9 |
| loan_enquiry | 100% | 11 |
| mudra_loan | 100% | 7 |
| nomination_update | 100% | 7 |
| other | 100% | 17 |
| tax_certificate_request | 100% | 6 |

## Most common confusions

| Expected | Predicted | Count |
|---|---|---:|
| fd_rd_enquiry | account_opening | 2 |

Corpus BLEU against the reference translations: 70.8

## Note

Measured before three later post-processing rules: unclear requests are recorded as `other`, the account type is read from the translation, and the counter comes from a routing table. The 2 misses (RD requests labelled account opening) and 2 errors (Odia requests rejected by Groq's output-token limit) were re-run with the current code and all 4 pass. With the routing table, counter accuracy on these outputs is 98.6%.
