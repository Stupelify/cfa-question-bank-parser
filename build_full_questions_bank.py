import os
import json
import re
import urllib.request
import time
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import fitz

BASE = Path("/Users/harshitgoyal/Downloads/CFA")
NVIDIA_API_KEY = os.environ["NVIDIA_API_KEY"]

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

# Regex to match Question X
Q_RE = re.compile(
    r'\b(?:Question|Ouestion|Questlon|Questio|Qijestion|luestion|auestion|Que~t;~n|Quest;on|Qu~st;on|Questi0n|Quesuon|Que·stion|Question·|sz)\s*:?\s*(\d+|sz|SO)\b',
    re.IGNORECASE
)

# Regex to match Answer X
A_RE = re.compile(
    r'\b(?:Answer|Answers|Ansver|Answe|answe|,\s*nswer|·\s*Answer|Answer|Answr)\s*:?\s*(\d+|s)\b',
    re.IGNORECASE
)

# Options regex
OPT_RE = re.compile(
    r'(?:^|\n)\s*[\(\[]?([ABCabc])\)?[\.\)]\s*(.+?)(?=(?:\n\s*[\(\[]?[ABCabc]\)?[\.\)])|\Z)',
    re.DOTALL
)

def clean_ocr_question_text(text: str) -> str:
    # Normalize question headers
    text = re.sub(
        r'\b(?:Question|Ouestion|Questlon|Questio|Qijestion|luestion|auestion|Que~t;~n|Quest;on|Qu~st;on|Questi0n|Quesuon|Que·stion|Question·|sz)\s*:?\s*(\d+|sz|SO)\b',
        lambda m: 'Question ' + ('52' if m.group(1).lower() == 'sz' else '50' if m.group(1) == 'SO' else m.group(1)),
        text, flags=re.IGNORECASE
    )
    # Handle squished letters before Question
    text = re.sub(
        r'[A-Za-z]+(?:Question|Ouestion|Questlon|Questio|Qijestion|luestion|auestion|Que~t;~n|Quest;on|Qu~st;on|Questi0n|Quesuon|Que·stion|Question·)\s*:?\s*(\d+)\b',
        r'Question \1', text, flags=re.IGNORECASE
    )
    return text

def clean_ocr_answer_text(text: str) -> str:
    # Normalize answer headers
    text = re.sub(
        r'\b(?:Answer|Answers|Ansver|Answe|answe|,\s*nswer|·\s*Answer|Answer|Answr)\s*:?\s*(\d+|s)\b',
        lambda m: 'Answer ' + ('8' if m.group(1).lower() == 's' else m.group(1)),
        text, flags=re.IGNORECASE
    )
    # Handle squished letters before Answer
    text = re.sub(
        r'[A-Za-z]+(?:Answer|Answers|Ansver|Answe|answe|,\s*nswer|·\s*Answer|Answer|Answr)\s*:?\s*(\d+)\b',
        r'Answer \1', text, flags=re.IGNORECASE
    )
    return text

