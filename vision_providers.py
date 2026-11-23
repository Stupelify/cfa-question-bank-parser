"""Vision provider registry for CFA page extraction."""

from __future__ import annotations

import os

# Presets tuned for scanned PDF MCQ + answer-key extraction
PROVIDER_PRESETS: dict[str, dict] = {
    "opencode": {
        "label": "OpenCode Zen",
        "key_env": "OPENCODE_API_KEY",
        "key_url": "https://opencode.ai/auth",
        "base_url": "https://opencode.ai/zen/v1",
        "rpm_delay": 4.0,
        "daily_note": "Free promo; rate-limited",
        "models": {
            "mimo": {
                "id": "mimo-v2.5-free",
                "label": "MiMo V2.5 Free",
                "vision": True,
                "recommended": True,
                "note": "Best if you already use OpenCode. Strong document vision.",
            },
        },
        "default_model": "mimo",
    },
    "nvidia": {
        "label": "NVIDIA NIM (build.nvidia.com)",
        "key_env": "NVIDIA_API_KEY",
        "key_url": "https://build.nvidia.com",
        "base_url": "https://integrate.api.nvidia.com/v1",
        "rpm_delay": 1.6,  # ~40 req/min free tier
        "daily_note": "~40 RPM, good for all 517 pages in ~15 min",
        "models": {
            "llama-vision-11b": {
                "id": "meta/llama-3.2-11b-vision-instruct",
                "label": "Llama 3.2 11B Vision",
                "vision": True,
                "recommended": True,
                "note": "Stable on NVIDIA NIM; best default for PDF extraction.",
            },
            "llama-maverick": {
                "id": "meta/llama-4-maverick-17b-128e-instruct",
                "label": "Llama 4 Maverick 17B",
                "vision": True,
                "recommended": True,
                "note": "Multimodal, good on tables.",
            },
            "llama-vision-90b": {
                "id": "meta/llama-3.2-90b-vision-instruct",
                "label": "Llama 3.2 90B Vision",
                "vision": True,
                "recommended": False,
                "note": "Higher quality, slower/heavier.",
            },
            "nemotron-vl": {
                "id": "nvidia/llama-3.1-nemotron-nano-vl-8b-v1",
                "label": "Nemotron Nano VL 8B",
                "vision": True,
                "recommended": False,
                "note": "Currently broken on NIM (500 error) — avoid until fixed.",
            },
        },
        "default_model": "llama-vision-11b",
        "fallback_presets": ["llama-maverick", "llama-vision-90b"],
    },
    "openrouter": {
        "label": "OpenRouter",
        "key_env": "OPENROUTER_API_KEY",
        "key_url": "https://openrouter.ai/keys",
        "base_url": "https://openrouter.ai/api/v1",
        "rpm_delay": 3.5,
        "daily_note": "⚠️ Free tier ~50–200 req/day — NOT enough alone for 517 pages",
        "extra_headers": {
            "HTTP-Referer": "https://local.cfa-quiz",
            "X-Title": "CFA Quiz Extractor",
        },
        "models": {
            "llama-maverick": {
                "id": "meta-llama/llama-4-maverick:free",
                "label": "Llama 4 Maverick Free",
                "vision": True,
                "recommended": True,
                "note": "Best OpenRouter free vision model for documents.",
            },
            "nemotron-vl": {
                "id": "nvidia/nemotron-nano-12b-v2-vl:free",
                "label": "Nemotron Nano 12B VL Free",
                "vision": True,
                "recommended": True,
                "note": "NVIDIA vision model via OpenRouter.",
            },
            "nemotron-omni": {
                "id": "nvidia/nemotron-3-nano-omni-30b-a3b-reasoning:free",
                "label": "Nemotron 3 Nano Omni Free",
                "vision": True,
                "recommended": False,
                "note": "Multimodal but slower; use if others fail.",
            },
            "auto-free": {
                "id": "openrouter/free",
                "label": "OpenRouter Free Router",
                "vision": True,
                "recommended": False,
                "note": "Random free model — unpredictable for JSON extraction.",
            },
        },
        "default_model": "llama-maverick",
    },
    "gemini": {
        "label": "Google Gemini",
        "key_env": "GEMINI_API_KEY",
        "key_alt_env": "GOOGLE_API_KEY",
        "key_url": "https://aistudio.google.com/apikey",
        "api_style": "gemini_native",
        "rpm_delay": 6.5,
        "daily_note": "Free tier; ~10–15 RPM",
        "models": {
            "flash-lite": {
                "id": "gemini-2.5-flash-lite",
                "label": "Gemini 2.5 Flash Lite",
                "vision": True,
                "recommended": True,
                "note": "Fastest free Gemini; good for bulk page extraction.",
            },
            "flash": {
                "id": "gemini-2.5-flash",
                "label": "Gemini 2.5 Flash",
                "vision": True,
                "recommended": False,
                "note": "Slightly better quality, same free tier.",
            },
            "flash-lite-31": {
                "id": "gemini-3.1-flash-lite",
                "label": "Gemini 3.1 Flash Lite",
                "vision": True,
                "recommended": False,
                "note": "Newest lite model.",
            },
        },
        "default_model": "flash-lite",
    },
    "openai": {
        "label": "OpenAI",
        "key_env": "OPENAI_API_KEY",
        "key_url": "https://platform.openai.com/api-keys",
        "base_url": "https://api.openai.com/v1",
        "rpm_delay": 0.5,
        "daily_note": "Paid (~$1–4 for all pages)",
        "models": {
            "mini": {
                "id": "gpt-4o-mini",
                "label": "GPT-4o Mini",
                "vision": True,
                "recommended": True,
                "note": "Reliable JSON + vision; small cost.",
            },
        },
        "default_model": "mini",
    },
}

