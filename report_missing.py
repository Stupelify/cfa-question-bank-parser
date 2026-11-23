#!/usr/bin/env python3
"""Report missing questions and generate a manual entry template."""

import json
from collections import Counter, defaultdict
from pathlib import Path

from extract_questions import (
    MANUAL_SECTIONS,
    PDFS,
    merge_qa,
    ocr_page,
    parse_answers,
    parse_questions,
)
from question_cleaner import is_embeddable

BASE = Path(__file__).parent
EXPECTED = {
    "Portfolio Management": 100,
    "Quantitative Methods": 78,
    "Fixed Income": 112,
    "Financial Statement Analysis": 126,
    "Equity": 140,
    "Ethics": 150,
    "Alternative Investments": 70,
    "Corporate Issuers": 77,
    "Derivatives": 75,
    "Economics": 74,
}


def load_bank() -> dict[str, dict]:
    bank = {}
    if (BASE / "questions.json").exists():
        for q in json.loads((BASE / "questions.json").read_text(encoding="utf-8")):
            bank[f"{q['topic']}:{q['number']}"] = q
    return bank


def scan_topic(pdf_name: str, topic: str) -> dict:
    sections = MANUAL_SECTIONS[pdf_name]
    path = BASE / pdf_name
    qsec = next(s for s in sections if s["topic"] == topic and s["type"] == "questions")
    asec = next(s for s in sections if s["topic"] == topic and s["type"] == "answers")

    qtext = "\n".join(ocr_page(path, p) for p in range(qsec["start_page"], qsec["end_page"] + 1))
    atext = "\n".join(ocr_page(path, p) for p in range(asec["start_page"], asec["end_page"] + 1))

    qs = parse_questions(qtext, topic)
    ans = parse_answers(atext)
    merged = {q["number"]: q for q in merge_qa(qs, ans) if q.get("answer")}

    return {
        "parsed_questions": {q["number"] for q in qs},
        "parsed_answers": set(ans),
        "merged": merged,
        "question_pages": f"pp {qsec['start_page']+1}-{qsec['end_page']+1}",
        "answer_pages": f"pp {asec['start_page']+1}-{asec['end_page']+1}",
    }


def main():
    bank = load_bank()
    report = {
        "expected_total": sum(EXPECTED.values()),
        "in_bank": len(bank),
        "topics": {},
        "missing": [],
    }
    template = []

    for pdf_name, topics in PDFS:
        for topic in topics:
            data = scan_topic(pdf_name, topic)
            exp = EXPECTED[topic]
            in_bank = sum(1 for k in bank if k.startswith(topic + ":"))
            missing_nums = []

            for n in range(1, exp + 1):
                key = f"{topic}:{n}"
                if key in bank:
                    continue
                if n not in data["parsed_questions"]:
                    reason = "question_not_parsed"
                elif n not in data["parsed_answers"]:
                    reason = "answer_not_parsed"
                elif n not in data["merged"] or not is_embeddable(data["merged"].get(n, {})):
                    reason = "failed_quality_check"
                else:
                    reason = "unknown"

                entry = {
                    "topic": topic,
                    "number": n,
                    "reason": reason,
                    "pdf": pdf_name,
                    "question_pages": data["question_pages"],
                    "answer_pages": data["answer_pages"],
                }
                report["missing"].append(entry)
                missing_nums.append(n)

                template.append(
                    {
                        "id": f"{topic.lower().replace(' ', '-')}-{n}",
                        "topic": topic,
                        "number": n,
                        "question": "PASTE QUESTION TEXT HERE",
                        "options": {"A": "", "B": "", "C": ""},
                        "answer": "A",
                        "explanation": "optional",
                        "_reason": reason,
                    }
                )

            report["topics"][topic] = {
                "expected": exp,
                "in_bank": in_bank,
                "parsed_questions": len(data["parsed_questions"]),
                "parsed_answers": len(data["parsed_answers"]),
                "missing_count": len(missing_nums),
                "missing_numbers": missing_nums,
                "pdf": pdf_name,
            }

    report["missing_count"] = len(report["missing"])
    report["missing_by_reason"] = dict(Counter(m["reason"] for m in report["missing"]))

    (BASE / "missing_report.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (BASE / "manual_questions.template.json").write_text(
        json.dumps(template, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"In bank: {report['in_bank']} / {report['expected_total']}")
    print(f"Missing: {report['missing_count']}")
    print("By reason:", report["missing_by_reason"])
    print("\nPer topic:")
    for t, info in sorted(report["topics"].items()):
        print(
            f"  {t}: {info['in_bank']}/{info['expected']} "
            f"(missing {info['missing_count']})"
        )
    print("\nWrote missing_report.json and manual_questions.template.json")


if __name__ == "__main__":
    main()
