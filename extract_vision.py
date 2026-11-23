#!/usr/bin/env python3
"""
Extract CFA questions by reading each PDF page as an image with a vision model.

Run:  .venv/bin/python3 extract_vision.py --list-providers
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import fitz

from extract_questions import EXPECTED_COUNTS, MANUAL_SECTIONS, PDFS
from question_cleaner import clean_explanation, clean_option, clean_question, is_embeddable
from vision_providers import (
    PROVIDER_PRESETS,
    available_providers,
    get_api_key,
    nvidia_model_chain,
    pick_provider,
    print_provider_guide,
    resolve_model,
    should_use_parallel,
)

BASE = Path(__file__).parent
IMG_DIR = BASE / "vision_pages"
CACHE_DIR = BASE / "vision_cache"


def load_dotenv() -> None:
    """Load KEY=value pairs from .env if present (never commit that file)."""
    env_path = BASE / ".env"
    if not env_path.exists():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        key, val = key.strip(), val.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = val


load_dotenv()

QUESTION_PROMPT = """You are extracting CFA exam practice questions from a scanned textbook page image.

Return ONLY valid JSON (no markdown) in this exact shape:
{
  "questions": [
    {
      "number": 1,
      "question": "full question text including any tables/data",
      "options": {"A": "...", "B": "...", "C": "..."}
    }
  ]
}

Rules:
- Extract EVERY question visible on the page (usually 4-6 per page).
- Preserve numbers, percentages, formulas, and table data exactly.
- Do not include page headers/footers or "Question X" label in question text.
- If no questions on this page (title/divider), return {"questions": []}.
"""

ANSWER_PROMPT = """You are extracting CFA exam answer keys from a scanned textbook page image.

Return ONLY valid JSON (no markdown) in this exact shape:
{
  "answers": [
    {
      "number": 1,
      "answer": "A",
      "explanation": "full feedback/explanation text after 'Correct because...'"
    }
  ]
}