# Ranked for CFA scanned-PDF task (517 pages, JSON output, tables/formulas)
RECOMMENDED_FOR_CFA = [
    ("nvidia", "llama-vision-11b", "Stable on NIM free tier; ~40 RPM"),
    ("opencode", "mimo", "Free MiMo V2.5 — great if you have OpenCode"),
    ("gemini", "flash-lite", "Free Google vision, slower RPM but reliable"),
    ("nvidia", "llama-maverick", "NVIDIA fallback if 11B vision fails"),
    ("openrouter", "llama-maverick", "Good quality but daily cap blocks full run"),
    ("openai", "mini", "Paid fallback, most reliable JSON"),
]


def get_api_key(provider: str) -> str | None:
    cfg = PROVIDER_PRESETS.get(provider, {})
    key_env = cfg.get("key_env")
    if not key_env:
        return None
    key = os.environ.get(key_env, "")
    if not key and cfg.get("key_alt_env"):
        key = os.environ.get(cfg["key_alt_env"], "")
    return key or None


def nvidia_model_chain(provider: str, primary_preset: str) -> list[str]:
    """Ordered list of model API ids to try for NVIDIA."""
    cfg = PROVIDER_PRESETS[provider]
    chain = []
    if primary_preset in cfg["models"]:
        chain.append(cfg["models"][primary_preset]["id"])
    for fb in cfg.get("fallback_presets", []):
        mid = cfg["models"][fb]["id"]
        if mid not in chain:
            chain.append(mid)
    return chain


def resolve_model(provider: str, model_preset: str | None = None) -> tuple[str, str]:
    """Return (provider_id, api_model_id)."""
    cfg = PROVIDER_PRESETS[provider]
    preset = model_preset or os.environ.get("VISION_MODEL_PRESET") or cfg["default_model"]
    if preset in cfg["models"]:
        return preset, cfg["models"][preset]["id"]
    # Allow passing raw model id directly (cloud paths, Gemini/GPT)
    if preset and (
        "/" in preset
        or preset.startswith("gemini")
        or preset.startswith("gpt")
    ):
        return preset, preset
    return cfg["default_model"], cfg["models"][cfg["default_model"]]["id"]


