# CFA Level I Question-Bank Parser

A self-study tool. It turns scanned and text PDFs of multiple-choice practice questions into a clean, searchable JSON question bank and an offline HTML quiz app. The pipeline handled about 1,000 questions across the 10 CFA Level I topic areas.

Source PDFs and the generated question bank are not included, because the content belongs to its publishers. This repository contains only the pipeline.

## Pipeline

```
PDF pages ──► PyMuPDF text / Tesseract OCR ──► question + answer parsing ──► cleaning & validation
     │                                                                    │
     └──► page images ──► vision-model fallback (Gemini / NVIDIA) ────────┘
                                                                          ▼
                              audit + missing-question reports ◄── questions.json ──► quiz app (index.html)
```

| Script | Role |
|--------|------|
| `extract_questions.py` | Parses question stems, A/B/C options, answer keys, and explanations from PDF text, per topic |
| `extract_vision.py`, `vision_providers.py` | Renders pages to images and sends layouts the text parser can't handle to a vision LLM (Gemini or NVIDIA), with on-disk caching and resumable runs |
| `question_cleaner.py` | Cleans OCR artifacts in stems, options and explanations, and runs lenient and strict validity checks on each multiple-choice question |
| `merge_*.py` | Merge manually checked or re-extracted questions into the bank by stable ID |
| `audit_questions.py`, `report_missing.py` | Compare parsed counts with the expected count per topic, and list missing or incomplete questions |
| `build_full_questions_bank.py`, `build_html.py` | Build the final bank and a single-file HTML quiz app from `index.template.html` |
| `rebuild_all.sh` | Runs the whole pipeline end to end |

## Setup

```bash
export GEMINI_API_KEY=...      # optional, for the vision fallback
export NVIDIA_API_KEY=...      # optional, for the vision fallback
./rebuild_all.sh
```

Built with Python 3, PyMuPDF, Tesseract OCR, and the Gemini and NVIDIA vision APIs (with concurrent requests).
