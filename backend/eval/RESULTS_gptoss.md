# Evaluation results

Model `openai/gpt-oss-120b` on 150 gold-text cases (0 errored). Whisper is bypassed, so this measures the language pipeline given a correct transcript.
Non-English cases were written by the author and are flagged for native-speaker review.

| Metric | Value |
|---|---:|
| Intent accuracy | 99.3% |
| Counter routing accuracy (soft) | 99.3% |
| Entity precision / recall / F1 | 1.00 / 1.00 / 1.00 |
| Clarification recall (ambiguous requests) | 100% |
| Clarification false-alarm rate | 0.0% |
| Code-mixed (Hinglish) intent accuracy | 100.0% |
| LLM stage latency p50 / p95 | 1.05s / 1.90s |

## Per language

| Language | Intent accuracy | Cases |
|---|---:|---:|
| bengali | 92% | 12 |
| english | 100% | 27 |
| gujarati | 100% | 12 |
| hindi | 100% | 39 |
| kannada | 100% | 12 |
| marathi | 100% | 12 |
| odia | 100% | 12 |
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
| fd_rd_enquiry | 100% | 11 |
| fund_transfer | 100% | 9 |
| kisan_credit_card | 100% | 6 |
| kyc_update | 100% | 9 |
| loan_enquiry | 100% | 11 |
| mudra_loan | 86% | 7 |
| nomination_update | 100% | 7 |
| other | 100% | 17 |
| tax_certificate_request | 100% | 7 |

## Most common confusions

| Expected | Predicted | Count |
|---|---|---:|
| mudra_loan | loan_enquiry | 1 |

Corpus BLEU against the reference translations: 72.2

## Note

The post-processing rules were tuned after an earlier run on this same set (gpt-oss: 94.0% intent, 0.95 entity F1), so this is not a held-out measurement.
