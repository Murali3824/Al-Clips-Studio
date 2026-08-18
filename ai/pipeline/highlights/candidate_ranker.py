"""
Phase J — Final Ranking & Selection Engine (Pass 7)
===================================================

Ranks only RETAINED and UNIQUE candidates (ignoring REJECTED_DUPLICATE candidates),
computes multi-dimensional RankingScores, applies human-editor selection constraints
(max clips, duration limits, timeline diversity, consecutive topic avoidance),
and exports `final_ranking.json`.

Multi-Dimensional RankingScore (10 Dimensions)
-----------------------------------------------
1. FinalProductionScore (0.35)
2. DiversityScore (0.15)
3. EditorialReviewScore (0.10)
4. EditorialQualityScore (0.08)
5. EstimatedViewerRetention (0.08)
6. ViralPotential (0.06)
7. InformationDensity (0.06)
8. StandaloneScore (0.04)
9. SemanticCompleteness (0.04)
10. BoundaryConfidence (0.04)

Selection & Diversity Constraints
---------------------------------
- Enforces `maxClips` target limit (default 5).
- Enforces `maxTotalDurationSec` limit (default 300s).
- Avoids consecutive clips from the same topic.
- Tie-breaking: when scores are within 0.02, prefers the clip that improves overall topic/timeline diversity.

Output
------
Writes ``final_ranking.json`` to the job's ``temp_dir``.
Returns list of ``RankingCandidate`` instances.
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
    RankingCandidate,
)

logger = logging.getLogger(__name__)


# Default Ranking Dimension Weights
DEFAULT_RANKING_WEIGHTS: dict[str, float] = {
    "FinalProductionScore": 0.35,
    "DiversityScore": 0.15,
    "EditorialReviewScore": 0.10,
    "EditorialQualityScore": 0.08,
    "EstimatedViewerRetention": 0.08,
    "ViralPotential": 0.06,
    "InformationDensity": 0.06,
    "StandaloneScore": 0.04,
    "SemanticCompleteness": 0.04,
    "BoundaryConfidence": 0.04,
}


def run_final_ranking(
    context: dict[str, Any],
    candidates: list[HighlightCandidate] | None = None,
    scores: list[ProductionScore] | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[RankingCandidate]:
    """
    Run Phase J: calculate multi-dimensional RankingScores, rank non-duplicate candidates,
    and select optimal production clips.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir`` and ``settings``).
        candidates: Optional list of ``HighlightCandidate`` instances.
        scores: Optional list of ``ProductionScore`` instances from Pass 6.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of ``RankingCandidate`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]
    settings: dict[str, Any] = context.get("settings", {})

    logger.info("Phase J: Starting Final Ranking & Selection Engine...")

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty ranking list")
        return []

    # 1. Filter out REJECTED_DUPLICATE candidates (only rank RETAINED or UNIQUE)
    eligible_candidates = [
        c for c in candidates if getattr(c, "duplicate_status", "UNIQUE") != "REJECTED_DUPLICATE"
    ]

    if not eligible_candidates:
        logger.warning("No eligible non-duplicate candidates found — falling back to all candidates")
        eligible_candidates = candidates

    logger.info("Ranking pool: %d eligible candidates (ignoring duplicate rejections)", len(eligible_candidates))

    # Resolve ranking weights
    weights = _resolve_ranking_weights(settings)

    # 2. Calculate RankingScore for each eligible candidate
    for cand in eligible_candidates:
        _compute_candidate_ranking_score(cand, weights)

    # 3. Sort candidates with tie-breaking for diversity
    ranked_pool = _sort_candidates_with_tie_breaking(eligible_candidates)

    # 4. Selection Constraints (clipCount / maxClips, dynamic maxTotalDuration, topic diversity)
    req_clips = settings.get("clipCount") or settings.get("maxClips") or settings.get("clip_count") or 5
    max_clips = int(req_clips)
    max_clip_dur = float(settings.get("maxClipDuration") or 30.0)
    dynamic_default_duration = max(1200.0, max_clips * max_clip_dur * 2.0)
    max_total_duration = float(settings.get("maxTotalDurationSec", dynamic_default_duration))

    ranking_results: list[RankingCandidate] = []
    selected_count = 0
    accumulated_duration = 0.0
    previous_topic = ""

    for rank_idx, cand in enumerate(ranked_pool, start=1):
        cand.rank = rank_idx
        topic = cand.topic_id or "default_topic"

        # Check selection constraints
        can_select = True
        rejection_reason = ""

        if selected_count >= max_clips:
            can_select = False
            rejection_reason = f"Excluded: max clip count limit reached ({max_clips} clips)"
        elif accumulated_duration + cand.duration > max_total_duration and selected_count > 0:
            can_select = False
            rejection_reason = f"Excluded: total duration limit reached ({accumulated_duration:.1f}s + {cand.duration:.1f}s > {max_total_duration:.1f}s)"
        elif topic == previous_topic and len(ranked_pool) > (max_clips * 2) and selected_count < max_clips:
            # Consecutive topic avoidance penalty only when ample candidate pool exists
            can_select = False
            rejection_reason = f"Excluded: consecutive clip from same topic ('{topic}')"

        if can_select:
            cand.selected = True
            cand.selection_reason = (
                f"Selected at Rank #{rank_idx} with RankingScore={cand.ranking_score:.4f} "
                f"(ProductionScore={cand.final_production_score:.4f}, DiversityScore={cand.diversity_score:.2f})"
            )
            cand.rejection_reason = ""
            selected_count += 1
            accumulated_duration += cand.duration
            previous_topic = topic
        else:
            cand.selected = False
            cand.selection_reason = ""
            cand.rejection_reason = rejection_reason

        rc = RankingCandidate(
            rank=rank_idx,
            candidate_id=cand.candidate_id,
            ranking_score=cand.ranking_score,
            final_production_score=cand.final_production_score,
            diversity_score=cand.diversity_score,
            selected=cand.selected,
            selection_reason=cand.selection_reason,
            rejection_reason=cand.rejection_reason,
            ranking_breakdown=cand.ranking_breakdown if hasattr(cand, "ranking_breakdown") else {},
            diagnostics={
                "startTime": cand.start,
                "endTime": cand.end,
                "duration": cand.duration,
                "topicId": cand.topic_id,
                "boundaryConfidence": cand.overall_boundary_confidence,
            },
        )
        ranking_results.append(rc)

    elapsed = time.perf_counter() - t_start
    logger.info(
        "Phase J complete in %.2fs: ranked %d candidates, selected %d clips (total duration %.1fs)",
        elapsed, len(ranking_results), selected_count, accumulated_duration
    )

    # Save final_ranking.json to disk
    _write_final_ranking_report(ranking_results, temp_dir, elapsed, max_clips, max_total_duration)

    return ranking_results


# ---------------------------------------------------------------------------
# Ranking Score & Tie-Breaking Calculation
# ---------------------------------------------------------------------------

def _resolve_ranking_weights(settings: dict[str, Any]) -> dict[str, float]:
    custom = settings.get("rankingWeights")
    if custom and isinstance(custom, dict):
        profile = dict(custom)
    else:
        profile = dict(DEFAULT_RANKING_WEIGHTS)

    total_w = sum(profile.values())
    if total_w > 0:
        return {k: round(v / total_w, 4) for k, v in profile.items()}
    return {k: 0.10 for k in profile}


def _compute_candidate_ranking_score(cand: HighlightCandidate, weights: dict[str, float]) -> None:
    raw_signals = {
        "FinalProductionScore": getattr(cand, "final_production_score", 0.80),
        "DiversityScore": getattr(cand, "diversity_score", 1.0),
        "EditorialReviewScore": getattr(cand, "editorial_review_score", 0.80),
        "EditorialQualityScore": getattr(cand, "editorial_quality_score", 0.80),
        "EstimatedViewerRetention": cand.estimated_retention,
        "ViralPotential": round(min(1.0, len(cand.viral_patterns) * 0.25 + 0.50), 3),
        "InformationDensity": round(min(1.0, getattr(cand, "information_density", 80.0) / 120.0), 3),
        "StandaloneScore": round(cand.standalone_score / 5.0, 3),
        "SemanticCompleteness": cand.semantic_completeness,
        "BoundaryConfidence": cand.overall_boundary_confidence,
    }

    breakdown: dict[str, dict[str, float]] = {}
    total_score = 0.0

    for dim_name, raw_val in raw_signals.items():
        w = weights.get(dim_name, 0.10)
        contrib = round(raw_val * w, 4)
        total_score += contrib
        breakdown[dim_name] = {
            "raw": round(raw_val, 4),
            "weight": round(w, 4),
            "contribution": contrib,
        }

    cand.ranking_score = round(max(0.0, min(1.0, total_score)), 4)
    cand.ranking_breakdown = breakdown


def _sort_candidates_with_tie_breaking(candidates: list[HighlightCandidate]) -> list[HighlightCandidate]:
    """
    Sort candidates by ranking_score descending.
    Tie-breaking: if scores are within 0.02, prefer the candidate with higher diversity_score.
    """
    def tie_break_key(c: HighlightCandidate) -> tuple[float, float]:
        # Rounded ranking score to 2 decimal places for tie buckets
        score_bucket = round(c.ranking_score, 2)
        return (score_bucket, c.diversity_score, c.ranking_score)

    return sorted(candidates, key=tie_break_key, reverse=True)


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
                duplicate_status=c.get("duplicateStatus", "UNIQUE"),
                diversity_score=float(c.get("diversityScore", 1.0)),
                final_production_score=float(c.get("finalProductionScore", 0.80)),
                editorial_quality_score=float(c.get("editorialQualityScore", 0.80)),
                information_density=float(c.get("informationDensity", 80.0)),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _write_final_ranking_report(
    rankings: list[RankingCandidate],
    temp_dir: Path,
    elapsed_sec: float,
    max_clips: int,
    max_total_duration: float,
) -> None:
    selected_items = [r.to_dict() for r in rankings if r.selected]
    unselected_items = [r.to_dict() for r in rankings if not r.selected]

    output = {
        "rankingCount": len(rankings),
        "selectedCandidatesCount": len(selected_items),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "maxClipsLimit": max_clips,
            "maxTotalDurationSec": max_total_duration,
            "selectedTotalDurationSec": round(sum(r["diagnostics"]["duration"] for r in selected_items), 1),
            "averageRankingScore": round(
                sum(r.ranking_score for r in rankings) / max(1, len(rankings)), 4
            ),
        },
        "rankedCandidates": [r.to_dict() for r in rankings],
    }
    out_path = temp_dir / "final_ranking.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
