#!/usr/bin/env python3
"""Embed questions.json into index.html template."""

import json
from pathlib import Path

from question_cleaner import clean_explanation, clean_option, clean_question, is_embeddable

BASE = Path(__file__).parent
questions_raw = json.loads((BASE / "questions.json").read_text(encoding="utf-8"))

questions = []
for q in questions_raw:
    q = dict(q)
    q["question"] = clean_question(q.get("question", ""))
    q["options"] = {k: clean_option(v) for k, v in q.get("options", {}).items()}
    q["explanation"] = clean_explanation(q.get("explanation", ""))
    if is_embeddable(q):
        questions.append(q)

print(f"Embedded {len(questions)} valid questions (from {len(questions_raw)} raw)")
template = (BASE / "index.template.html").read_text(encoding="utf-8")
payload = json.dumps(questions, ensure_ascii=False, separators=(",", ":"))
html = template.replace("/*__QUESTIONS_DATA__*/[]", payload)
(BASE / "index.html").write_text(html, encoding="utf-8")
print(f"Built index.html")