Rules:
- Extract EVERY answer block visible (Answer 1, Answer 2, ...).
- "answer" must be exactly A, B, or C.
- Include the full explanation paragraph when present.
- Keep explanation text verbatim but do not repeat boilerplate like "Based on your answer".
- If no answers on this page, return {"answers": []}.
"""


def _unescape_json_str(s: str) -> str:
    return s.replace("\\n", "\n").replace('\\"', '"').replace("\\\\", "\\")


def _salvage_answer_objects(text: str) -> list[dict]:
    answers: list[dict] = []
    seen: set[int] = set()
    complete = re.compile(
        r'\{\s*"number"\s*:\s*(\d+)\s*,\s*"answer"\s*:\s*"([ABC])"\s*,'
        r'\s*"explanation"\s*:\s*"((?:[^"\\]|\\.)*)"\s*\}',
        re.DOTALL | re.IGNORECASE,
    )
    for m in complete.finditer(text):
        num = int(m.group(1))
        if num in seen:
            continue
        seen.add(num)
        answers.append(
            {
                "number": num,
                "answer": m.group(2).upper(),
                "explanation": _unescape_json_str(m.group(3)),
            }
        )

    partial = re.compile(
        r'\{\s*"number"\s*:\s*(\d+)\s*,\s*"answer"\s*:\s*"([ABC])"\s*,'
        r'\s*"explanation"\s*:\s*"(.*?)\Z',
        re.DOTALL | re.IGNORECASE,
    )
    m = partial.search(text)
    if m:
        num = int(m.group(1))
        if num not in seen:
            answers.append(
                {
                    "number": num,
                    "answer": m.group(2).upper(),
                    "explanation": _unescape_json_str(m.group(3).rstrip('",}\n ')),
                }
            )
    return sorted(answers, key=lambda x: x["number"])


def _salvage_question_objects(text: str) -> list[dict]:
    questions: list[dict] = []
    seen: set[int] = set()
    complete = re.compile(
        r'\{\s*"number"\s*:\s*(\d+)\s*,\s*"question"\s*:\s*"((?:[^"\\]|\\.)*)"\s*,'
        r'\s*"options"\s*:\s*(\{[^{}]*\})\s*\}',
        re.DOTALL | re.IGNORECASE,
    )
    for m in complete.finditer(text):
        num = int(m.group(1))
        if num in seen:
            continue
        try:
            opts = json.loads(m.group(3))
        except json.JSONDecodeError:
            continue
        seen.add(num)
        questions.append(
            {
                "number": num,
                "question": _unescape_json_str(m.group(2)),
                "options": opts,
            }
        )
    return sorted(questions, key=lambda x: x["number"])


def salvage_json(text: str) -> dict | list | None:
    """Recover partial JSON when the model hits max_tokens mid-response."""
    text = (text or "").strip()
    if not text:
        return None

    if '"answers"' in text or re.search(r'"answer"\s*:\s*"[ABC]"', text, re.I):
        items = _salvage_answer_objects(text)
        if items:
            return {"answers": items}

    if '"questions"' in text or re.search(r'"options"\s*:\s*\{', text):
        items = _salvage_question_objects(text)
        if items:
            return {"questions": items}

    start = text.find("{")
    if start < 0:
        start = text.find("[")
    if start < 0:
        return None
    fragment = text[start:]
    step = max(len(fragment) // 40, 20)
    for trim in range(len(fragment), max(len(fragment) // 4, 30), -step):
        chunk = fragment[:trim].rstrip().rstrip(",")
        for suffix in ('"}]}', '"]}', '"}', ']}', '}'):
            try:
                return json.loads(chunk + suffix)
            except json.JSONDecodeError:
                continue
    return None


def render_page(pdf_path: Path, page_num: int, dpi: int = 200) -> Path:
    IMG_DIR.mkdir(exist_ok=True)
    out = IMG_DIR / f"{pdf_path.stem}__p{page_num+1}.png"
    if out.exists() and out.stat().st_size > 10000:
        return out
    doc = fitz.open(pdf_path)
    page = doc[page_num]
    mat = fitz.Matrix(dpi / 72, dpi / 72)
    pix = page.get_pixmap(matrix=mat, alpha=False)
    pix.save(str(out))
    doc.close()
    return out


def cache_path(pdf_name: str, page_num: int, kind: str) -> Path:
    CACHE_DIR.mkdir(exist_ok=True)
    safe = re.sub(r"[^\w.-]", "_", pdf_name)
    return CACHE_DIR / f"{safe}__p{page_num+1}__{kind}.json"


def parse_json_response(text: str) -> dict | list:
    text = (text or "").strip()
    if not text:
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    for pattern in (
        r"```(?:json)?\s*(\{.*?\})\s*```",
        r"```(?:json)?\s*(\[.*?\])\s*```",
    ):
        m = re.search(pattern, text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(1))
            except json.JSONDecodeError:
                pass
    salvaged = salvage_json(text)
    if salvaged is not None:
        return salvaged
    raise json.JSONDecodeError("No JSON in response", text, 0)


def normalize_vision_payload(data: object, kind: str) -> dict:
    """Coerce model/cache JSON into {questions: [...]} or {answers: [...]}."""
    key = "questions" if kind == "questions" else "answers"
    if isinstance(data, list):
        return {key: data}
    if not isinstance(data, dict):
        return {key: []}
    if key in data and isinstance(data[key], list):
        return data
    if "number" in data:
        return {key: [data]}
    for alt in ("items", "data", "results"):
        if alt in data and isinstance(data[alt], list):
            return {key: data[alt]}
    return {key: []}


def call_openai_compatible(
    base_url: str,
    api_key: str,
    model_id: str,
    image_path: Path,
    prompt: str,
    extra_headers: dict | None = None,
    rpm_delay: float = 2.0,
    json_mode: bool = True,
    max_tokens: int = 4096,
) -> dict:
    import urllib.error
    import urllib.request

    b64 = base64.b64encode(image_path.read_bytes()).decode()
    url = f"{base_url.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    if extra_headers:
        headers.update(extra_headers)

    raw = "{}"
    tokens = max_tokens
    for attempt in range(4):
        payload = {
            "model": model_id,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"},
                        },
                    ],
                }
            ],
            "temperature": 0.1,
            "max_tokens": tokens,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=360 if tokens >= 8192 else 240) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            choice = body["choices"][0]
            raw = choice["message"]["content"] or "{}"
            finish = choice.get("finish_reason", "")
            try:
                parsed = parse_json_response(raw)
            except json.JSONDecodeError:
                salvaged = salvage_json(raw)
                if salvaged is None:
                    raise
                parsed = salvaged
                n = len(salvaged.get("answers") or salvaged.get("questions") or [])
                print(f"  salvaged {n} item(s) from truncated JSON", file=sys.stderr)
            if finish == "length" and attempt < 3:
                n = len(parsed.get("answers") or parsed.get("questions") or [])
                if n >= 3:
                    print(f"  truncated but got {n} items, accepting", file=sys.stderr)
                    return parsed
                tokens = min(tokens * 2, 16384)
                print(f"  output truncated, retry with max_tokens={tokens}...", file=sys.stderr)
                time.sleep(rpm_delay)
                continue
            return parsed
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                wait = rpm_delay * (attempt + 3)
                print(f"  rate limit, wait {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            if e.code in (403, 502, 503) or e.code >= 500:
                if attempt < 3:
                    wait = rpm_delay * (attempt + 2)
                    print(f"  HTTP {e.code}, retry in {wait:.0f}s...", file=sys.stderr)
                    time.sleep(wait)
                    continue
            raise RuntimeError(f"HTTP {e.code}: {err[:400]}") from e
        except json.JSONDecodeError as e:
            salvaged = salvage_json(raw)
            if salvaged is not None:
                n = len(salvaged.get("answers") or salvaged.get("questions") or [])
                print(f"  salvaged {n} item(s) from malformed JSON", file=sys.stderr)
                return salvaged
            if attempt == 3:
                raise RuntimeError(f"Non-JSON response: {raw[:200]}") from e
            tokens = min(tokens * 2, 16384)
            print(f"  JSON retry {attempt+1} (max_tokens={tokens})", file=sys.stderr)
            time.sleep(rpm_delay)
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt+1}: {e}", file=sys.stderr)
            time.sleep(rpm_delay * (attempt + 1))
    return {}


def call_gemini_native(
    api_key: str, model_id: str, image_path: Path, prompt: str, rpm_delay: float
) -> dict:
    import urllib.error
    import urllib.request

    b64 = base64.b64encode(image_path.read_bytes()).decode()
    url = (
        f"https://generativelanguage.googleapis.com/v1beta/models/"
        f"{model_id}:generateContent?key={api_key}"
    )
    payload = {
        "contents": [
            {
                "parts": [
                    {"text": prompt},
                    {"inline_data": {"mime_type": "image/png", "data": b64}},
                ]
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.1,
        },
    }
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                body = json.loads(resp.read().decode("utf-8"))
            text = body["candidates"][0]["content"]["parts"][0]["text"]
            return json.loads(text)
        except urllib.error.HTTPError as e:
            err = e.read().decode("utf-8", errors="replace")
            if e.code == 429:
                wait = rpm_delay * (attempt + 2)
                print(f"  rate limit, wait {wait:.0f}s...", file=sys.stderr)
                time.sleep(wait)
                continue
            raise RuntimeError(f"Gemini HTTP {e.code}: {err[:300]}") from e
        except Exception as e:
            if attempt == 3:
                raise
            print(f"  retry {attempt+1}: {e}", file=sys.stderr)
            time.sleep(rpm_delay * (attempt + 1))
    return {}


def _call_vision_one(
    provider: str, image_path: Path, prompt: str, kind: str
) -> dict:
    cfg = PROVIDER_PRESETS[provider]
    api_key = get_api_key(provider)
    if not api_key:
        raise RuntimeError(f"Missing {cfg['key_env']}")

    preset, model_id = resolve_model(provider)
    rpm_delay = cfg.get("rpm_delay", 2.0)
    model_ids = nvidia_model_chain(provider, preset) if provider == "nvidia" else [model_id]
    max_tokens = 8192 if kind == "answers" else 4096

    last_err: Exception | None = None
    for i, mid in enumerate(model_ids):
        try:
            if cfg.get("api_style") == "gemini_native":
                result = call_gemini_native(api_key, mid, image_path, prompt, rpm_delay)
            else:
                result = call_openai_compatible(
                    cfg["base_url"],
                    api_key,
                    mid,
                    image_path,
                    prompt,
                    extra_headers=cfg.get("extra_headers"),
                    rpm_delay=rpm_delay,
                    max_tokens=max_tokens,
                )
            if i > 0:
                print(f"  fallback model ok: {mid}", file=sys.stderr)
            time.sleep(rpm_delay)
            return result
        except RuntimeError as e:
            last_err = e
            msg = str(e)
            if ("500" in msg or "502" in msg or "503" in msg) and i < len(model_ids) - 1:
                print(f"  {mid} failed ({msg[:80]}), trying next model...", file=sys.stderr)
                continue
            raise
    if last_err:
        raise last_err
    return {}


def call_vision(
    image_path: Path, prompt: str, kind: str = "questions", provider: str | None = None
) -> dict:
    primary = provider or pick_provider()
    if primary == "none":
        print_provider_guide()
        raise SystemExit("\nSet an API key above (see --list-providers).")

    chain = [primary]
    for p in available_providers():
        if p != primary:
            chain.append(p)

    last_err: Exception | None = None
    for i, prov in enumerate(chain):
        try:
            return _call_vision_one(prov, image_path, prompt, kind)
        except Exception as e:
            last_err = e
            if i < len(chain) - 1:
                print(
                    f"  {prov} failed ({str(e)[:70]}), trying {chain[i + 1]}...",
                    file=sys.stderr,
                )
                continue
            raise
    if last_err:
        raise last_err
    return {}


def process_page(
    pdf_path: Path,
    page_num: int,
    kind: str,
    topic: str,
    provider: str | None = None,
) -> list[dict]:
    cp = cache_path(pdf_path.name, page_num, kind)
    if cp.exists():
        raw = json.loads(cp.read_text(encoding="utf-8"))
    else:
        img = render_page(pdf_path, page_num)
        prompt = QUESTION_PROMPT if kind == "questions" else ANSWER_PROMPT
        raw = call_vision(img, prompt, kind=kind, provider=provider)
        cp.write_text(json.dumps(raw, indent=2, ensure_ascii=False), encoding="utf-8")

    data = normalize_vision_payload(raw, kind)
    if data != raw:
        cp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    items = []
    if kind == "questions":
        for q in data.get("questions", []):
            num = int(q["number"])
            opts = {k.upper(): clean_option(v) for k, v in q.get("options", {}).items()}
            if len(opts) < 2:
                continue
            items.append(
                {
                    "id": f"{topic.lower().replace(' ', '-')}-{num}",
                    "topic": topic,
                    "number": num,
                    "question": clean_question(q.get("question", "")),
                    "options": opts,
                    "answer": None,
                    "explanation": None,
                }
            )
    else:
        for a in data.get("answers", []):
            num = int(a["number"])
            letter = str(a.get("answer", "")).upper().strip()
            if letter not in ("A", "B", "C"):
                continue
            items.append(
                {
                    "number": num,
                    "answer": letter,
                    "explanation": clean_explanation(a.get("explanation", "")),
                }
            )
    return items


def _topic_slug(topic: str) -> str:
    return topic.lower().replace(" ", "-")


def count_complete_for_topic(bank: dict[str, dict], topic: str) -> int:
    return sum(
        1
        for q in bank.values()
        if q.get("topic") == topic and q.get("answer") and is_embeddable(q)
    )


def topic_is_complete(bank: dict[str, dict], topic: str) -> bool:
    exp = EXPECTED_COUNTS.get(topic, 0)
    return exp > 0 and count_complete_for_topic(bank, topic) >= exp


def load_baseline_bank() -> dict[str, dict]:
    """Prefer questions.json (includes premium merges) over OCR-only baseline."""
    bank: dict[str, dict] = {}
    for path in (BASE / "questions.json", BASE / "questions_ocr.json"):
        if not path.exists():
            continue
        for q in json.loads(path.read_text(encoding="utf-8")):
            bank[q["id"]] = q
        print(f"Loaded baseline from {path.name}: {len(bank)} questions", file=sys.stderr)
        break
    return bank


def should_keep_existing(existing: dict, incoming: dict) -> bool:
    """In gaps-only mode, never replace a complete question with vision output."""
    if not existing:
        return False
    if existing.get("answer") and is_embeddable(existing):
        return True
    if not incoming.get("answer"):
        return bool(existing.get("answer"))
    return False


def extract_topic(
    pdf_name: str,
    topic: str,
    only_topic: str | None = None,
    parallel_providers: list[str] | None = None,
    gaps_only: bool = True,
    existing_bank: dict[str, dict] | None = None,
) -> list[dict]:
    if only_topic and topic != only_topic:
        return []

    existing_bank = existing_bank or {}
    if gaps_only and topic_is_complete(existing_bank, topic):
        exp = EXPECTED_COUNTS.get(topic, "?")
        have = count_complete_for_topic(existing_bank, topic)
        print(
            f"\n=== {topic} === SKIP (gaps-only: {have}/{exp} already complete)",
            file=sys.stderr,
        )
        return []

    sections = MANUAL_SECTIONS[pdf_name]
    pdf_path = BASE / pdf_name
    qsec = next(s for s in sections if s["topic"] == topic and s["type"] == "questions")
    asec = next(s for s in sections if s["topic"] == topic and s["type"] == "answers")

    all_q: dict[int, dict] = {}
    all_a: dict[int, dict] = {}

    tasks: list[tuple[int, str]] = []
    for p in range(qsec["start_page"], qsec["end_page"] + 1):
        tasks.append((p, "questions"))
    for p in range(asec["start_page"], asec["end_page"] + 1):
        tasks.append((p, "answers"))

    print(f"\n=== {topic} ===", file=sys.stderr)
    if parallel_providers and len(parallel_providers) >= 2:
        buckets: dict[str, list[tuple[int, str]]] = {p: [] for p in parallel_providers}
        for i, task in enumerate(tasks):
            buckets[parallel_providers[i % len(parallel_providers)]].append(task)

        def run_bucket(prov: str, bucket: list[tuple[int, str]]) -> tuple[dict, dict]:
            q_out: dict[int, dict] = {}
            a_out: dict[int, dict] = {}
            for page_num, kind in bucket:
                label = "Q" if kind == "questions" else "A"
                print(f"  [{prov}] {label} page {page_num + 1}...", file=sys.stderr)
                try:
                    page_items = process_page(pdf_path, page_num, kind, topic, provider=prov)
                except Exception as e:
                    print(f"  WARN {label} page {page_num + 1} failed: {e}", file=sys.stderr)
                    continue
                for item in page_items:
                    if kind == "questions":
                        q_out[item["number"]] = item
                    else:
                        a_out[item["number"]] = item
            return q_out, a_out

        with ThreadPoolExecutor(max_workers=len(parallel_providers)) as pool:
            futures = [
                pool.submit(run_bucket, prov, buckets[prov]) for prov in parallel_providers
            ]
            for fut in as_completed(futures):
                q_part, a_part = fut.result()
                all_q.update(q_part)
                all_a.update(a_part)
    else:
        for page_num, kind in tasks:
            label = "Q" if kind == "questions" else "A"
            print(f"  {label} page {page_num + 1}...", file=sys.stderr)
            try:
                page_items = process_page(pdf_path, page_num, kind, topic)
            except Exception as e:
                print(f"  WARN {label} page {page_num + 1} failed: {e}", file=sys.stderr)
                continue
            for item in page_items:
                if kind == "questions":
                    all_q[item["number"]] = item
                else:
                    all_a[item["number"]] = item

    merged = []
    for num in sorted(all_q):
        q = all_q[num]
        a = all_a.get(num)
        if a:
            q["answer"] = a["answer"]
            q["explanation"] = a["explanation"]
        if q.get("answer") and is_embeddable(q):
            merged.append(q)

    if gaps_only:
        slug = _topic_slug(topic)
        filtered = []
        for q in merged:
            qid = q.get("id") or f"{slug}-{q['number']}"
            q["id"] = qid
            prev = existing_bank.get(qid)
            if should_keep_existing(prev, q):
                continue
            filtered.append(q)
        merged = filtered

    exp = EXPECTED_COUNTS.get(topic, "?")
    print(
        f"  Result: {len(merged)} new/updated / {len(all_q)} parsed Q / {len(all_a)} parsed A / expected {exp}",
        file=sys.stderr,
    )
    return merged


def main():
    parser = argparse.ArgumentParser(description="Vision-based CFA question extraction")
    parser.add_argument("--topic", help="Process only this topic")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--list-providers", action="store_true", help="Show all providers/models")
    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Split pages across all free providers with keys (nvidia+opencode+gemini)",
    )
    parser.add_argument(
        "--no-parallel",
        action="store_true",
        help="Force single provider even when multiple API keys are set",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Re-run vision on every page and allow overwriting existing questions (default: gaps-only)",
    )
    args = parser.parse_args()
    gaps_only = not args.all

    if args.list_providers:
        print_provider_guide()
        return

    if args.dry_run:
        bank = load_baseline_bank()
        total = 0
        skipped_pages = 0
        for pdf_name, topics in PDFS:
            for topic in topics:
                if args.topic and topic != args.topic:
                    continue
                sections = MANUAL_SECTIONS[pdf_name]
                pages = sum(
                    sec["end_page"] - sec["start_page"] + 1
                    for sec in sections
                    if sec["topic"] == topic
                )
                if gaps_only and topic_is_complete(bank, topic):
                    skipped_pages += pages
                    print(f"  SKIP {topic}: {pages} pages ({count_complete_for_topic(bank, topic)}/{EXPECTED_COUNTS[topic]} complete)")
                else:
                    total += pages
                    have = count_complete_for_topic(bank, topic)
                    exp = EXPECTED_COUNTS.get(topic, "?")
                    print(f"  RUN  {topic}: {pages} pages ({have}/{exp} complete)")
        print(f"Vision pages to process: {total} (skipping {skipped_pages} in complete topics)")
        prov = pick_provider()
        if prov != "none":
            _, mid = resolve_model(prov)
            print(f"Auto-selected: {prov} / {mid}")
        par = available_providers()
        if len(par) >= 2:
            print(f"Parallel-capable providers ({len(par)}): {', '.join(par)}")
            print("  Runs all platforms automatically (or pass --parallel / --no-parallel)")
        elif prov == "none":
            print("No API key set — run with --list-providers")
        return

    if args.no_parallel:
        os.environ["VISION_PARALLEL"] = "0"
    parallel = should_use_parallel(explicit=args.parallel)
    parallel_providers = available_providers() if parallel else None
    if parallel and (not parallel_providers or len(parallel_providers) < 2):
        print("Need API keys for at least 2 of: nvidia, opencode, gemini", file=sys.stderr)
        raise SystemExit(1)

    if parallel_providers:
        print(
            f"Parallel mode: {len(parallel_providers)} providers",
            file=sys.stderr,
        )
        for p in parallel_providers:
            _, mid = resolve_model(p)
            print(f"  {p}: {mid}", file=sys.stderr)
    else:
        prov = pick_provider()
        if prov == "none":
            print_provider_guide()
            raise SystemExit("\nSet an API key (see --list-providers).")
        _, model_id = resolve_model(prov)
        cfg = PROVIDER_PRESETS[prov]
        print(f"Using {cfg['label']} / {model_id}", file=sys.stderr)
        print(f"Limits: {cfg['daily_note']}", file=sys.stderr)

    all_questions = load_baseline_bank()
    if gaps_only:
        print("Gaps-only mode: complete topics skipped; existing answers kept", file=sys.stderr)
    else:
        print("Full re-extract mode (--all): all pages processed, vision may overwrite", file=sys.stderr)

    for pdf_name, topics in PDFS:
        for topic in topics:
            for q in extract_topic(
                pdf_name,
                topic,
                args.topic,
                parallel_providers=parallel_providers,
                gaps_only=gaps_only,
                existing_bank=all_questions,
            ):
                all_questions[q["id"]] = q

    result = sorted(all_questions.values(), key=lambda x: (x["topic"], x["number"]))
    (BASE / "questions.json").write_text(
        json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    print(f"\n=== TOTAL: {len(result)} questions ===", file=sys.stderr)
    for t in sorted(EXPECTED_COUNTS):
        c = sum(1 for q in result if q["topic"] == t)
        print(f"  {t}: {c} (expected {EXPECTED_COUNTS[t]})", file=sys.stderr)

    import subprocess

    subprocess.run([sys.executable, str(BASE / "build_html.py")], check=True)


if __name__ == "__main__":
    main()
