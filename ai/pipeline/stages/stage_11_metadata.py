import json
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).resolve().parent.parent))

from metadata_engine import (
    CHANNEL_NAME,
    clean_text,
    generate_with_quality_review,
)

def run(context):
    print("Generating production-grade metadata with 2-pass quality review...", flush=True)
    metadata_dir = context["output_dir"] / "metadata"
    metadata_dir.mkdir(parents=True, exist_ok=True)

    highlights_file = context["temp_dir"] / "highlights.json"
    if not highlights_file.exists():
        highlights_file = context["output_dir"] / "highlights.json"

    highlights = json.loads(highlights_file.read_text(encoding="utf-8"))["highlights"]

    for highlight in highlights:
        text = clean_text(highlight.get("text") or highlight.get("hook") or "")
        if not text:
            continue

        start = float(highlight.get("start", 0.0))
        end = float(highlight.get("end", 0.0))
        duration = float(highlight.get("duration") or max(0.5, end - start))

        # Generate production metadata via 2-pass quality review engine
        meta_res = generate_with_quality_review(highlight, context.get("settings", {}))

        metadata = {
            "pipelineVersion": "2.5.0",
            "schemaVersion": "1.2",
            "title": meta_res["title"],
            "hook": meta_res["hook"],
            "autoHookText": meta_res["autoHookText"],
            "description": meta_res["description"],
            "tags": meta_res["tags"],
            "categorizedHashtags": meta_res["categorizedHashtags"],
            "channel": CHANNEL_NAME,
            "niche": meta_res["category"],
            "category": meta_res["category"],
            "targetAudience": meta_res["targetAudience"],
            "mood": meta_res["mood"],
            "ctrPrediction": meta_res.get("ctrPrediction"),
            "seoScore": meta_res.get("seoScore"),
            "hookScore": meta_res.get("hookScore"),
            "retentionScore": meta_res.get("retentionScore"),
            "emotionalImpact": meta_res.get("emotionalImpact"),
            "productionScore": meta_res.get("productionScore"),
            "viralScore": meta_res.get("viralScore"),
            "score": meta_res.get("score"),
            "qualityScore": meta_res.get("qualityScore"),
            "confidenceScore": meta_res.get("confidenceScore"),
            "platformRecommendation": "YouTube Shorts",
            "suggestedPostingTime": meta_res["bestPostingTime"],
            "sourceStart": start,
            "sourceEnd": end,
            "sourceDuration": duration,
            "keywords": meta_res["keywords"],
            "diagnostics": {
                "keywordCount": len(meta_res["keywords"]),
                "qualityReviewPassed": meta_res["qualityScore"] >= 75,
                "brandingIncluded": True,
            },
        }

        (metadata_dir / f"{highlight['id']}.json").write_text(
            json.dumps(metadata, indent=2),
            encoding="utf-8",
        )
        (metadata_dir / f"{highlight['id']}.txt").write_text(
            "\n\n".join([
                f"Title: {meta_res['title']}",
                f"Hook: {meta_res['hook']}",
                f"Description:\n{meta_res['description']}",
                f"Hashtags:\n{' '.join(meta_res['tags'])}",
                f"Channel: {CHANNEL_NAME}",
                f"Category: {meta_res['category']}",
                f"Suggested Posting Time: {meta_res['bestPostingTime']}",
            ]) + "\n",
            encoding="utf-8",
        )
