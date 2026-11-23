#!/usr/bin/env python3
"""Merge 77 Corporate Issuers questions from premium pack paste into questions.json."""

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

TOPIC = "Corporate Issuers"
EXPECTED = 77
VERIFY = {1: "A", 23: "B", 77: "C"}


def load_ci_section() -> str:
    with open(TRANSCRIPT, encoding="utf-8") as f:
        for line in f:
            obj = json.loads(line)
            if obj.get("role") != "user":
                continue
            text = obj["message"]["content"][0]["text"]
            if "Corporate Issuers Answers and Explanations" in text and "### 1" in text:
                text = re.sub(r"\[ppl-ai-file-upload[^\]]*\]\([^\)]+\)", "", text)
                return text
    raise SystemExit("Could not locate Corporate Issuers section in transcript")


def clean_text(s: str) -> str:
    from question_cleaner import strip_premium_paste_artifacts

    s = strip_premium_paste_artifacts(s)
    s = re.sub(r"\[ppl-ai-file-upload[^\]]*\]\([^\)]+\)", "", s)
    s = re.sub(r"\[[^\]]+\]\([^\)]+\)", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip()


def parse_questions(section: str) -> list[dict]:
    pattern = re.compile(r"^### (\d+)\s*\n(.*?)(?=^### \d+\s*$|\Z)", re.MULTILINE | re.DOTALL)
    out = []
    failures: list[str] = []

    for num_str, body in pattern.findall(section):
        num = int(num_str)
        body = body.strip()

        q_match = re.search(r"\*\*Question:\*\*\s*(.*?)(?=\n\s*[ABC]\.\s|\Z)", body, re.DOTALL)
        if not q_match:
            failures.append(f"Q{num}: missing question stem")
            continue
        question = clean_text(q_match.group(1))

        options: dict[str, str] = {}
        for opt in re.finditer(r"^([ABC])\.\s*(.+?)\s*$", body, re.MULTILINE):
            if opt.group(1) not in options:
                options[opt.group(1)] = clean_text(opt.group(2))

        ans_match = re.search(r"\*\*Answer:\*\*\s*([ABC])\.\s*(.*)", body)
        if not ans_match:
            failures.append(f"Q{num}: missing answer")
            continue
        answer = ans_match.group(1)

        exp_match = re.search(r"\*\*Explanation:\*\*\s*(.*)", body, re.DOTALL)
        explanation = clean_text(exp_match.group(1)) if exp_match else ""

        if answer not in ("A", "B", "C"):
            failures.append(f"Q{num}: invalid answer {answer!r}")
            continue
        if len(options) != 3:
            failures.append(f"Q{num}: expected 3 options, got {list(options)}")
            continue

        out.append(
            {
                "id": f"corporate-issuers-{num}",
                "topic": TOPIC,
                "number": num,
                "question": question,
                "options": options,
                "answer": answer,
                "explanation": explanation,
            }
        )

    out.sort(key=lambda q: q["number"])
    nums = {q["number"] for q in out}
    missing = sorted(set(range(1, EXPECTED + 1)) - nums)
    if missing:
        failures.append(f"Missing question numbers: {missing}")

    if failures:
        for msg in failures:
            print(f"PARSE WARNING: {msg}", file=sys.stderr)

    if len(out) != EXPECTED:
        raise SystemExit(f"Expected {EXPECTED} questions, parsed {len(out)}")

    for num, expected in VERIFY.items():
        q = next(x for x in out if x["number"] == num)
        if q["answer"] != expected:
            raise SystemExit(f"Q{num}: expected answer {expected}, got {q['answer']}")

    return out


def main():
    ci_questions = parse_questions(load_ci_section())
    bank = json.loads(BANK.read_text(encoding="utf-8")) if BANK.exists() else []

    before_ci = sum(1 for q in bank if q["topic"] == TOPIC)
    other = [q for q in bank if q["topic"] != TOPIC]
    by_id = {q["id"]: q for q in other}

    added = updated = 0
    for q in ci_questions:
        if q["id"] in by_id:
            updated += 1
        else:
            added += 1
        by_id[q["id"]] = q

    merged = sorted(by_id.values(), key=lambda x: (x["topic"], x["number"]))
    BANK.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")

    after_ci = sum(1 for q in merged if q["topic"] == TOPIC)
    counts = Counter(q["topic"] for q in merged)

    print(f"Corporate Issuers: {before_ci} -> {after_ci} (+{added} new, ~{updated} updated)")
    print(f"Total bank: {len(merged)} questions")
    print("By topic:")
    for topic, n in sorted(counts.items()):
        print(f"  {topic}: {n}")

    print("Verification: Q1=A, Q23=B, Q77=C OK")

    subprocess.run([sys.executable, str(BASE / "build_html.py")], check=True)
    print("Rebuilt index.html")


if __name__ == "__main__":
    main()
