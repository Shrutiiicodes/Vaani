# Evaluation results

Model `openai/gpt-oss-120b` on 150 gold-text cases (0 errored). Whisper is bypassed, so this measures the language pipeline given a correct transcript.
Non-English cases were written by the author and are flagged for native-speaker review.

| Metric | Value |
|---|---:|
| Intent accuracy | 94.0% |
| Counter routing accuracy (soft) | 88.7% |
| Entity precision / recall / F1 | 1.00 / 0.91 / 0.95 |
| Clarification recall (ambiguous requests) | 100% |
| Clarification false-alarm rate | 0.0% |
| Code-mixed (Hinglish) intent accuracy | 92.3% |
| LLM stage latency p50 / p95 | 1.11s / 2.47s |

## Per language

| Language | Intent accuracy | Cases |
|---|---:|---:|
| bengali | 83% | 12 |
| english | 93% | 27 |
| gujarati | 92% | 12 |
| hindi | 92% | 39 |
| kannada | 100% | 12 |
| marathi | 100% | 12 |
| odia | 100% | 12 |
| tamil | 100% | 12 |
| telugu | 92% | 12 |

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
| fd_rd_enquiry | 91% | 11 |
| fund_transfer | 100% | 9 |
| kisan_credit_card | 100% | 6 |
| kyc_update | 100% | 9 |
| loan_enquiry | 100% | 11 |
| mudra_loan | 86% | 7 |
| nomination_update | 100% | 7 |
| other | 59% | 17 |
| tax_certificate_request | 100% | 7 |

## Most common confusions

| Expected | Predicted | Count |
|---|---|---:|
| other | cash_transaction | 7 |
| mudra_loan | loan_enquiry | 1 |
| fd_rd_enquiry | account_opening | 1 |

Corpus BLEU against the reference translations: 72.9

## Note

Measured before three later post-processing rules: unclear requests are recorded as `other`, the account type is read from the translation, and the counter comes from a routing table. Re-applying them to these same model outputs gives 98.7% intent accuracy, entity F1 1.00 and 99.3% counter routing. 7 of the 9 intent misses were vague money requests labelled `cash_transaction`; all 7 still triggered the clarifying question.
