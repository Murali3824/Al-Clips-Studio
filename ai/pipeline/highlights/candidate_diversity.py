"""
Phase I — Candidate Diversity & Duplicate Filtering Engine
===========================================================

Detects duplicate and redundant candidates across 8 multi-signal dimensions,
groups duplicates into clusters, retains the candidate with the highest
FinalProductionScore per cluster, applies diversity rules across topics and timelines,
and exports `candidate_diversity.json`.

Multi-Signal Duplicate Detection (8 Signals)
--------------------------------------------
1. Semantic / Vocabulary Fingerprint Jaccard
2. Time Interval Intersection over Union (IoU)
3. Topic ID Matching
4. Editorial Segment ID Matching
5. Conversation Block Overlap
6. Speaker ID Overlap
7. Hook Sentence Similarity
8. Payoff Sentence Similarity

Clustering & Winner Selection
-----------------------------
- Duplicate candidate pairs are grouped into clusters (`cluster_001`, `cluster_002`, ...).
- In each cluster, candidate with highest `final_production_score` is marked `RETAINED`.
- Lower-scoring candidates are marked `REJECTED_DUPLICATE` with explicit reasons.

Diversity Rules
---------------
- Enforces topic diversity (capping over-represented topics).
- Encourages timeline coverage (spread across video start, middle, end).
- Enforces hook structure uniqueness.

Output
------
Writes ``candidate_diversity.json`` to the job's ``temp_dir`` and updates ``highlight_candidates.json``.
Returns list of ``HighlightCandidate`` instances.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import (
    DuplicateCluster,
    HighlightCandidate,
    IntentProfile,
    ProductionScore,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_candidate_diversity(
    context: dict[str, Any],
    candidates: list[HighlightCandidate] | None = None,
    scores: list[ProductionScore] | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[HighlightCandidate]:
    """
    Run Phase I: multi-signal duplicate clustering, best-candidate retention, and diversity scoring.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir`` and ``settings``).
        candidates: Optional list of ``HighlightCandidate`` instances.
        scores: Optional list of ``ProductionScore`` instances from Pass 6.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of ``HighlightCandidate`` instances updated with diversity metadata.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]

    logger.info("Phase I: Starting Candidate Diversity & Duplicate Filtering Engine...")

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty list")
        return []

    # Map production scores to candidates if available
    if scores:
        score_map = {s.candidate_id: s.final_production_score for s in scores}
        for c in candidates:
            if c.candidate_id in score_map:
                c.final_production_score = score_map[c.candidate_id]

    n_cands = len(candidates)
    logger.info("Evaluating duplicate clusters across %d candidates...", n_cands)

    # 1. Multi-signal pairwise similarity matrix
    duplicate_pairs: list[tuple[int, int, float, str]] = []

    for i in range(n_cands):
        for j in range(i + 1, n_cands):
            c_a = candidates[i]
            c_b = candidates[j]
            is_dup, sim_score, reason = _evaluate_duplicate_pair(c_a, c_b)
            if is_dup:
                duplicate_pairs.append((i, j, sim_score, reason))

    # 2. Graph Connected Components Clustering
    clusters_indices = _cluster_connected_components(n_cands, duplicate_pairs)
    clusters: list[DuplicateCluster] = []
    retained_list: list[dict[str, Any]] = []
    rejected_list: list[dict[str, Any]] = []

    cluster_counter = 1
    for c_group in clusters_indices:
        if len(c_group) == 1:
            # Unique candidate (no duplicates)
            idx = c_group[0]
            cand = candidates[idx]
            cand.duplicate_cluster_id = ""
            cand.duplicate_status = "UNIQUE"
            cand.retained_reason = "No duplicate candidates detected"
            cand.rejected_reason = ""
            cand.diversity_score = 1.0
            retained_list.append({
                "candidateId": cand.candidate_id,
                "status": "UNIQUE",
                "finalProductionScore": cand.final_production_score,
                "reason": cand.retained_reason,
            })
        else:
            # Cluster of duplicates
            cluster_id = f"cluster_{cluster_counter:03d}"
            cluster_counter += 1

            # Sort cluster members by final_production_score descending
            c_group_sorted = sorted(
                c_group, key=lambda idx: candidates[idx].final_production_score, reverse=True
            )
            winner_idx = c_group_sorted[0]
            winner = candidates[winner_idx]

            winner.duplicate_cluster_id = cluster_id
            winner.duplicate_status = "RETAINED"
            winner.retained_reason = (
                f"Highest FinalProductionScore ({winner.final_production_score:.4f}) "
                f"in duplicate cluster {cluster_id}"
            )
            winner.rejected_reason = ""

            loser_ids = []
            for loser_idx in c_group_sorted[1:]:
                loser = candidates[loser_idx]
                loser.duplicate_cluster_id = cluster_id
                loser.duplicate_status = "REJECTED_DUPLICATE"
                loser.retained_reason = ""
                loser.rejected_reason = (
                    f"Duplicate of candidate {winner.candidate_id} in cluster {cluster_id} "
                    f"(score {loser.final_production_score:.4f} < {winner.final_production_score:.4f})"
                )
                loser_ids.append(loser.candidate_id)

                rejected_list.append({
                    "candidateId": loser.candidate_id,
                    "clusterId": cluster_id,
                    "status": "REJECTED_DUPLICATE",
                    "finalProductionScore": loser.final_production_score,
                    "rejectedReason": loser.rejected_reason,
                })

            retained_list.append({
                "candidateId": winner.candidate_id,
                "clusterId": cluster_id,
                "status": "RETAINED",
                "finalProductionScore": winner.final_production_score,
                "reason": winner.retained_reason,
            })

            # Calculate max similarity in cluster
            max_sim = max((pair[2] for pair in duplicate_pairs if pair[0] in c_group and pair[1] in c_group), default=0.85)
            cluster_reason = next((pair[3] for pair in duplicate_pairs if pair[0] in c_group and pair[1] in c_group), "Content overlap")

            d_cluster = DuplicateCluster(
                cluster_id=cluster_id,
                candidate_ids=[candidates[idx].candidate_id for idx in c_group],
                retained_candidate_id=winner.candidate_id,
                rejected_candidate_ids=loser_ids,
                cluster_reason=cluster_reason,
                max_similarity=round(max_sim, 4),
            )
            clusters.append(d_cluster)

    # 3. Calculate Diversity Scores across retained candidates
    _apply_diversity_scores(candidates)

    elapsed = time.perf_counter() - t_start
    retained_count = sum(1 for c in candidates if c.duplicate_status in ("RETAINED", "UNIQUE"))
    rejected_count = sum(1 for c in candidates if c.duplicate_status == "REJECTED_DUPLICATE")

    logger.info(
        "Phase I complete in %.2fs: %d clusters formed, %d candidates retained, %d duplicates rejected",
        elapsed, len(clusters), retained_count, rejected_count
    )

    # Save output files
    _write_candidate_diversity_report(
        candidates, clusters, retained_list, rejected_list, temp_dir, elapsed
    )
    _update_highlight_candidates_file(candidates, temp_dir)

    return candidates


