#!/usr/bin/env python3
"""Extract CFA MCQ questions and answers from scanned PDFs via OCR."""

import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # pymupdf

from question_cleaner import clean_explanation, clean_option, clean_question, is_embeddable

BASE = Path(__file__).parent
CACHE_DIR = BASE / "ocr_cache"
CACHE_DIR.mkdir(exist_ok=True)

EXPECTED_COUNTS = {
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
PDFS = [
    ("AI&CI premium pack.pdf", ["Alternative Investments", "Corporate Issuers"]),
    ("Derivatives&Economics premium pack-1.pdf", ["Derivatives", "Economics"]),
    ("Equity&Ethics premium pack.pdf", ["Equity", "Ethics"]),
    ("FSA and Fixed Income.pdf", ["Financial Statement Analysis", "Fixed Income"]),
    ("PM&Quants premium pack.pdf", ["Portfolio Management", "Quantitative Methods"]),
]

TOPIC_PATTERNS = [
    (r"ethical and professional standards", "Ethics"),
    (r"equity investments?", "Equity"),
    (r"\bfsa\b", "Financial Statement Analysis"),
    (r"financial statement analysis", "Financial Statement Analysis"),
    (r"portfolio management", "Portfolio Management"),
    (r"quantitative methods?", "Quantitative Methods"),
    (r"alternative investments?", "Alternative Investments"),
    (r"corporate issuers?", "Corporate Issuers"),
    (r"derivatives", "Derivatives"),
    (r"economics", "Economics"),
    (r"fixed income", "Fixed Income"),
]

# 0-indexed page ranges from header OCR scan
MANUAL_SECTIONS: dict[str, list[dict]] = {
    "PM&Quants premium pack.pdf": [
        {"topic": "Portfolio Management", "type": "questions", "start_page": 3, "end_page": 25},
        {"topic": "Portfolio Management", "type": "answers", "start_page": 26, "end_page": 52},
        {"topic": "Quantitative Methods", "type": "questions", "start_page": 53, "end_page": 72},
        {"topic": "Quantitative Methods", "type": "answers", "start_page": 73, "end_page": 93},
    ],
    "AI&CI premium pack.pdf": [
        {"topic": "Alternative Investments", "type": "questions", "start_page": 3, "end_page": 16},
        {"topic": "Alternative Investments", "type": "answers", "start_page": 17, "end_page": 37},
        {"topic": "Corporate Issuers", "type": "questions", "start_page": 38, "end_page": 54},
        {"topic": "Corporate Issuers", "type": "answers", "start_page": 55, "end_page": 73},
    ],
    "Derivatives&Economics premium pack-1.pdf": [
        {"topic": "Derivatives", "type": "questions", "start_page": 3, "end_page": 18},
        {"topic": "Derivatives", "type": "answers", "start_page": 19, "end_page": 36},
        {"topic": "Economics", "type": "questions", "start_page": 37, "end_page": 50},
        {"topic": "Economics", "type": "answers", "start_page": 51, "end_page": 67},
    ],
    "Equity&Ethics premium pack.pdf": [
        {"topic": "Equity", "type": "questions", "start_page": 3, "end_page": 30},
        {"topic": "Equity", "type": "answers", "start_page": 31, "end_page": 63},
        {"topic": "Ethics", "type": "questions", "start_page": 64, "end_page": 105},
        {"topic": "Ethics", "type": "answers", "start_page": 106, "end_page": 155},
    ],
    "FSA and Fixed Income.pdf": [
        {"topic": "Fixed Income", "type": "questions", "start_page": 3, "end_page": 30},
        {"topic": "Fixed Income", "type": "answers", "start_page": 31, "end_page": 63},
        {"topic": "Financial Statement Analysis", "type": "questions", "start_page": 64, "end_page": 101},
        {"topic": "Financial Statement Analysis", "type": "answers", "start_page": 102, "end_page": 139},
    ],
}


def ocr_page(pdf_path: Path, page_num: int, dpi: int = 200) -> str:
    cache_key = f"{pdf_path.name}__p{page_num}__dpi{dpi}.txt"
    cache_file = CACHE_DIR / cache_key
    if cache_file.exists():
        return cache_file.read_text(encoding="utf-8")

    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        pix.save(str(tmp_path))
        result = subprocess.run(
            ["tesseract", str(tmp_path), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            check=False,
        )
        text = result.stdout or ""
    finally:
        tmp_path.unlink(missing_ok=True)
        doc.close()

    cache_file.write_text(text, encoding="utf-8")
    return text


def ocr_header(pdf_path: Path, page_num: int) -> str:
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    rect = page.rect
    clip = fitz.Rect(rect.width * 0.30, 0, rect.width, rect.height * 0.14)
    mat = fitz.Matrix(2.5, 2.5)
    pix = page.get_pixmap(matrix=mat, clip=clip, alpha=False)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        pix.save(str(tmp_path))
        result = subprocess.run(
            ["tesseract", str(tmp_path), "stdout", "--psm", "6"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.stdout or ""
    finally:
        tmp_path.unlink(missing_ok=True)
        doc.close()


def classify_page(header: str) -> tuple[str | None, str | None]:
    h = header.lower()
    topic = None
    for pat, name in TOPIC_PATTERNS:
        if re.search(pat, h):
            topic = name
            break
    if not topic:
        return None, None
    if "answer" in h or "answe" in h:
        return topic, "answers"
    if "question" in h or "questi" in h:
        return topic, "questions"
    return topic, None


def detect_sections(pdf_path: Path) -> list[dict]:
    name = pdf_path.name
    if name in MANUAL_SECTIONS:
        sections = MANUAL_SECTIONS[name]
        print(f"  Using manual sections ({len(sections)}):", file=sys.stderr)
        for s in sections:
            print(
                f"    {s['topic']} {s['type']}: pp {s['start_page']+1}-{s['end_page']+1}",
                file=sys.stderr,
            )
        return sections

    doc = fitz.open(pdf_path)
    n_pages = len(doc)
    doc.close()

    labels: list[tuple[int, str, str]] = []
    for i in range(n_pages):
        header = ocr_header(pdf_path, i)
        topic, kind = classify_page(header)
        if topic and kind:
            labels.append((i, topic, kind))
        if (i + 1) % 30 == 0:
            print(f"  header scan {i + 1}/{n_pages}", file=sys.stderr)

    if not labels:
        return []

    sections = []
    for idx, (page, topic, kind) in enumerate(labels):
        end = (labels[idx + 1][0] - 1) if idx + 1 < len(labels) else n_pages - 1
        # Skip pure divider pages (title only): if next label is same topic+kind or very short span
        start = page
        sections.append({"topic": topic, "type": kind, "start_page": start, "end_page": end})

    # Merge consecutive same topic+type (OCR noise)
    merged = []
    for sec in sections:
        if merged and merged[-1]["topic"] == sec["topic"] and merged[-1]["type"] == sec["type"]:
            merged[-1]["end_page"] = sec["end_page"]
        else:
            merged.append(sec)

    print(f"  Sections ({len(merged)}):", file=sys.stderr)
    for s in merged:
        print(
            f"    {s['topic']} {s['type']}: pp {s['start_page']+1}-{s['end_page']+1}",
            file=sys.stderr,
        )
    return merged


def clean_text(text: str) -> str:
    text = text.replace("\x0c", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


Q_SPLIT = re.compile(r"(?=(?:Question|Ouestion|Questlon|Questio)\s*:?\s*\d+\b)", re.I)
Q_HEAD = re.compile(r"(?:Question|Ouestion|Questlon|Questio)\s*:?\s*(\d+)\s*(.*)", re.I | re.S)
A_SPLIT = re.compile(r"(?=(?:Answer|Ansver|Answe)\s*:?\s*\d+\b)", re.I)
A_HEAD = re.compile(r"(?:Answer|Ansver|Answe)\s*:?\s*(\d+)\s*(.*)", re.I | re.S)
OPT_RE = re.compile(r"(?:^|\n)\s*[\(\[]?([ABCabc])\)?[\.\)]\s*(.+?)(?=(?:\n\s*[\(\[]?[ABCabc]\)?[\.\)])|\Z)", re.S)


def parse_questions(text: str, topic: str) -> list[dict]:
    questions = []
    parts = Q_SPLIT.split(text)
    for part in parts:
        m = Q_HEAD.match(part)
        if not m:
            continue
        qnum = int(m.group(1))
        body = m.group(2).strip()

        opt_matches = list(OPT_RE.finditer(body))
        opts = {}
        if len(opt_matches) >= 2:
            qtext = body[: opt_matches[0].start()].strip()
            for om in opt_matches:
                opts[om.group(1).upper()] = clean_text(om.group(2))
        else:
            lines = body.split("\n")
            qtext_lines = []
            for line in lines:
                om = re.match(r"^\s*[\(\[]?([ABCabc])\)?[\.\)]\s*(.+)", line)
                if om:
                    opts[om.group(1).upper()] = om.group(2).strip()
                elif not opts:
                    qtext_lines.append(line.strip())
            qtext = " ".join(qtext_lines).strip()

        qtext = clean_question(clean_text(qtext))
        opts = {k: clean_option(v) for k, v in opts.items()}
        if not qtext or len(opts) < 2:
            continue

        questions.append(
            {
                "id": f"{topic.lower().replace(' ', '-')}-{qnum}",
                "topic": topic,
                "number": qnum,
                "question": qtext,
                "options": opts,
                "answer": None,
                "explanation": None,
            }
        )
    return questions


def extract_answer_letter(body: str) -> tuple[str | None, str]:
    body = body.strip()
    patterns = [
        r"^[\*\s\¥\©\®\°\|\{\}]*[\(\[]?([ABCabc])\)?[\.,:;]\s*(.+)",
        r"^[\*\s\¥\©\®\°\|\{\}]*[\(\[]?([ABCabc])\)?\s*\n\s*(.+)",
        r"^[\*\s\¥\©\®\°\|\{\}€]*[\.,:;]\s*(.+)",  # OCR lost letter, e.g. "€. abnormal"
    ]
    for i, pat in enumerate(patterns):
        m = re.match(pat, body, re.I | re.S)
        if not m:
            continue
        if i < 2:
            return m.group(1).upper(), m.group(2).strip()
        # No letter captured — try infer from explanation or skip
        return None, m.group(1).strip()
    return None, ""


def parse_answers(text: str) -> dict[int, dict]:
    answers = {}
    parts = A_SPLIT.split(text)
    for part in parts:
        m = A_HEAD.match(part)
        if not m:
            continue
        anum = int(m.group(1))
        body = m.group(2).strip()

        letter, ans_text = extract_answer_letter(body)
        if not letter:
            # Try finding letter after Feedback header
            fb_letter = re.search(
                r"(?:Correct because|Incorrect)[^\n]*?\b([ABCabc])\b", body, re.I
            )
            if fb_letter:
                letter = fb_letter.group(1).upper()
            else:
                # Common OCR: €. or C,
                cm = re.match(r"^[€Cc][\.,]\s*(.+)", body, re.I | re.S)
                if cm:
                    letter = "C"
                    ans_text = cm.group(1).strip()
                else:
                    continue

        if not ans_text:
            ans_m = re.match(
                r"[\(\[]?([ABCabc])\)?[\.,]\s*(.+?)(?=\n\s*Feedback|\n\s*Based on|\Z)",
                body,
                re.I | re.S,
            )
            if ans_m:
                letter = ans_m.group(1).upper()
                ans_text = ans_m.group(2).strip()

        expl = ""
        fb = re.search(
            r"Feedback\s*\n?\s*Based on your answer\s*\n?\s*(.+)", body, re.I | re.S
        )
        if fb:
            expl = fb.group(1).strip()
        else:
            fb2 = re.search(r"(Correct because.+)", body, re.I | re.S)
            if fb2:
                expl = fb2.group(1).strip()

        answers[anum] = {
            "answer": letter,
            "answerText": clean_option(ans_text.split("\n")[0] if ans_text else ""),
            "explanation": clean_explanation(expl),
        }
    return answers


def merge_qa(questions: list[dict], answers: dict[int, dict]) -> list[dict]:
    for q in questions:
        a = answers.get(q["number"])
        if a:
            q["answer"] = a["answer"]
            q["explanation"] = a["explanation"] or a.get("answerText", "")
    return questions


def extract_pdf(pdf_name: str, expected_topics: list[str]) -> list[dict]:
    pdf_path = BASE / pdf_name
    print(f"\n=== {pdf_name} ===", file=sys.stderr)

    sections = detect_sections(pdf_path)
    if not sections:
        doc = fitz.open(pdf_path)
        n = len(doc)
        doc.close()
        q_end = n // 4
        a_end = n // 2
        q2_end = 3 * n // 4
        sections = [
            {"topic": expected_topics[0], "type": "questions", "start_page": 2, "end_page": q_end},
            {"topic": expected_topics[0], "type": "answers", "start_page": q_end + 1, "end_page": a_end},
            {"topic": expected_topics[1], "type": "questions", "start_page": a_end + 1, "end_page": q2_end},
            {"topic": expected_topics[1], "type": "answers", "start_page": q2_end + 1, "end_page": n - 1},
        ]
        print("  fallback section split", file=sys.stderr)

    all_questions: dict[str, list[dict]] = {}
    answer_bank: dict[str, dict[int, dict]] = {}

    for sec in sections:
        topic = sec["topic"]
        pages_text = []
        for p in range(sec["start_page"], sec["end_page"] + 1):
            print(f"  OCR {topic[:12]} {sec['type'][:1]} p{p+1}", file=sys.stderr)
            pages_text.append(ocr_page(pdf_path, p))
        text = "\n".join(pages_text)

        if sec["type"] == "questions":
            qs = parse_questions(text, topic)
            all_questions.setdefault(topic, []).extend(qs)
            print(f"  -> {len(qs)} questions", file=sys.stderr)
        else:
            ans = parse_answers(text)
            answer_bank.setdefault(topic, {}).update(ans)
            print(f"  -> {len(ans)} answers", file=sys.stderr)

    merged = []
    for topic in expected_topics:
        qs = all_questions.get(topic, [])
        ans = answer_bank.get(topic, {})
        topic_qs = merge_qa(qs, ans)
        with_ans = [q for q in topic_qs if q.get("answer") and is_embeddable(q)]
        exp = EXPECTED_COUNTS.get(topic, "?")
        print(
            f"  {topic}: {len(with_ans)} usable / {len(topic_qs)} parsed / {len(ans)} answers / expected {exp}",
            file=sys.stderr,
        )
        merged.extend(with_ans)

    return merged


def main():
    all_q = []
    for pdf_name, topics in PDFS:
        try:
            all_q.extend(extract_pdf(pdf_name, topics))
        except Exception as e:
            import traceback
            print(f"ERROR {pdf_name}: {e}", file=sys.stderr)
            traceback.print_exc()

    seen = set()
    unique = []
    best: dict[str, dict] = {}
    for q in sorted(all_q, key=lambda x: (x["topic"], x["number"])):
        key = q["id"]
        if key in best:
            prev = best[key]
            if len(q.get("question", "")) > len(prev.get("question", "")):
                best[key] = q
        else:
            best[key] = q

    for q in best.values():
        if q["id"] not in seen:
            seen.add(q["id"])
            unique.append(q)
    unique.sort(key=lambda x: (x["topic"], x["number"]))

    out = BASE / "questions.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(unique, f, indent=2, ensure_ascii=False)

    print(f"\n=== TOTAL: {len(unique)} questions ===", file=sys.stderr)
    counts = {}
    for q in unique:
        counts[q["topic"]] = counts.get(q["topic"], 0) + 1
    for t, c in sorted(counts.items()):
        exp = EXPECTED_COUNTS.get(t, "?")
        gap = exp - c if isinstance(exp, int) else "?"
        print(f"  {t}: {c} (expected {exp}, gap {gap})", file=sys.stderr)


if __name__ == "__main__":
    main()
