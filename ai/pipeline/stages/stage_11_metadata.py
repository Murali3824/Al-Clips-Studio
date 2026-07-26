import json
from pathlib import Path

import sys
sys.path.append(str(Path(__file__).resolve().parent.parent))

from metadata_engine import (
    CHANNEL_NAME,
    clean_text,
    extract_keywords,
    detect_niche,
    generate_title,
    generate_description,
    generate_hashtags,
)

PLATFORM_RULES = [
    ("TikTok", {"quick", "simple", "trend", "secret", "mistake", "stop", "start"}),
    ("Instagram Reels", {"creator", "story", "visual", "brand", "moment", "share"}),
    ("YouTube Shorts", {"how", "why", "learn", "important", "remember", "method"}),
]


def _platform(keywords: list[str], duration: float) -> str:
    keyword_set = set(keywords)
    scores = {
        platform: len(keyword_set & platform_keywords)
        for platform, platform_keywords in PLATFORM_RULES
    }
    if duration <= 20:
        scores["TikTok"] += 1
        scores["Instagram Reels"] += 1
    else:
        scores["YouTube Shorts"] += 1
    return max(scores, key=scores.get)


def _posting_time(platform: str) -> str:
    if platform == "TikTok":
        return "Weekday evening, 6 PM - 9 PM"
    if platform == "Instagram Reels":
        return "Weekday lunch or evening, 12 PM - 2 PM or 6 PM - 8 PM"
    return "Weekday afternoon, 2 PM - 5 PM"


def run(context):
    print("Generating metadata...", flush=True)
    metadata_dir = context["output_dir"] / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    highlights = json.loads(
        (context["temp_dir"] / "highlights.json").read_text(encoding="utf-8")
    )["highlights"]

    for highlight in highlights:
        text = clean_text(highlight.get("text") or highlight.get("hook") or "")
        if not text:
            raise RuntimeError(f"No transcript text available for {highlight['id']}")

        start = float(highlight["start"])
        end = float(highlight["end"])
        duration = float(highlight.get("duration") or end - start)
        keywords = extract_keywords(text)
        niche = detect_niche(keywords)
        platform = _platform(keywords, duration)
        tags = generate_hashtags(keywords, niche)

        title = generate_title(text, keywords)
        desc = generate_description(text, keywords, niche)

        # AI Decision Confidence Score
        confidence = 0.95 if len(keywords) >= 3 else 0.80

        metadata = {
            "pipelineVersion": "2.4.0",
            "schemaVersion": "1.1",
            "title": title,
            "description": desc,
            "tags": tags,
            "channel": CHANNEL_NAME,
            "niche": niche,
            "confidenceScore": confidence,
            "platformRecommendation": platform,
            "suggestedPostingTime": _posting_time(platform),
            "sourceStart": start,
            "sourceEnd": end,
            "sourceDuration": duration,
            "keywords": keywords,
            "diagnostics": {
                "keywordCount": len(keywords),
                "nicheClassification": niche,
                "brandingIncluded": True,
            },
        }

        (metadata_dir / f"{highlight['id']}.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        (metadata_dir / f"{highlight['id']}.txt").write_text(
            "\n\n".join([
                f"Title: {title}",
                f"Description:\n{desc}",
                f"Hashtags:\n{' '.join(tags)}",
                f"Channel: {CHANNEL_NAME}",
                f"Recommended Platform: {platform}",
                f"Suggested Posting Time: {metadata['suggestedPostingTime']}",
            ]) + "\n",
            encoding="utf-8",
        )