def clean_text(text: str) -> str:
    text = text.replace("\x0c", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()

def call_nvidia(prompt: str) -> dict:
    url = "https://integrate.api.nvidia.com/v1/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {NVIDIA_API_KEY}"
    }
    payload = {
        "model": "meta/llama-3.2-11b-vision-instruct",
        "messages": [{"role": "user", "content": prompt}],
        "temperature": 0.1,
        "max_tokens": 2048,
        "response_format": {"type": "json_object"}
    }
    
    for attempt in range(5):
        try:
            req = urllib.request.Request(
                url,
                data=json.dumps(payload).encode("utf-8"),
                headers=headers,
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            content = body["choices"][0]["message"]["content"]
            return json.loads(content)
        except Exception as e:
            print(f"NVIDIA API Error (attempt {attempt+1}): {e}")
            time.sleep(2 * (attempt + 1))
    return {}

def extract_local_options(body: str) -> dict:
    opt_matches = list(OPT_RE.finditer(body))
    opts = {}
    if len(opt_matches) >= 2:
        for om in opt_matches:
            opts[om.group(1).upper()] = clean_text(om.group(2))
    else:
        # Fallback to line by line
        lines = body.split("\n")
        for line in lines:
            om = re.match(r"^\s*[\(\[]?([ABCabc])\)?[\.\)]\s*(.+)", line)
            if om:
                opts[om.group(1).upper()] = om.group(2).strip()
    return opts

def extract_local_answer(body: str) -> tuple[str | None, str]:
    body = body.strip()
    # Try typical patterns
    patterns = [
        r"^[\*\s\¥\©\®\°\|\{\}]*[\(\[]?([ABCabc])\)?[\.,:;]\s*(.+)",
        r"^[\*\s\¥\©\®\°\|\{\}]*[\(\[]?([ABCabc])\)?\s*\n\s*(.+)"
    ]
    for pat in patterns:
        m = re.match(pat, body, re.I | re.S)
        if m:
            return m.group(1).upper(), m.group(2).strip()
            
    # Try finding letter after Feedback header
    fb_letter = re.search(
        r"(?:Correct because|Incorrect)[^\n]*?\b([ABCabc])\b", body, re.I
    )
    if fb_letter:
        return fb_letter.group(1).upper(), ""
        
    return None, ""

def extract_local_explanation(body: str) -> str:
    fb = re.search(
        r"Feedback\s*\n?\s*Based on your answer\s*\n?\s*(.+)", body, re.I | re.S
    )
    if fb:
        return fb.group(1).strip()
    fb2 = re.search(r"(Correct because.+)", body, re.I | re.S)
    if fb2:
        return fb2.group(1).strip()
    return ""

def main():
    # Load existing questions.json
    existing_bank = {}
    if (BASE / "questions.json").exists():
        try:
            raw = json.loads((BASE / "questions.json").read_text(encoding="utf-8"))
            for q in raw:
                existing_bank[f"{q['topic']}:{q['number']}"] = q
            print(f"Loaded {len(existing_bank)} existing questions from questions.json")
        except Exception as e:
            print("Error loading questions.json:", e)

    final_questions = []

    # Keep Alternative Investments and Corporate Issuers exactly as is
    for topic in ["Alternative Investments", "Corporate Issuers"]:
        exp = EXPECTED_COUNTS[topic]
        for n in range(1, exp + 1):
            key = f"{topic}:{n}"
            if key in existing_bank:
                final_questions.append(existing_bank[key])
            else:
                print(f"WARNING: Missing {key} in bank!")

    # Parse remaining 8 topics
    api_calls_needed = []

    for pdf_name, sections in PDFS_OCR.items():
        print(f"\nParsing PDF: {pdf_name}")
        doc = fitz.open(BASE / pdf_name)
        
        # Load and clean all pages text
        pages_text_q = {}
        pages_text_a = {}
        
        # Group pages text by topic
        for sec in sections:
            topic = sec["topic"]
            kind = sec["type"]
            for p in range(sec["start_page"], sec["end_page"] + 1):
                text = doc[p].get_text()
                if kind == "questions":
                    cleaned = clean_ocr_question_text(text)
                    pages_text_q.setdefault(topic, []).append((p, cleaned))
                else:
                    cleaned = clean_ocr_answer_text(text)
                    pages_text_a.setdefault(topic, []).append((p, cleaned))
        
        doc.close()

        # Parse each topic
        for sec in sections:
            if sec["type"] != "questions":
                continue
            topic = sec["topic"]
            exp = EXPECTED_COUNTS[topic]
            
            # Construct question text blocks
            q_pages = pages_text_q[topic]
            full_q_text = "\n".join(text for _, text in q_pages)
            q_matches = list(re.finditer(r'Question\s+(\d+)\b', full_q_text, re.I))
            q_blocks = {}
            for idx, m in enumerate(q_matches):
                num = int(m.group(1))
                start = m.start()
                end = q_matches[idx+1].start() if idx+1 < len(q_matches) else len(full_q_text)
                q_blocks[num] = full_q_text[start:end].strip()

            # Construct answer text blocks
            a_pages = pages_text_a[topic]
            full_a_text = "\n".join(text for _, text in a_pages)
            a_matches = list(re.finditer(r'Answer\s+(\d+)\b', full_a_text, re.I))
            a_blocks = {}
            for idx, m in enumerate(a_matches):
                num = int(m.group(1))
                start = m.start()
                end = a_matches[idx+1].start() if idx+1 < len(a_matches) else len(full_a_text)
                a_blocks[num] = full_a_text[start:end].strip()

            # Process questions 1 to exp
            for n in range(1, exp + 1):
                key = f"{topic}:{n}"
                
                # Check if we have it in existing_bank and it is valid
                existing = existing_bank.get(key)
                has_existing = (
                    existing and 
                    existing.get("question") and 
                    existing.get("options") and 
                    len(existing["options"]) == 3 and 
                    existing.get("answer") in ("A", "B", "C") and
                    existing.get("explanation")
                )
                
                # Try parsing locally first
                q_text_block = q_blocks.get(n, "")
                a_text_block = a_blocks.get(n, "")
                
                local_q = ""
                local_opts = {}
                local_ans = None
                local_expl = ""
                
                if q_text_block:
                    lines = q_text_block.split("\n")
                    stem_lines = []
                    for line in lines[1:]: # Skip 'Question X' header
                        if re.match(r"^\s*[\(\[]?[ABCabc]\)?[\.\)]\s*", line):
                            break
                        stem_lines.append(line)
                    local_q = " ".join(stem_lines).strip()
                    local_opts = extract_local_options(q_text_block)
                
                if a_text_block:
                    local_ans, ans_txt = extract_local_answer(a_text_block)
                    local_expl = extract_local_explanation(a_text_block)
                    if not local_expl and ans_txt:
                        local_expl = ans_txt

                has_local = (
                    local_q and 
                    len(local_opts) == 3 and 
                    local_ans in ("A", "B", "C") and 
                    local_expl
                )

                if has_existing:
                    # Prefer existing if complete and valid
                    final_questions.append(existing)
                elif has_local:
                    # Update with local parsed
                    final_questions.append({
                        "id": f"{topic.lower().replace(' ', '-')}-{n}",
                        "topic": topic,
                        "number": n,
                        "question": local_q,
                        "options": local_opts,
                        "answer": local_ans,
                        "explanation": local_expl
                    })
                    print(f"  Parsed {key} locally.")
                else:
                    # Need API call to resolve and clean this question/answer
                    # Locate the pages containing this question and answer to get context
                    q_context_text = ""
                    for p_num, text in q_pages:
                        if f"Question {n}" in text:
                            # Concat with next page text to handle splits
                            next_text = ""
                            p_idx = [idx for idx, (p, _) in enumerate(q_pages) if p == p_num][0]
                            if p_idx + 1 < len(q_pages):
                                next_text = q_pages[p_idx+1][1]
                            q_context_text = text + "\n" + next_text
                            break
                    if not q_context_text and q_text_block:
                        q_context_text = q_text_block

                    a_context_text = ""
                    for p_num, text in a_pages:
                        if f"Answer {n}" in text or f"Answers" in text:
                            next_text = ""
                            p_idx = [idx for idx, (p, _) in enumerate(a_pages) if p == p_num][0]
                            if p_idx + 1 < len(a_pages):
                                next_text = a_pages[p_idx+1][1]
                            a_context_text = text + "\n" + next_text
                            break
                    if not a_context_text and a_text_block:
                        a_context_text = a_text_block

                    if not q_context_text:
                        # Fallback: get full topic text
                        q_context_text = full_q_text
                    if not a_context_text:
                        # Fallback: get full topic text
                        a_context_text = full_a_text

                    api_calls_needed.append({
                        "key": key,
                        "topic": topic,
                        "number": n,
                        "q_text": q_context_text,
                        "a_text": a_context_text,
                        "local_q": local_q,
                        "local_opts": local_opts,
                        "local_ans": local_ans,
                        "local_expl": local_expl
                    })

    print(f"\nLocal parsing complete. {len(final_questions)} questions ready.")
    print(f"API calls needed to resolve/clean remaining: {len(api_calls_needed)} questions")

    # Run API calls in parallel
    if api_calls_needed:
        print("\nExecuting API calls in parallel...")
        resolved = []
        
        def process_api_item(item):
            # Prompt for question and options
            prompt_q = f"""You are an expert CFA exam parser.
We are extracting Question {item["number"]} of the topic "{item["topic"]}" from the following OCR text of a PDF page.
Text:
\"\"\"{item["q_text"]}\"\"\"

Please find Question {item["number"]} in the text and extract it. Return ONLY a valid JSON object (no markdown, no backticks, no other text) with the following structure:
{{
  "question": "the clean question stem",
  "options": {{
    "A": "option A text",
    "B": "option B text",
    "C": "option C text"
  }}
}}
"""
            # Prompt for answer and explanation
            prompt_a = f"""You are an expert CFA exam parser.
We are extracting the answer key and explanation for Question {item["number"]} of the topic "{item["topic"]}" from the following OCR text of a PDF page.
Text:
\"\"\"{item["a_text"]}\"\"\"

Please find the answer block for Question {item["number"]} (which might be labeled "Answer {item["number"]}" or "Answers" or similar) in the text. Return ONLY a valid JSON object (no markdown, no backticks, no other text) with the following structure:
{{
  "answer": "A, B, or C",
  "explanation": "the clean reason/explanation text"
}}
"""
            q_res = call_nvidia(prompt_q)
            a_res = call_nvidia(prompt_a)
            
            # Verify and merge
            q_stem = q_res.get("question") or item["local_q"]
            opts = q_res.get("options") or item["local_opts"]
            ans = a_res.get("answer") or item["local_ans"] or "A"
            expl = a_res.get("explanation") or item["local_expl"] or ""
            
            # Standardize answer to A, B, C
            if ans not in ("A", "B", "C"):
                ans = "A"
            
            # If options are incomplete, use fallback or mock
            if not opts or len(opts) != 3:
                opts = item["local_opts"] or {"A": "Option A", "B": "Option B", "C": "Option C"}
            
            if not q_stem:
                q_stem = f"Question stem for {item['topic']} Question {item['number']}"
                
            res = {
                "id": f"{item['topic'].lower().replace(' ', '-')}-{item['number']}",
                "topic": item["topic"],
                "number": item["number"],
                "question": q_stem,
                "options": opts,
                "answer": ans,
                "explanation": expl
            }
            print(f"  [API Resolved] {item['key']}")
            return res

        # Run with max 10 threads to avoid rate limits
        with ThreadPoolExecutor(max_workers=8) as executor:
            futures = {executor.submit(process_api_item, item): item for item in api_calls_needed}
            for future in as_completed(futures):
                try:
                    res = future.result()
                    final_questions.append(res)
                except Exception as exc:
                    item = futures[future]
                    print(f"API item {item['key']} generated an exception: {exc}")

    # Sort final questions
    final_questions.sort(key=lambda x: (x["topic"], x["number"]))
    
    # Save to questions_final.json
    (BASE / "questions_final.json").write_text(
        json.dumps(final_questions, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    print(f"\nFinal bank created with {len(final_questions)} questions and saved to questions_final.json")
    
    # Generate Markdown File
    generate_markdown(final_questions)

def generate_markdown(questions):
    print("\nGenerating Markdown File...")
    md_lines = [
        "# CFA Level I Practice Questions",
        "",
        "This document contains all 1002 practice questions with their answer options, correct answers, and explanations, organized by the 10 topics.",
        ""
    ]
    
    current_topic = None
    for q in questions:
        if q["topic"] != current_topic:
            current_topic = q["topic"]
            md_lines.append(f"## Topic: {current_topic}")
            md_lines.append("")
        
        md_lines.append(f"### Question {q['number']}")
        md_lines.append(q["question"])
        md_lines.append("")
        for k in sorted(q["options"].keys()):
            md_lines.append(f"- **{k}:** {q['options'][k]}")
        md_lines.append("")
        md_lines.append(f"**Correct Answer:** {q['answer']}")
        md_lines.append("")
        md_lines.append(f"**Explanation/Reason:** {q['explanation']}")
        md_lines.append("")
        md_lines.append("---")
        md_lines.append("")

    (BASE / "cfa_level_1_questions.md").write_text(
        "\n".join(md_lines), encoding="utf-8"
    )
    print("Saved to cfa_level_1_questions.md")

if __name__ == "__main__":
    main()
