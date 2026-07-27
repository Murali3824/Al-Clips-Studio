"""Modular Metadata Engine.

Single source of truth for Title, Hook, Description, and Hashtag generation.
Integrates primary channel branding ('ClipForge World') and automated niche classification.
"""

import json
import re
from collections import Counter
from pathlib import Path
import requests

STOP_WORDS = {
    "a", "an", "and", "are", "as", "at", "be", "because", "but", "by",
    "for", "from", "has", "have", "how", "in", "into", "is", "it", "its",
    "of", "on", "or", "that", "the", "this", "to", "was", "with", "you",
    "your", "can", "will", "just", "about", "all", "what", "which", "when",
    "there", "here", "they", "them", "like", "more", "some", "very", "also"
}

# ── Primary Channel Branding ──────────────────────────────────────────────────
CHANNEL_NAME = "ClipForge World"
BRAND_HASHTAGS = ["#clipforgeworld", "#clipforge"]

# ── Niche Classification & Discovery Tags ─────────────────────────────────────
NICHE_KEYWORDS: dict[str, list[str]] = {
    "business": ["business", "money", "investing", "startup", "entrepreneur", "finance", "wealth", "sales", "market"],
    "tech": ["tech", "code", "ai", "software", "computer", "digital", "data", "future", "app"],
    "motivation": ["mindset", "success", "discipline", "goal", "focus", "habit", "growth", "life", "power"],
    "podcast": ["podcast", "interview", "conversation", "discussion", "thought", "idea", "advice", "guest"],
    "storytelling": ["story", "lesson", "moment", "experience", "truth", "secret", "history", "real"],
    "gaming": ["game", "play", "player", "gaming", "win", "level", "score", "clip", "stream"],
    "fitness": ["fitness", "workout", "health", "gym", "body", "diet", "energy", "training"],
    "education": ["learn", "how", "why", "method", "fact", "explain", "guide", "concept", "study"]
}

NICHE_HASHTAGS: dict[str, list[str]] = {
    "business": ["#entrepreneurship", "#businessgrowth", "#wealthbuilding", "#financialfreedom"],
    "tech": ["#techtrends", "#aitools", "#futuretech", "#softwareengineering"],
    "motivation": ["#mindsetshift", "#personaldevelopment", "#motivationdaily", "#successhabits"],
    "podcast": ["#podcastclips", "#podcastwisdom", "#deepthoughts", "#conversations"],
    "storytelling": ["#storytime", "#lifelessons", "#realstories", "#inspiration"],
    "gaming": ["#gamingcommunity", "#gamer", "#epicmoments", "#streamer"],
    "fitness": ["#fitnessmotivation", "#healthylifestyle", "#workouttips", "#gymtok"],
    "education": ["#learnontiktok", "#educational", "#facts", "#didyouknow"]
}


def clean_text(text: str) -> str:
    """Clean and normalize whitespace."""
    return re.sub(r"\s+", " ", text).strip()


def extract_keywords(text: str, limit: int = 12) -> list[str]:
    """Extract non-stop-word frequency-ranked keywords."""
    words = [
        word.lower()
        for word in re.findall(r"[a-zA-Z][a-zA-Z']{2,}", text)
        if word.lower() not in STOP_WORDS
    ]
    return [word for word, _count in Counter(words).most_common(limit)]


def detect_niche(keywords: list[str]) -> str:
    """Classify video content into a content niche based on keywords."""
    kw_set = set(keywords)
    scores = {
        niche: len(kw_set & set(words))
        for niche, words in NICHE_KEYWORDS.items()
    }
    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "podcast"


def generate_title(text: str, keywords: list[str]) -> str:
    """Generate a clean, punchy title under 60 characters."""
    sentence = re.split(r"(?<=[.!?])\s+", text)[0] if text else ""
    base = sentence or "Key Moment From This Short"
    base = clean_text(base)

    if len(base) > 55:
        base = base[:54].rsplit(" ", 1)[0]
    elif len(base) < 22 and keywords:
        base = f"{base}: {keywords[0].title()}".strip(": ")

    return base.strip()[:60]


