import json
import re
from pathlib import Path
import fitz

BASE = Path("/Users/harshitgoyal/Downloads/CFA")
PDFS_OCR = {
    "PM&Quants premium pack-ocr.pdf": [
        {"topic": "Portfolio Management", "type": "questions", "start_page": 3, "end_page": 25},
        {"topic": "Portfolio Management", "type": "answers", "start_page": 26, "end_page": 52},
        {"topic": "Quantitative Methods", "type": "questions", "start_page": 53, "end_page": 72},
        {"topic": "Quantitative Methods", "type": "answers", "start_page": 73, "end_page": 93},
    ],
    "Derivatives&Economics premium pack-1-ocr.pdf": [
        {"topic": "Derivatives", "type": "questions", "start_page": 3, "end_page": 18},
        {"topic": "Derivatives", "type": "answers", "start_page": 19, "end_page": 36},
        {"topic": "Economics", "type": "questions", "start_page": 37, "end_page": 50},
        {"topic": "Economics", "type": "answers", "start_page": 51, "end_page": 67},
    ],
    "Equity&Ethics premium pack-ocr.pdf": [
        {"topic": "Equity", "type": "questions", "start_page": 3, "end_page": 30},
        {"topic": "Equity", "type": "answers", "start_page": 31, "end_page": 63},
        {"topic": "Ethics", "type": "questions", "start_page": 64, "end_page": 105},
        {"topic": "Ethics", "type": "answers", "start_page": 106, "end_page": 155},
    ],
    "FSA and Fixed Income-ocr.pdf": [
        {"topic": "Fixed Income", "type": "questions", "start_page": 3, "end_page": 30},
        {"topic": "Fixed Income", "type": "answers", "start_page": 31, "end_page": 63},
        {"topic": "Financial Statement Analysis", "type": "questions", "start_page": 64, "end_page": 101},
        {"topic": "Financial Statement Analysis", "type": "answers", "start_page": 102, "end_page": 139},
    ],
}

# Import functions from extract_questions.py by copying/modifying them to run here
from extract_questions import parse_questions, parse_answers, merge_qa, EXPECTED_COUNTS

def test_parsing():
    all_parsed = {}
    for pdf_name, sections in PDFS_OCR.items():
        print(f"\nProcessing {pdf_name}...")
        doc = fitz.open(BASE / pdf_name)
        
        pdf_qs = {}
        pdf_ans = {}
        
        for sec in sections:
            topic = sec["topic"]
            pages_text = []
            for p in range(sec["start_page"], sec["end_page"] + 1):
                pages_text.append(doc[p].get_text())
            text = "\n".join(pages_text)
            
            if sec["type"] == "questions":
                qs = parse_questions(text, topic)
                pdf_qs[topic] = qs
                print(f"  {topic} questions: parsed {len(qs)}")
            else:
                ans = parse_answers(text)
                pdf_ans[topic] = ans
                print(f"  {topic} answers: parsed {len(ans)}")
        
        for topic in pdf_qs:
            qs = pdf_qs[topic]
            ans = pdf_ans.get(topic, {})
            merged = merge_qa(qs, ans)
            all_parsed[topic] = merged
            
            # Check how many have answer
            with_ans = [q for q in merged if q.get("answer")]
            exp = EXPECTED_COUNTS.get(topic, 0)
            print(f"  {topic}: {len(with_ans)} with answer / {len(merged)} total parsed / {len(ans)} answers parsed (expected {exp})")
            
        doc.close()

if __name__ == "__main__":
    test_parsing()
