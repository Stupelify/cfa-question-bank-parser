#!/usr/bin/env python3
"""Merge manually entered questions into questions.json and rebuild index.html."""

import json
import subprocess
import sys
from pathlib import Path

BASE = Path(__file__).parent
MANUAL = BASE / "manual_questions.json"
BANK = BASE / "questions.json"


def main():
    if not MANUAL.exists():
        print("Create manual_questions.json first.")
        print("Copy manual_questions.template.json → manual_questions.json")
        print("Fill in only the questions you want to add, then run this script again.")
        sys.exit(1)

    bank = json.loads(BANK.read_text(encoding="utf-8")) if BANK.exists() else []
    by_id = {q["id"]: q for q in bank}

    manual = json.loads(MANUAL.read_text(encoding="utf-8"))
    added = updated = skipped = 0

    for q in manual:
        if q.get("question", "").startswith("PASTE"):
            skipped += 1
            continue
        if q.get("answer") not in ("A", "B", "C"):
            print(f"Skip {q.get('id')}: invalid answer")
            skipped += 1
            continue
        opts = q.get("options", {})
        if not all(opts.get(k) for k in ("A", "B", "C")):
            print(f"Skip {q.get('id')}: missing options")
            skipped += 1
            continue

        clean = {
            "id": q["id"],
            "topic": q["topic"],
            "number": q["number"],
            "question": q["question"].strip(),
            "options": {k: opts[k].strip() for k in ("A", "B", "C")},
            "answer": q["answer"],
            "explanation": q.get("explanation", "").strip(),
        }
        if clean["id"] in by_id:
            updated += 1
        else:
            added += 1
        by_id[clean["id"]] = clean

    merged = sorted(by_id.values(), key=lambda x: (x["topic"], x["number"]))
    BANK.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Bank: {len(merged)} questions (+{added} new, ~{updated} updated, {skipped} skipped)")

    subprocess.run([sys.executable, str(BASE / "build_html.py")], check=True)
    print("Rebuilt index.html")


if __name__ == "__main__":
    main()