def extract_dynamic_fallback_hook(clip_text: str, clip_index: int) -> str:
    """Extract a unique, scroll-stopping hook directly from transcript text when offline."""
    if not clip_text or not clip_text.strip():
        fallbacks = [
            "This Changed Everything...",
            "The Secret Most People Miss",
            "Don't Make This Mistake!",
            "Watch What Happens Next...",
            "The Truth They Hid From You",
        ]
        return fallbacks[clip_index % len(fallbacks)]

    sentences = [s.strip() for s in re.split(r"[.!?]", clip_text) if s.strip()]

    # Priority 1: Question or short impactful sentence
    for sentence in sentences:
        words = sentence.split()
        if 3 <= len(words) <= 9:
            clean = re.sub(r"[^a-zA-Z0-9\s']", "", sentence).strip()
            return clean.title() + "..."

    # Priority 2: Extract strong phrase from first sentence
    if sentences:
        words = sentences[0].split()
        if len(words) > 8:
            clean = " ".join(words[:7])
            clean = re.sub(r"[^a-zA-Z0-9\s']", "", clean).strip()
            return clean.title() + "..."
        elif len(words) >= 3:
            clean = re.sub(r"[^a-zA-Z0-9\s']", "", sentences[0]).strip()
            return clean.title() + "..."

    fallbacks = [
        "This Changed Everything...",
        "The Secret Most People Miss",
        "Don't Make This Mistake!",
        "Watch What Happens Next...",
    ]
    return fallbacks[clip_index % len(fallbacks)]


def generate_viral_hook(clip_text: str, clip_index: int, settings: dict) -> str:
    """Generate a high-CTR title hook using local Ollama or dynamic content extraction."""
    fallback = extract_dynamic_fallback_hook(clip_text, clip_index)
    base_url = settings.get("ollamaUrl", "http://localhost:11434").rstrip("/")
    model = settings.get("ollamaModel", "llama3:8b")

    if not clip_text or not clip_text.strip():
        return fallback

    try:
        response = requests.get(f"{base_url}/api/tags", timeout=1.5)
        if not response.ok:
            return fallback

        prompt = (
            "You are a top-tier YouTube Shorts content editor.\n"
            "Given the transcript of a video clip, craft a unique, punchy, curiosity-inducing video title hook (3 to 7 words).\n"
            "The hook MUST be specifically tailored to the clip's topic and create immense curiosity.\n\n"
            "Rules:\n"
            "- Do NOT repeat the exact first sentence of the transcript.\n"
            "- Do NOT use generic meta phrases like 'Here is a clip'.\n"
            "- Return ONLY the hook text (plain text, no quotes, no markdown, 7 words max).\n\n"
            f"Transcript:\n\"{clip_text[:400]}\""
        )

        res = requests.post(
            f"{base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "options": {
                    "temperature": 0.7,
                    "num_predict": 15
                }
            },
            timeout=5.0
        )
        if res.ok:
            hook = res.json().get("response", "").strip()
            hook = re.sub(r'^["\'`\-*]+|["\'`\-*]+$', '', hook).strip()
            word_count = len(hook.split())
            if 3 <= word_count <= 8 and len(hook) > 5:
                return hook
    except Exception:
        pass

    return fallback


def generate_description(text: str, keywords: list[str], niche: str) -> str:
    """Generate a clean, structured YouTube Shorts description with subscriber CTA."""
    summary = clean_text(text)
    if len(summary) > 280:
        summary = summary[:277].rsplit(" ", 1)[0] + "..."

    topic_str = ", ".join(kw.title() for kw in keywords[:4]) if keywords else niche.title()

    lines = [
        f"🔥 {summary}",
        "",
        f"📌 Key Topics: {topic_str}",
        f"🔔 Subscribe to {CHANNEL_NAME} for daily short clips, insights, and top highlights!",
    ]
    return "\n".join(lines).strip()


def generate_hashtags(keywords: list[str], niche: str) -> list[str]:
    """Generate balanced hashtags combining Channel Branding, Niche, and Topic keywords."""
    tags = list(BRAND_HASHTAGS) + ["#youtubeshorts", "#shorts", "#viral"]

    if niche in NICHE_HASHTAGS:
        for tag in NICHE_HASHTAGS[niche]:
            if tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)

    for keyword in keywords:
        tag = "#" + re.sub(r"[^a-zA-Z0-9]", "", keyword.title())
        if len(tag) > 2 and tag.lower() not in {t.lower() for t in tags}:
            tags.append(tag)
        if len(tags) >= 15:
            break

    return tags[:16]
