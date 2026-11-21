#!/usr/bin/env python3
"""Generate a new self-contained HTML5 mini-game using the Gemini API."""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import random
import re
import sys
import time
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
GAMES_JSON = ROOT / "games.json"
GAMES_DIR = ROOT / "games"

DEFAULT_MODELS = [
    os.environ.get("GEMINI_MODEL", "gemini-4-hydrogen"),
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemini-3.1-flash-lite-preview",
    "gemini-3.8-flash",
]
PREFERRED_MODELS = list(dict.fromkeys(m for m in DEFAULT_MODELS if m))

GENRE_SEEDS = [
    "one-button timing reflex game",
    "physics slingshot or ricochet puzzle",
    "grid-based tactical or logic puzzle",
    "fast-paced arcade survival dodger",
    "rhythm or beat-matching challenge",
    "chain-reaction color/tile matching game",
    "grappling or momentum platformer",
    "memory and pattern-recognition duel",
    "miniature tower defense or wave shooter",
    "balancing or stacking physics challenge",
]

CATEGORIES = ["Arcade", "Puzzle", "Reflex", "Action", "Strategy", "Physics"]
ACCENTS = [
    "#E85D04",
    "#0EA5E9",
    "#10B981",
    "#8B5CF6",
    "#EC4899",
    "#F59E0B",
    "#EF4444",
    "#14B8A6",
]


def load_games() -> list[dict]:
    if not GAMES_JSON.exists():
        return []
    data = json.loads(GAMES_JSON.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("games.json must contain a JSON array")
    return data


def sanitize_slug(raw: str, existing_slugs: set[str]) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = "mini-game"
    base = slug[:40].strip("-") or "mini-game"
    candidate = base
    suffix = 2
    while candidate in existing_slugs or (GAMES_DIR / candidate).exists():
        candidate = f"{base}-{suffix}"
        suffix += 1
    return candidate


def strip_code_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z0-9_-]*\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    return text.strip()


def list_available_models(api_key: str) -> list[str]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        models = []
        for m in data.get("models", []):
            methods = m.get("supportedGenerationMethods", [])
            name = str(m.get("name", "")).removeprefix("models/")
            if "generateContent" in methods and name:
                models.append(name)
        print(f"Available generateContent models: {', '.join(models[:15])}", flush=True)
        return models
    except Exception as exc:
        print(f"Could not list models: {exc}", file=sys.stderr, flush=True)
        return []


def call_gemini(api_key: str, prompt: str) -> dict:
    available = list_available_models(api_key)
    if available:
        hydrogen_models = [m for m in available if "hydrogen" in m.lower()]
        flash_models = [m for m in available if "flash" in m and "tts" not in m and "image" not in m and "audio" not in m]
        models_to_try = list(
            dict.fromkeys(
                [m for m in PREFERRED_MODELS if m in available]
                + hydrogen_models
                + flash_models
            )
        )
        if not models_to_try:
            models_to_try = PREFERRED_MODELS
    else:
        models_to_try = PREFERRED_MODELS

    base_gen_config = {
        "temperature": 1.0,
        "maxOutputTokens": 12288,
        "responseMimeType": "application/json",
    }

    last_error: Exception | None = None

    for model in models_to_try:
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{model}:generateContent?key={api_key}"
        )
        use_thinking_config = True
        for attempt in range(1, 3):
            gen_config = dict(base_gen_config)
            if use_thinking_config:
                if model.startswith("gemini-4-"):
                    gen_config["thinkingConfig"] = {"thinkingLevel": "low"}
                else:
                    gen_config["thinkingConfig"] = {"thinkingBudget": 0}
            encoded_payload = json.dumps(
                {
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": gen_config,
                }
            ).encode("utf-8")

            print(f"Calling {model} (attempt {attempt})...", flush=True)
            req = urllib.request.Request(
                url,
                data=encoded_payload,
                headers={"Content-Type": "application/json"},
                method="POST",
            )
            try:
                with urllib.request.urlopen(req, timeout=60) as resp:
                    body = json.loads(resp.read().decode("utf-8"))
                candidates = body.get("candidates") or []
                if not candidates:
                    raise RuntimeError(f"Gemini returned no candidates: {body}")
                parts = candidates[0].get("content", {}).get("parts", [])
                raw_text = "".join(part.get("text", "") for part in parts)
                if not raw_text.strip():
                    raise RuntimeError(f"Gemini returned empty text: {body}")
                parsed = json.loads(strip_code_fences(raw_text))
                print(f"Generated response using model {model} (attempt {attempt})", flush=True)
                return parsed
            except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as exc:
                if isinstance(exc, urllib.error.HTTPError):
                    err_body = exc.read().decode("utf-8", errors="replace")
                    last_error = RuntimeError(
                        f"Gemini API HTTP {exc.code} ({model}): {err_body}"
                    )
                    if exc.code == 400 and use_thinking_config and "thinking" in err_body.lower():
                        print(f"{model} rejected thinkingConfig, retrying without it...", file=sys.stderr, flush=True)
                        use_thinking_config = False
                        continue
                    if exc.code == 404:
                        print(f"Model {model} unavailable (404), trying next model...", file=sys.stderr, flush=True)
                        break
                    if exc.code in (429, 500, 502, 503, 504) and attempt < 2:
                        delay = 3
                        print(
                            f"Transient HTTP {exc.code} from {model}; retrying in {delay}s...",
                            file=sys.stderr,
                            flush=True,
                        )
                        time.sleep(delay)
                        continue
                    if exc.code in (429, 500, 502, 503, 504):
                        print(f"Model {model} failed with HTTP {exc.code}, trying next model...", file=sys.stderr, flush=True)
                        break
                    raise last_error from exc
                last_error = exc
                print(f"Transient error from {model} (attempt {attempt}): {exc}", file=sys.stderr, flush=True)
                if isinstance(exc, TimeoutError):
                    break
                if attempt < 2:
                    time.sleep(3)
                    continue
                break

    assert last_error is not None
    raise last_error


