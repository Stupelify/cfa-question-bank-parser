#!/usr/bin/env python3
"""Merge 70 Alternative Investments questions from premium pack paste into questions.json."""

import json
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path

BASE = Path(__file__).parent
BANK = BASE / "questions.json"
TRANSCRIPT = Path(
    "/Users/harshitgoyal/.cursor/projects/Users-harshitgoyal-Downloads-CFA/"
    "agent-transcripts/dcb8afb4-1418-4298-b73d-5b6971fbd58a/"
    "dcb8afb4-1418-4298-b73d-5b6971fbd58a.jsonl"
)

TOPIC = "Alternative Investments"
Q8_STEM = "Alternative investments:"


def load_ai_section() -> str:
    with open(TRANSCRIPT, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("role") != "user":
                continue
            text = obj["message"]["content"][0]["text"]
            if "CFA Practice Pack Questions" in text and "Question 1" in text:
                start = text.find("## Alternative Investments Questions and Answers")
                end = text.find("## Corporate Issuers Questions and Answers")
                if end == -1:
                    end = text.find("</user_query>", start)
                if start == -1:
                    raise SystemExit("Could not locate Alternative Investments section in transcript")
                if end == -1:
                    end = len(text)
                section = text[start:end]
                return re.sub(r"\[ppl-ai-file-upload[^\]]*\]\([^\)]+\)", "", section)
    raise SystemExit("Transcript with AI questions not found")


def parse_questions(section: str) -> list[dict]:
    pattern = re.compile(
        r"Question\s+(\d+)\s*\n(.*?)(?=\nQuestion\s+\d+\s*\n|\Z)",
        re.DOTALL,
    )
    out = []
    for num_str, body in pattern.findall(section):
        num = int(num_str)
        lines = [l.strip() for l in body.strip().split("\n") if l.strip()]
        options: dict[str, str] = {}
        question_lines: list[str] = []
        answer = None
        explanation = ""
        phase = "question"

        for line in lines:
            if re.match(r"^[ABC]\.\s", line):
                phase = "options"
                options[line[0]] = line[3:].strip()
            elif line.startswith("Answer:"):
                phase = "answer"
                m = re.match(r"Answer:\s*([ABC])\.\s*(.*)", line)
                if m:
                    answer = m.group(1)
            elif line.startswith("Reason:"):
                phase = "explanation"
                explanation = line[7:].strip()
            elif phase == "explanation":
                explanation += " " + line
            elif phase == "question":
                question_lines.append(line)

        question = " ".join(question_lines).strip()
        if num == 8 and not question:
            question = Q8_STEM

        if answer not in ("A", "B", "C"):
            raise SystemExit(f"Q{num}: invalid answer {answer!r}")
        if len(options) != 3:
            raise SystemExit(f"Q{num}: expected 3 options, got {list(options)}")

        out.append(
            {
                "id": f"alternative-investments-{num}",
                "topic": TOPIC,
                "number": num,
                "question": question,
                "options": options,
                "answer": answer,
                "explanation": explanation.strip(),
            }
        )

    out.sort(key=lambda q: q["number"])
    if len(out) != 70:
        raise SystemExit(f"Expected 70 questions, parsed {len(out)}")
    return out


def main():
    ai_questions = parse_questions(load_ai_section())
    bank = json.loads(BANK.read_text(encoding="utf-8")) if BANK.exists() else []

    before_ai = sum(1 for q in bank if q["topic"] == TOPIC)
    other = [q for q in bank if q["topic"] != TOPIC]
    by_id = {q["id"]: q for q in other}

    added = updated = 0
    for q in ai_questions:
        if q["id"] in by_id:
            updated += 1
        else:
            added += 1
        by_id[q["id"]] = q

    merged = sorted(by_id.values(), key=lambda x: (x["topic"], x["number"]))
    BANK.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    after_ai = sum(1 for q in merged if q["topic"] == TOPIC)
    counts = Counter(q["topic"] for q in merged)

    print(f"Alternative Investments: {before_ai} -> {after_ai} (+{added} new, ~{updated} updated)")
    print(f"Total bank: {len(merged)} questions")
    print("By topic:")
    for topic, n in sorted(counts.items()):
        print(f"  {topic}: {n}")

    q8 = next(q for q in ai_questions if q["number"] == 8)
    if not q8["question"] or q8["question"] == Q8_STEM:
        print("NOTE: Q8 stem was missing in paste; recovered as 'Alternative investments:'")

    subprocess.run([sys.executable, str(BASE / "build_html.py")], check=True)
    print("Rebuilt index.html")


if __name__ == "__main__":
    main()