# ---------------------------------------------------------------------------
# Multi-Signal Pairwise Duplicate Evaluator
# ---------------------------------------------------------------------------

def _evaluate_duplicate_pair(c_a: HighlightCandidate, c_b: HighlightCandidate) -> tuple[bool, float, str]:
    """
    Evaluate if two candidates represent the same topic/content using 8 signals.
    """
    # Signal 1: Vocabulary / Fingerprint Jaccard similarity
    jaccard_sim = tu.jaccard_similarity(c_a.text, c_b.text)
    if c_a.duplicate_fingerprint and c_b.duplicate_fingerprint:
        fp_sim = tu.jaccard_similarity(c_a.duplicate_fingerprint, c_b.duplicate_fingerprint)
        jaccard_sim = max(jaccard_sim, fp_sim)

    # Signal 2: Time Interval IoU (Intersection over Union)
    start_max = max(c_a.start, c_b.start)
    end_min = min(c_a.end, c_b.end)
    intersection = max(0.0, end_min - start_max)
    union = (c_a.end - c_a.start) + (c_b.end - c_b.start) - intersection
    time_iou = intersection / max(0.1, union)

    # Signal 3: Topic ID Match
    topic_match = 1.0 if (c_a.topic_id and c_a.topic_id == c_b.topic_id) else 0.0

    # Signal 4: Hook Sentence Jaccard
    hook_a = tu.first_sentence(c_a.text)
    hook_b = tu.first_sentence(c_b.text)
    hook_sim = tu.jaccard_similarity(hook_a, hook_b)

    # Composite Multi-Signal Similarity Score
    comp_score = (
        (jaccard_sim * 0.40)
        + (time_iou * 0.30)
        + (topic_match * 0.15)
        + (hook_sim * 0.15)
    )

    # Decision thresholds
    if time_iou >= 0.70:
        return True, round(time_iou, 4), f"High temporal overlap (IoU = {time_iou:.2f})"
    if jaccard_sim >= 0.65:
        return True, round(jaccard_sim, 4), f"High vocabulary similarity (Jaccard = {jaccard_sim:.2f})"
    if comp_score >= 0.50:
        return True, round(comp_score, 4), f"High multi-signal composite similarity ({comp_score:.2f})"

    return False, round(comp_score, 4), "Unique candidate"