def build_prompt(existing_games: list[dict]) -> str:
    existing_list = "\n".join(
        f"- {g.get('title', '')} ({g.get('slug', '')}): {g.get('description', '')}"
        for g in existing_games
    ) or "- (none yet)"

    custom_theme = os.environ.get("GAME_THEME", "").strip()
    seed = custom_theme if custom_theme else random.choice(GENRE_SEEDS)
    suggested_accent = random.choice(ACCENTS)

    return f"""Create a brand-new, super fun, polished, self-contained HTML5 browser mini-game for "Fun Arcade".

Inspiration seed for this hour: {seed}
Suggested accent color (you may use this or another vibrant hex): {suggested_accent}

Existing games already in the arcade (DO NOT duplicate these concepts or names):
{existing_list}

Requirements for the output JSON fields:
1. "slug": short kebab-case identifier (2-3 words, lowercase letters and hyphens only).
2. "title": catchy 2-3 word game title.
3. "description": 1 crisp sentence explaining how to play (max 140 chars).
4. "category": one of {", ".join(CATEGORIES)}.
5. "accent": valid 6-digit hex color like "#E85D04".
6. "html": a complete, single-file HTML5 document (`<!DOCTYPE html>...</html>`) with inline `<style>` and `<script>`:
   - Works immediately with zero external JS/CSS libraries (optional Google Fonts link is okay, no local file dependencies).
   - Responsive layout that fits cleanly in `100dvh` on both desktop and mobile (touch + mouse + keyboard controls).
   - Top bar with a `<a href="../../" class="back-btn">Back</a>` link to return to the arcade menu, live Score and Best Score HUD, and a `?` ("How to Play") button that toggles a clean About/How-to-Play overlay explaining the goal, rules, and controls anytime.
   - Crisp start screen / overlay with a clear 1-2 sentence description of the game, a subtle bottom controls hint bar, active gameplay loop (`requestAnimationFrame` or clean event loop), satisfying visual feedback (particles, screen shake, or Web Audio API synth sound effects with a mute toggle), and a Game Over / Win overlay with Play Again.
   - Saves high score to `localStorage` using key `'fun_arcade_highscore_' + SLUG` (where `SLUG` matches your `slug` field) so the main arcade menu can display the player's best score.
   - Bug-free, fair difficulty curve, and genuinely fun to play!
"""


def validate_html(html: str) -> str:
    cleaned = strip_code_fences(html)
    lower = cleaned.lower()
    if "<html" not in lower or "</html>" not in lower or "<script" not in lower:
        raise ValueError("Generated HTML is incomplete or missing required tags.")
    if len(cleaned) < 1500:
        raise ValueError(f"Generated HTML is suspiciously short ({len(cleaned)} chars).")
    return cleaned


def main() -> int:
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        print("Error: GEMINI_API_KEY environment variable is not set.", file=sys.stderr)
        return 1

    existing_games = load_games()
    existing_slugs = {str(g.get("slug", "")).strip() for g in existing_games}

    prompt = build_prompt(existing_games)
    result = call_gemini(api_key, prompt)

    raw_slug = str(result.get("slug", "mini-game"))
    slug = sanitize_slug(raw_slug, existing_slugs)
    title = str(result.get("title", "")).strip() or slug.replace("-", " ").title()
    description = str(result.get("description", "")).strip() or "Play this AI-generated browser mini-game."
    category = str(result.get("category", "Arcade")).strip()
    if category not in CATEGORIES:
        category = "Arcade"

    accent = str(result.get("accent", "")).strip()
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", accent):
        accent = random.choice(ACCENTS)

    html = validate_html(str(result.get("html", "")))
    if raw_slug != slug:
        html = html.replace(f"fun_arcade_highscore_{raw_slug}", f"fun_arcade_highscore_{slug}")

    game_dir = GAMES_DIR / slug
    game_dir.mkdir(parents=True, exist_ok=True)
    game_file = game_dir / "index.html"
    game_file.write_text(html + "\n", encoding="utf-8")

    new_entry = {
        "slug": slug,
        "title": title,
        "description": description,
        "category": category,
        "accent": accent,
        "addedAt": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z"),
    }
    existing_games.append(new_entry)
    GAMES_JSON.write_text(json.dumps(existing_games, indent=2) + "\n", encoding="utf-8")

    print(f"Generated game '{title}' at {game_file.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
