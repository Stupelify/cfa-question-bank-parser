"""Shared OCR cleanup helpers for CFA question bank."""

import re

HEADER_PATTERNS = [
    r"corporate issuers?\s*-\s*(questions|answers)",
    r"equity investments?\s*-\s*(questions|answers)",
    r"ethical and professional standards?\s*-\s*(questions|answers)",
    r"fixed income\s*-\s*(questions|answers)",
    r"fsa\s*-\s*(questions|answers)",
    r"portfolio management\s*-\s*(questions|answers)",
    r"quantitative methods?\s*-\s*(questions|answers)",
    r"alternative investments?\s*-\s*(questions|answers)",
    r"derivatives\s*-\s*(questions|answers)",
    r"economics\s*-\s*(questions|answers)",
    r"financial statement analysis\s*-\s*(questions|answers)",
    r"mahakali book centre",
    r"eee+",
]

JUNK_LINE_RE = re.compile(
    r"^(?:"
    r"[|\-—_=]{2,}|"
    r"[A-Za-z?\d]{1,2}\s*$|"
    r";?\s*[ABC]\.\s*.*|"
    r"\d{1,3}\s*\|\s*$|"
    r"ns\s|"
    r"itions\s|"
    r"ce\s+—"
    r")",
    re.I,
)


def clean_question(text: str) -> str:
    text = (text or "").replace("\x0c", "\n").strip()
    text = re.sub(r"^[|\{\}\¢\s]+", "", text)
    text = re.sub(r"^[ABC]\n+", "", text)
    text = re.sub(r"^[ABC]\s+(?=[A-Z\"'])", "", text)

    for pat in HEADER_PATTERNS:
        text = re.sub(pat, "", text, flags=re.I)

    lines = [ln.strip() for ln in text.split("\n")]
    cleaned_lines = []
    for ln in lines:
        if not ln:
            continue
        if JUNK_LINE_RE.match(ln):
            continue
        if re.match(r"^[A-Z]\s*$", ln) and len(lines) > 1:
            continue
        if re.match(r"^[A-Za-z]{1,2}\s*$", ln) and ln.lower() not in ("an", "or", "if"):
            continue
        cleaned_lines.append(ln)
    text = "\n".join(cleaned_lines)

    text = re.sub(r"\s+[A-Z]\s*$", "", text)
    text = re.sub(r":\s*[A-Za-z]{1,2}\s*$", ":", text)
    text = re.sub(r"\s+[a-z]{1,2}\s*$", "", text)
    text = re.sub(r"\s+\)\s*[a-z],?\s*$", "", text)
    text = re.sub(r"\s+[wgp]\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+Cc\s*$", "", text)
    text = re.sub(r"\s+fol\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+vl\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+Al\s*$", "", text)
    text = re.sub(r"\s+\d{1,2}\s*$", "", text)
    text = re.sub(r"\n\s*\d{2,3}\s*\n", "\n", text)
    text = re.sub(
        r"\n(?:Ethical and Professional Standards|FSA|Alternative Investment)[^\n]*\n",
        "\n",
        text,
        flags=re.I,
    )
    text = re.sub(r"\s+[—\-_]{3,}\s*", " ", text)
    text = re.sub(r"\s+_\s+ee\s+a\s+—\s+Cc\s*", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_option(text: str) -> str:
    text = (text or "").strip()
    text = re.sub(r"^[|\}\{\s]+", "", text)
    if "\n" in text:
        text = text.split("\n")[0].strip()
    text = re.sub(r"\s+[ABC][c]?\.?\)?\s*$", "", text)
    text = re.sub(r"\s+[ABC]\.\s*$", "", text)
    text = re.sub(r"\s+\|\s*$", "", text)
    text = re.sub(r"\s+[0-9]{1,2}\s*$", "", text)
    text = re.sub(r"\s+[a-z]{1,2}\s*$", "", text)
    text = re.sub(r"\s+if\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+is\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+ik\s*$", "", text, flags=re.I)
    text = re.sub(r"\s+Q\s*$", "", text)
    text = re.sub(r"\s+Cc\s*$", "", text)
    return text.strip()


def strip_premium_paste_artifacts(text: str) -> str:
    """Remove Perplexity/chat export headers, citations, and source URLs from explanations."""
    if not text:
        return ""
    text = re.sub(r"\[ppl-ai-file-upload[^\]]*\]\([^\)]+\)", "", text)
    text = re.sub(r"Sources\s*\[\d+\].*$", "", text, flags=re.DOTALL | re.I)
    text = re.sub(r"https?://ppl-ai-file-upload[^\s]+", "", text)
    text = re.sub(r"#+\s*CFA Book \d+[^\n]*", "", text)
    text = re.sub(
        r"This file contains[^\n]*Premium Practice Pack\.?\s*(\[\d+\])?\s*",
        "",
        text,
        flags=re.I,
    )
    text = re.sub(r"#+\s*Questions\s+\d+[–-]\d+\s*", "", text)
    text = re.sub(r"\[\d+\]\s*$", "", text.strip())
    return text.strip()


def clean_explanation(text: str) -> str:
    if not text:
        return ""
    text = strip_premium_paste_artifacts(text.strip())
    for pat in HEADER_PATTERNS:
        text = re.sub(pat, "", text, flags=re.I)
    text = re.sub(r"\n?\s*\d{1,3}\s*\|\s*\n?", "\n", text)
    text = re.sub(r"^\s*i\s*\n", "", text, flags=re.I)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def is_embeddable(q: dict) -> bool:
    """Lenient check — keep question if usable despite OCR imperfections."""
    if q.get("answer") not in ("A", "B", "C"):
        return False
    qtext = q.get("question", "")
    if len(qtext) < 12:
        return False
    if re.match(r"^[ABC]\n", qtext) or re.match(r"^[ABC]\.\s", qtext):
        return False
    opts = q.get("options", {})
    present = [k for k in ("A", "B", "C") if opts.get(k) and len(opts[k]) >= 2]
    if len(present) < 2:
        return False
    if q["answer"] not in present and not opts.get(q["answer"]):
        return False
    alpha = sum(c.isalpha() for c in qtext)
    if alpha / max(len(qtext), 1) < 0.35:
        return False
    return True


def is_valid_mcq(q: dict) -> bool:
    """Strict check for high-quality questions."""
    if not is_embeddable(q):
        return False
    opts = q.get("options", {})
    if not all(len(opts.get(k, "")) >= 3 for k in ("A", "B", "C")):
        return False
    if len(q.get("question", "")) < 20:
        return False
    if re.search(r"\bMahakali\b|Questio[^n]|Ons FSA|_\s*ee\s*a", q.get("question", "")):
        return False
    return True


def question_issues(text: str) -> list[str]:
    issues = []
    if len(text) < 20:
        issues.append("too_short")
    if re.match(r"^[BC]\s+[A-Z]", text):
        issues.append("leading_option_letter")
    if re.match(r"^[ABC]\n", text) or re.match(r"^[ABC]\.\s", text):
        issues.append("leading_option_letter")
    if re.search(r"(?:Questions|Answers)\s*$", text, re.I):
        issues.append("header_bleed")
    return issues