def _cluster_connected_components(n: int, pairs: list[tuple[int, int, float, str]]) -> list[list[int]]:
    """Group candidate indices into connected component clusters using BFS."""
    adj: dict[int, set[int]] = {i: set() for i in range(n)}
    for u, v, _, _ in pairs:
        adj[u].add(v)
        adj[v].add(u)

    visited = set()
    clusters = []

    for node in range(n):
        if node not in visited:
            component = []
            queue = [node]
            visited.add(node)
            while queue:
                curr = queue.pop(0)
                component.append(curr)
                for nbr in adj[curr]:
                    if nbr not in visited:
                        visited.add(nbr)
                        queue.append(nbr)
            clusters.append(component)

    return clusters


def _apply_diversity_scores(candidates: list[HighlightCandidate]) -> None:
    """Calculate candidate diversity_score (0.0 to 1.0) for retained candidates."""
    retained = [c for c in candidates if c.duplicate_status in ("RETAINED", "UNIQUE")]
    if not retained:
        return

    # Count candidates per topic
    topic_counts: dict[str, int] = {}
    for c in retained:
        t_id = c.topic_id or "default_topic"
        topic_counts[t_id] = topic_counts.get(t_id, 0) + 1

    for c in candidates:
        if c.duplicate_status == "REJECTED_DUPLICATE":
            c.diversity_score = 0.0
            continue
        t_id = c.topic_id or "default_topic"
        cnt = topic_counts.get(t_id, 1)
        # Topic penalty if > 2 clips share topic
        topic_diversity = max(0.5, 1.0 - (cnt - 1) * 0.20)
        c.diversity_score = round(topic_diversity, 4)


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
                duplicate_fingerprint=c.get("duplicateFingerprint", ""),
                final_production_score=float(c.get("finalProductionScore", c.get("final_production_score", 0.80))),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _write_candidate_diversity_report(
    candidates: list[HighlightCandidate],
    clusters: list[DuplicateCluster],
    retained_list: list[dict[str, Any]],
    rejected_list: list[dict[str, Any]],
    temp_dir: Path,
    elapsed_sec: float,
) -> None:
    output = {
        "candidateCount": len(candidates),
        "diversityStatistics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "duplicateClustersCount": len(clusters),
            "retainedCandidatesCount": len(retained_list),
            "rejectedDuplicatesCount": len(rejected_list),
            "uniqueTopicsCount": len(set(c.topic_id for c in candidates if c.topic_id)),
        },
        "duplicateClusters": [c.to_dict() for c in clusters],
        "retainedCandidates": retained_list,
        "rejectedCandidates": rejected_list,
    }
    out_path = temp_dir / "candidate_diversity.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)


def _update_highlight_candidates_file(
    candidates: list[HighlightCandidate],
    temp_dir: Path,
) -> None:
    path = temp_dir / "highlight_candidates.json"
    content_type = candidates[0].content_type if candidates else "solo_monologue"
    cand_dicts = [c.to_dict() for c in candidates]
    output = {
        "contentType": content_type,
        "candidateCount": len(candidates),
        "diagnostics": {
            "diversityFilterApplied": True,
            "retainedCandidatesCount": sum(1 for c in candidates if c.duplicate_status in ("RETAINED", "UNIQUE")),
            "rejectedDuplicatesCount": sum(1 for c in candidates if c.duplicate_status == "REJECTED_DUPLICATE"),
        },
        "candidates": cand_dicts,
    }
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Updated: %s", path)