PARALLEL_PROVIDERS = ["nvidia", "opencode", "gemini"]


def available_providers(include_openrouter: bool = False) -> list[str]:
    """Providers with API keys that can share a bulk extraction run."""
    out = [p for p in PARALLEL_PROVIDERS if get_api_key(p)]
    if include_openrouter and get_api_key("openrouter"):
        out.append("openrouter")
    return out


def should_use_parallel(explicit: bool = False) -> bool:
    """Use all configured free platforms in parallel unless explicitly disabled."""
    env = os.environ.get("VISION_PARALLEL", "").lower()
    if env in ("0", "false", "no"):
        return False
    if explicit or env in ("1", "true", "yes"):
        return len(available_providers()) >= 2
    # Default: parallel whenever 2+ platform keys are set
    return len(available_providers()) >= 2


def pick_provider() -> str:
    forced = os.environ.get("VISION_PROVIDER", "auto").lower()
    if forced != "auto" and forced in PROVIDER_PRESETS:
        return forced
    # Auto: first provider with API key, in quality order
    for prov, _, _ in RECOMMENDED_FOR_CFA:
        if get_api_key(prov):
            return prov
    return "none"


def print_provider_guide() -> None:
    print("\n=== CFA Vision Extractor — Providers & Models ===\n")
    print("Task: read 517 scanned PDF pages → JSON questions + answers\n")
    print("TOP PICKS for this job (free, vision, enough throughput):\n")
    for i, (prov, preset, why) in enumerate(RECOMMENDED_FOR_CFA, 1):
        cfg = PROVIDER_PRESETS[prov]
        m = cfg["models"][preset]
        print(f"  {i}. {cfg['label']} / {m['label']}")
        print(f"     Model ID: {m['id']}")
        print(f"     Key: export {cfg['key_env']}=...  ({cfg['key_url']})")
        print(f"     Why: {why}")
        print(f"     Limits: {cfg['daily_note']}\n")

    print("All supported providers:\n")
    for prov, cfg in PROVIDER_PRESETS.items():
        print(f"  [{prov}] {cfg['label']} — {cfg['key_env']}")
        for name, m in cfg["models"].items():
            if not m.get("vision"):
                continue
            rec = " ★ recommended" if m.get("recommended") else ""
            print(f"      {name}: {m['id']}{rec}")
        print()

    print("Quick start examples:\n")
    print("  # All free platforms at once (auto if 2+ keys set)")
    print("  export NVIDIA_API_KEY=nvapi-...")
    print("  export OPENCODE_API_KEY=...")
    print("  export GEMINI_API_KEY=...")
    print("  .venv/bin/python3 extract_vision.py --parallel")
    print("  # Or single platform only:")
    print("  export VISION_PROVIDER=nvidia")
    print("  export VISION_PARALLEL=0")
    print("  .venv/bin/python3 extract_vision.py --topic 'Portfolio Management'\n")
    print("  # NVIDIA only")
    print("  export NVIDIA_API_KEY=nvapi-...")
    print("  export VISION_PROVIDER=nvidia")
    print("  export VISION_MODEL_PRESET=llama-vision-11b")
    print("  .venv/bin/python3 extract_vision.py\n")
    print("  # OpenCode MiMo V2.5")
    print("  export OPENCODE_API_KEY=...")
    print("  export VISION_PROVIDER=opencode")
    print("  .venv/bin/python3 extract_vision.py\n")
    print("  # OpenRouter (supplement only — daily cap)")
    print("  export OPENROUTER_API_KEY=...")
    print("  export VISION_PROVIDER=openrouter")
    print("  export VISION_MODEL_PRESET=llama-maverick\n")
