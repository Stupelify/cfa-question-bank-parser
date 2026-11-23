#!/usr/bin/env python3
"""Audit and auto-fix OCR issues in the CFA question bank."""

import json
from collections import Counter
from pathlib import Path

from question_cleaner import (
    clean_explanation,
    clean_option,
    clean_question,
    is_embeddable,
    question_issues,
)

BASE = Path(__file__).parent
DATA = BASE / "questions.json"


def main():
    # Re-load from backup if we have original - use current questions.json
    raw = json.loads(DATA.read_text(encoding="utf-8"))
    fixed = []
    audit = {"fixed": [], "removed": [], "warnings": []}

    for q in raw:
        q = dict(q)
        orig_q = q.get("question", "")
        orig_opts = dict(q.get("options", {}))

        q["question"] = clean_question(q.get("question", ""))
        q["options"] = {k: clean_option(v) for k, v in q.get("options", {}).items()}
        q["explanation"] = clean_explanation(q.get("explanation", ""))

        if q["question"] != orig_q or q["options"] != orig_opts:
            audit["fixed"].append({"id": q["id"], "topic": q["topic"], "number": q["number"]})

        issues = question_issues(q["question"])
        if issues:
            audit["warnings"].append(
                {
                    "id": q["id"],
                    "topic": q["topic"],
                    "number": q["number"],
                    "issues": issues,
                    "question": q["question"][:200],
                }
            )

        if is_embeddable(q):
            fixed.append(q)
        else:
            audit["removed"].append(
                {
                    "id": q.get("id"),
                    "topic": q.get("topic"),
                    "number": q.get("number"),
                    "issues": issues,
                    "question": q.get("question", "")[:200],
                }
            )

    DATA.write_text(json.dumps(fixed, indent=2, ensure_ascii=False), encoding="utf-8")
    (BASE / "audit_report.json").write_text(
        json.dumps(audit, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"Input:   {len(raw)}")
    print(f"Valid:   {len(fixed)}")
    print(f"Removed: {len(audit['removed'])}")
    print(f"Cleaned: {len(audit['fixed'])}")
    print(f"Warnings in valid set: {len(audit['warnings'])}")

    if audit["warnings"]:
        print("\nRemaining warnings:")
        for w in audit["warnings"][:30]:
            print(f"  [{w['topic']} #{w['number']}] {w['issues']}: {w['question'][:80]}...")

    if audit["removed"]:
        print(f"\nRemoved samples:")
        for r in audit["removed"][:15]:
            print(f"  [{r['topic']} #{r['number']}] {r['question'][:80]}...")

    by_topic = Counter(q["topic"] for q in fixed)
    print("\nPer topic:")
    for t, c in sorted(by_topic.items()):
        print(f"  {t}: {c}")


if __name__ == "__main__":
    main()
