"""
Pass 6 — Production Scoring Engine
===================================

Combines 15 signal dimensions from previous passes into a single production-grade
FinalProductionScore for every HighlightCandidate using dynamic, content-type-weighted
profiles.

15 Signal Dimensions
--------------------
1. EditorialReviewScore
2. EditorialQualityScore
3. BoundaryConfidence
4. SemanticCompleteness
5. EditorialCompleteness
6. StandaloneScore
7. EstimatedViewerRetention
8. InformationDensity
9. EmotionScore
10. ViralPotential
11. WhisperConfidence
12. TopicConfidence
13. HookStrength
14. PayoffQuality
15. ContextCompleteness

Dynamic Weight Profiles
-----------------------
Weights are tailored per content_type (`interview`, `tutorial_explainer`, `personal_story`,
`motivation_speech`, `podcast`, `comedy`, `news_update`, `debate_argument`, `solo_monologue`)
and fully configurable from user settings.

Output
------
Writes ``production_scores.json`` to the job's ``temp_dir``.
Returns a list of ``ProductionScore`` instances.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import (
    EditorialReview,
    HighlightCandidate,
    IntentProfile,
    ProductionScore,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Default Dynamic Weight Profiles (per Content Type)
# ---------------------------------------------------------------------------

DEFAULT_WEIGHT_PROFILES: dict[str, dict[str, float]] = {
    "interview": {
        "EditorialReviewScore": 0.12,
        "EditorialQualityScore": 0.08,
        "BoundaryConfidence": 0.08,
        "SemanticCompleteness": 0.08,
        "EditorialCompleteness": 0.06,
        "StandaloneScore": 0.06,
        "EstimatedViewerRetention": 0.06,
        "InformationDensity": 0.04,
        "EmotionScore": 0.04,
        "ViralPotential": 0.06,
        "WhisperConfidence": 0.04,
        "TopicConfidence": 0.04,
        "HookStrength": 0.10,
        "PayoffQuality": 0.10,
        "ContextCompleteness": 0.04,
    },
    "tutorial_explainer": {
        "EditorialReviewScore": 0.10,
        "EditorialQualityScore": 0.08,
        "BoundaryConfidence": 0.06,
        "SemanticCompleteness": 0.10,
        "EditorialCompleteness": 0.08,
        "StandaloneScore": 0.10,
        "EstimatedViewerRetention": 0.06,
        "InformationDensity": 0.14,
        "EmotionScore": 0.02,
        "ViralPotential": 0.04,
        "WhisperConfidence": 0.04,
        "TopicConfidence": 0.04,
        "HookStrength": 0.06,
        "PayoffQuality": 0.04,
        "ContextCompleteness": 0.04,
    },
    "personal_story": {
        "EditorialReviewScore": 0.10,
        "EditorialQualityScore": 0.06,
        "BoundaryConfidence": 0.06,
        "SemanticCompleteness": 0.06,
        "EditorialCompleteness": 0.06,
        "StandaloneScore": 0.06,
        "EstimatedViewerRetention": 0.10,
        "InformationDensity": 0.04,
        "EmotionScore": 0.14,
        "ViralPotential": 0.10,
        "WhisperConfidence": 0.04,
        "TopicConfidence": 0.04,
        "HookStrength": 0.06,
        "PayoffQuality": 0.10,
        "ContextCompleteness": 0.04,
    },
    "motivation_speech": {
        "EditorialReviewScore": 0.10,
        "EditorialQualityScore": 0.06,
        "BoundaryConfidence": 0.06,
        "SemanticCompleteness": 0.04,
        "EditorialCompleteness": 0.04,
        "StandaloneScore": 0.04,
        "EstimatedViewerRetention": 0.10,
        "InformationDensity": 0.04,
        "EmotionScore": 0.14,
        "ViralPotential": 0.08,
        "WhisperConfidence": 0.04,
        "TopicConfidence": 0.04,
        "HookStrength": 0.14,
        "PayoffQuality": 0.10,
        "ContextCompleteness": 0.04,
    },
    "solo_monologue": {
        "EditorialReviewScore": 0.10,
        "EditorialQualityScore": 0.08,
        "BoundaryConfidence": 0.08,
        "SemanticCompleteness": 0.08,
        "EditorialCompleteness": 0.08,
        "StandaloneScore": 0.08,
        "EstimatedViewerRetention": 0.08,
        "InformationDensity": 0.06,
        "EmotionScore": 0.06,
        "ViralPotential": 0.06,
        "WhisperConfidence": 0.04,
        "TopicConfidence": 0.04,
        "HookStrength": 0.08,
        "PayoffQuality": 0.08,
        "ContextCompleteness": 0.04,
    },
}


def run_production_scoring(
    context: dict[str, Any],
    candidates: list[HighlightCandidate] | None = None,
    reviews: list[EditorialReview] | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[ProductionScore]:
    """
    Run Pass 6: calculate multi-dimensional ProductionScore for all candidates.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir`` and ``settings``).
        candidates: Optional list of ``HighlightCandidate`` instances from Pass 4.
        reviews: Optional list of ``EditorialReview`` instances from Pass 5.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of ``ProductionScore`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]
    settings: dict[str, Any] = context.get("settings", {})

    logger.info("Pass 6: Starting Production Scoring Engine...")

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty production score list")
        return []

    # Load reviews if not provided
    if reviews is None:
        reviews = _load_editorial_reviews(temp_dir)

    review_map = {r.candidate_id: r for r in reviews}

    # Determine content_type and weighting profile
    content_type = intent_profile.primary_type if intent_profile else candidates[0].content_type
    weights = _resolve_weighting_profile(content_type, settings)

    production_scores: list[ProductionScore] = []

    for cand in candidates:
        review = review_map.get(cand.candidate_id, EditorialReview(candidate_id=cand.candidate_id))

        # Extract 15 normalized signal values (0.0 to 1.0)
        raw_signals = {
            "EditorialReviewScore": review.editorial_review_score,
            "EditorialQualityScore": getattr(cand, "editorial_quality_score", 0.80),
            "BoundaryConfidence": cand.overall_boundary_confidence,
            "SemanticCompleteness": cand.semantic_completeness,
            "EditorialCompleteness": cand.editorial_completeness,
            "StandaloneScore": round(cand.standalone_score / 5.0, 3),
            "EstimatedViewerRetention": cand.estimated_retention,
            "InformationDensity": round(min(1.0, getattr(cand, "information_density", 80.0) / 120.0), 3),
            "EmotionScore": review.emotional_impact,
            "ViralPotential": review.viral_potential,
            "WhisperConfidence": cand.whisper_confidence.region_avg if hasattr(cand, "whisper_confidence") else 0.95,
            "TopicConfidence": 1.0,
            "HookStrength": review.hook_strength,
            "PayoffQuality": review.payoff_quality,
            "ContextCompleteness": review.context_completeness,
        }

        # Calculate score breakdown and final score
        breakdown: dict[str, dict[str, float]] = {}
        total_score = 0.0

        for dim_name, raw_val in raw_signals.items():
            w = weights.get(dim_name, 0.066)
            contrib = round(raw_val * w, 4)
            total_score += contrib
            breakdown[dim_name] = {
                "raw": round(raw_val, 4),
                "weight": round(w, 4),
                "contribution": contrib,
            }

        final_score = round(max(0.0, min(1.0, total_score)), 4)

        # Attach score to candidate object
        cand.final_production_score = final_score
        cand.score_breakdown = breakdown
        cand.weighting_profile = weights

        p_score = ProductionScore(
            candidate_id=cand.candidate_id,
            final_production_score=final_score,
            score_breakdown=breakdown,
            weighting_profile=weights,
            confidence=0.95,
            content_type=content_type,
            diagnostics={
                "topContributors": _get_top_contributors(breakdown, top_n=3),
                "rejectionFlagsCount": len(review.rejection_reasons),
            },
        )
        production_scores.append(p_score)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 6 complete in %.2fs: calculated production scores for %d candidates", elapsed, len(production_scores))

    # Save production_scores.json to disk
    _write_production_scores(production_scores, temp_dir, elapsed, content_type)

    return production_scores


# ---------------------------------------------------------------------------
# Weight Resolution & Helper Functions
# ---------------------------------------------------------------------------

def _resolve_weighting_profile(content_type: str, settings: dict[str, Any]) -> dict[str, float]:
    """Resolve and normalize 15 dimension weights for the given content_type."""
    custom_weights = settings.get("scoringWeights")
    if custom_weights and isinstance(custom_weights, dict):
        profile = dict(custom_weights)
    else:
        profile = dict(DEFAULT_WEIGHT_PROFILES.get(content_type, DEFAULT_WEIGHT_PROFILES["solo_monologue"]))

    # Normalize weights so sum == 1.0
    total_w = sum(profile.values())
    if total_w > 0:
        normalized = {k: round(v / total_w, 4) for k, v in profile.items()}
    else:
        normalized = {k: 0.0667 for k in profile}

    return normalized


def _get_top_contributors(breakdown: dict[str, dict[str, float]], top_n: int = 3) -> list[str]:
    sorted_dims = sorted(
        breakdown.items(), key=lambda x: x[1].get("contribution", 0.0), reverse=True
    )
    return [f"{name} ({data['contribution']:.4f})" for name, data in sorted_dims[:top_n]]


# ---------------------------------------------------------------------------
# File I/O Helpers
# ---------------------------------------------------------------------------

def _load_highlight_candidates(temp_dir: Path) -> list[HighlightCandidate]:
    path = temp_dir / "highlight_candidates.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            HighlightCandidate(
                candidate_id=c.get("candidateId", c.get("candidate_id", "")),
                segment_id=c.get("segmentId", c.get("segment_id", "")),
                topic_id=c.get("topicId", c.get("topic_id", "")),
                content_type=c.get("contentType", c.get("content_type", "solo_monologue")),
                start=float(c.get("startTime", c.get("start", 0.0))),
                end=float(c.get("endTime", c.get("end", 0.0))),
                duration=float(c.get("clipDuration", c.get("duration", 0.0))),
                overall_boundary_confidence=float(c.get("overallBoundaryConfidence", 0.8)),
                semantic_completeness=float(c.get("semanticCompleteness", 1.0)),
                editorial_completeness=float(c.get("editorialCompleteness", 1.0)),
                standalone_score=int(c.get("standaloneScore", 4)),
                estimated_retention=float(c.get("estimatedRetention", 0.75)),
                viral_patterns=c.get("viralPatterns", []),
                speakers=c.get("speakers", []),
                text=c.get("text", ""),
                editorial_quality_score=float(c.get("editorialQualityScore", 0.80)),
                information_density=float(c.get("informationDensity", 80.0)),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _load_editorial_reviews(temp_dir: Path) -> list[EditorialReview]:
    path = temp_dir / "editorial_review.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            EditorialReview(
                candidate_id=r.get("candidateId", r.get("candidate_id", "")),
                hook_strength=float(r.get("hookStrength", 0.8)),
                curiosity_level=float(r.get("curiosityLevel", 0.8)),
                payoff_quality=float(r.get("payoffQuality", 0.8)),
                standalone_understanding=float(r.get("standaloneUnderstanding", 0.8)),
                context_completeness=float(r.get("contextCompleteness", 0.85)),
                emotional_impact=float(r.get("emotionalImpact", 0.75)),
                information_value=float(r.get("informationValue", 0.80)),
                story_completeness=float(r.get("storyCompleteness", 0.80)),
                conversation_completeness=float(r.get("conversationCompleteness", 0.85)),
                viral_potential=float(r.get("viralPotential", 0.80)),
                replay_value=float(r.get("replayValue", 0.75)),
                shareability=float(r.get("shareability", 0.80)),
                editorial_review_score=float(r.get("editorialReviewScore", 0.82)),
                detailed_reasoning=str(r.get("detailedReasoning", "")),
                rejection_reasons=r.get("rejectionReasons", []),
            )
            for r in data.get("reviews", [])
        ]
    except Exception as exc:
        logger.error("Failed to load editorial_review.json: %s", exc)
        return []


def _write_production_scores(
    scores: list[ProductionScore],
    temp_dir: Path,
    elapsed_sec: float,
    content_type: str,
) -> None:
    score_dicts = [s.to_dict() for s in scores]
    output = {
        "contentType": content_type,
        "scoreCount": len(scores),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "averageProductionScore": round(
                sum(s.final_production_score for s in scores) / max(1, len(scores)), 4
            ),
        },
        "productionScores": score_dicts,
    }
    out_path = temp_dir / "production_scores.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
