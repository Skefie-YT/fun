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
import urllib.error
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[2]
GAMES_JSON = ROOT / "games.json"
GAMES_DIR = ROOT / "games"

GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
API_URL = (
    f"https://generativelanguage.googleapis.com/v1beta/models/"
    f"{GEMINI_MODEL}:generateContent"
)

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


def call_gemini(api_key: str, prompt: str) -> dict:
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": 1.0,
            "responseMimeType": "application/json",
            "responseSchema": {
                "type": "OBJECT",
                "properties": {
                    "slug": {"type": "STRING"},
                    "title": {"type": "STRING"},
                    "description": {"type": "STRING"},
                    "category": {"type": "STRING"},
                    "accent": {"type": "STRING"},
                    "html": {"type": "STRING"},
                },
                "required": [
                    "slug",
                    "title",
                    "description",
                    "category",
                    "accent",
                    "html",
                ],
            },
        },
    }

    req = urllib.request.Request(
        f"{API_URL}?key={api_key}",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        err_body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTP {exc.code}: {err_body}") from exc

    candidates = body.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {body}")

    parts = candidates[0].get("content", {}).get("parts", [])
    raw_text = "".join(part.get("text", "") for part in parts)
    if not raw_text.strip():
        raise RuntimeError(f"Gemini returned empty text: {body}")

    return json.loads(strip_code_fences(raw_text))


def build_prompt(existing_games: list[dict]) -> str:
    existing_list = "\n".join(
        f"- {g.get('title', '')} ({g.get('slug', '')}): {g.get('description', '')}"
        for g in existing_games
    ) or "- (none yet)"

    seed = random.choice(GENRE_SEEDS)
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
   - Top bar with a `<a href="../../" class="back-btn">Back</a>` link to return to the arcade menu, plus live Score and Best Score HUD.
   - Crisp start screen / overlay, active gameplay loop (`requestAnimationFrame` or clean event loop), satisfying visual feedback (particles, screen shake, or Web Audio API synth sound effects with a mute toggle), and a Game Over / Win overlay with Play Again.
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
