"""
Phase K — Final Editorial QA Gate (Pass 8)
===========================================

Simulates the review process of a Senior YouTube Shorts Editor on ONLY selected candidates
(``selected == True``).

Validates each selected candidate against an 18-point Production QA Checklist
covering Editorial QA, Technical QA, and Content QA.

Self-Correction & Automatic Repair
-----------------------------------
- If a candidate fails repairable checks (e.g. abrupt ending, mid-sentence cutoff, or boundary confidence),
  allows ONE automatic repair attempt (extending end boundary to complete sentence).
- Re-runs QA once on repaired candidate.
- If it passes after repair: sets status `REPAIRED_AND_PASSED` and approves.
- If it still fails: sets status `REJECTED` with explicit rejection reasons. Never silently approves.

Output
------
Writes ``qa_report.json`` to the job's ``temp_dir``.
Returns list of ``QAReportEntry`` instances.
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
    ProductionScore,
    QAReportEntry,
    RankingCandidate,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_editorial_qa(
    context: dict[str, Any],
    rankings: list[RankingCandidate] | None = None,
    candidates: list[HighlightCandidate] | None = None,
) -> list[QAReportEntry]:
    """
    Run Phase K: validate selected candidates against Production QA Checklist with automatic self-correction.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir``).
        rankings: Optional list of ``RankingCandidate`` instances from Phase J.
        candidates: Optional list of ``HighlightCandidate`` instances.

    Returns:
        List of ``QAReportEntry`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]

    logger.info("Phase K: Starting Final Editorial QA Gate...")

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    # Load rankings if not provided
    if rankings is None:
        rankings = _load_final_rankings(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty QA report list")
        return []

    # Map rankings and reviews for fast lookup
    ranking_map = {r.candidate_id: r for r in rankings}
    cand_map = {c.candidate_id: c for c in candidates}
    reviews_map = {r.candidate_id: r for r in _load_editorial_reviews(temp_dir)}
    words = _load_transcript_words(temp_dir)

    # Determine target clip count from user settings
    settings = context.get("settings", {})
    req_clips = settings.get("clipCount") or settings.get("maxClips") or settings.get("clip_count") or 5
    target_count = int(req_clips)

    # Order evaluation pool by ranking rank ascending
    if rankings:
        ranked_cand_ids = [r.candidate_id for r in sorted(rankings, key=lambda r: r.rank)]
        evaluation_pool = [cand_map[cid] for cid in ranked_cand_ids if cid in cand_map]
    else:
        evaluation_pool = list(candidates)

    logger.info("Evaluating up to %d approved candidates (target %d) from pool of %d candidates...", target_count, target_count, len(evaluation_pool))

    qa_entries: list[QAReportEntry] = []
    approved_count = 0

    for cand in evaluation_pool:
        if approved_count >= target_count:
            break

        review = reviews_map.get(cand.candidate_id, EditorialReview(candidate_id=cand.candidate_id))

        # Initial QA Checklist Validation
        passed, failed, warnings = _evaluate_qa_checklist(cand, review)

        if not failed:
            # Passed cleanly on first attempt
            cand.qa_status = "PASSED"
            cand.final_approval = True
            cand.selected = True
            approved_count += 1
            entry = QAReportEntry(
                candidate_id=cand.candidate_id,
                qa_status="PASSED",
                passed_checks=passed,
                failed_checks=[],
                warnings=warnings,
                rejection_reasons=[],
                final_approval=True,
                reviewer_confidence=0.95,
                qa_diagnostics={
                    "repairAttempted": False,
                    "checksPassedCount": len(passed),
                },
            )
        else:
            # Failed one or more checks — attempt ONE automatic self-correction repair
            logger.info("Candidate %s failed %d checks (%s) — attempting automatic repair...", cand.candidate_id, len(failed), failed)
            repaired_cand, repair_log = _attempt_automatic_repair(cand, words)

            # Re-evaluate QA checklist on repaired candidate
            passed_retry, failed_retry, warnings_retry = _evaluate_qa_checklist(repaired_cand, review)

            if not failed_retry:
                # Repaired and passed!
                cand.start = repaired_cand.start
                cand.end = repaired_cand.end
                cand.duration = repaired_cand.duration
                cand.text = repaired_cand.text
                cand.natural_end = True
                cand.boundary_confidence_end = 0.90
                cand.overall_boundary_confidence = max(0.70, cand.overall_boundary_confidence)
                cand.qa_status = "REPAIRED_AND_PASSED"
                cand.final_approval = True
                cand.selected = True
                approved_count += 1

                entry = QAReportEntry(
                    candidate_id=cand.candidate_id,
                    qa_status="REPAIRED_AND_PASSED",
                    passed_checks=passed_retry,
                    failed_checks=[],
                    warnings=warnings_retry,
                    rejection_reasons=[],
                    final_approval=True,
                    reviewer_confidence=0.90,
                    qa_diagnostics={
                        "repairAttempted": True,
                        "repairAction": repair_log,
                        "checksPassedCount": len(passed_retry),
                    },
                )
            else:
                # Failed QA after repair — reject and continue replenishment to next ranked candidate!
                cand.qa_status = "REJECTED"
                cand.final_approval = False
                cand.selected = False
                entry = QAReportEntry(
                    candidate_id=cand.candidate_id,
                    qa_status="REJECTED",
                    passed_checks=passed_retry,
                    failed_checks=failed_retry,
                    warnings=warnings_retry,
                    rejection_reasons=[f"Failed QA checks after repair: {', '.join(failed_retry)}"],
                    final_approval=False,
                    reviewer_confidence=0.95,
                    qa_diagnostics={
                        "repairAttempted": True,
                        "repairAction": repair_log,
                        "remainingFailures": failed_retry,
                    },
                )

        cand.qa_diagnostics = entry.qa_diagnostics
        qa_entries.append(entry)

    elapsed = time.perf_counter() - t_start
    passed_count = sum(1 for e in qa_entries if e.qa_status == "PASSED")
    repaired_count = sum(1 for e in qa_entries if e.qa_status == "REPAIRED_AND_PASSED")
    rejected_count = sum(1 for e in qa_entries if e.qa_status == "REJECTED")

    logger.info(
        "Phase K complete in %.2fs: %d approved (%d passed, %d repaired), %d rejected",
        elapsed, approved_count, passed_count, repaired_count, rejected_count
    )

    # Write qa_report.json to disk
    _write_qa_report(qa_entries, temp_dir, elapsed)

    return qa_entries


# ---------------------------------------------------------------------------
# 18-Point Production QA Checklist Evaluator
# ---------------------------------------------------------------------------

def _evaluate_qa_checklist(
    cand: HighlightCandidate,
    review: EditorialReview,
) -> tuple[list[str], list[str], list[str]]:
    """
    Evaluate candidate against 18-point Production QA Checklist.
    Returns (passed_checks, failed_checks, warnings).
    """
    passed = []
    failed = []
    warnings = []

    # 1. Editorial QA Checks
    if review.hook_strength >= 0.45:
        passed.append("complete_hook")
    else:
        failed.append("complete_hook")

    if review.standalone_understanding >= 0.40 or cand.standalone_score >= 3:
        passed.append("complete_context")
    else:
        failed.append("complete_context")

    if cand.semantic_completeness >= 0.50:
        passed.append("complete_explanation")
    else:
        failed.append("complete_explanation")

    if review.payoff_quality >= 0.45:
        passed.append("complete_payoff")
    else:
        failed.append("complete_payoff")

    if cand.boundary_confidence_end >= 0.50 and cand.natural_end:
        passed.append("no_abrupt_ending")
    else:
        failed.append("no_abrupt_ending")

    if cand.boundary_confidence_start >= 0.50:
        passed.append("no_abrupt_beginning")
    else:
        failed.append("no_abrupt_beginning")

    if cand.standalone_score >= 3:
        passed.append("standalone_understandable")
    else:
        failed.append("standalone_understandable")

    if review.information_value >= 0.35:
        passed.append("high_viewer_value")
    else:
        warnings.append("low_viewer_value_warning")

    if cand.overall_boundary_confidence >= 0.50:
        passed.append("natural_editorial_flow")
    else:
        failed.append("natural_editorial_flow")

    # 2. Technical QA Checks
    if cand.overall_boundary_confidence >= 0.50:
        passed.append("boundary_confidence_threshold")
    else:
        failed.append("boundary_confidence_threshold")

    if cand.start >= 0.0 and cand.end > cand.start and cand.duration > 0.0:
        passed.append("valid_timestamps")
    else:
        failed.append("valid_timestamps")

    if 10.0 <= cand.duration <= 90.0:
        passed.append("duration_within_limits")
    else:
        failed.append("duration_within_limits")

    if len(cand.text) > 0:
        passed.append("valid_transcript_alignment")
    else:
        failed.append("valid_transcript_alignment")

    if cand.semantic_completeness >= 0.50:
        passed.append("valid_semantic_completeness")
    else:
        failed.append("valid_semantic_completeness")

    # 3. Content QA Checks
    if "incomplete_answer" not in review.rejection_reasons:
        passed.append("no_incomplete_answer")
    else:
        failed.append("no_incomplete_answer")

    if "context_missing" not in review.rejection_reasons:
        passed.append("no_missing_explanation")
    else:
        failed.append("no_missing_explanation")

    if cand.natural_end:
        passed.append("no_mid_sentence_ending")
    else:
        failed.append("no_mid_sentence_ending")

    if review.replay_value >= 0.40:
        passed.append("high_replay_potential")
    else:
        warnings.append("low_replay_warning")

    return passed, failed, warnings


# ---------------------------------------------------------------------------
# Self-Correction Repair Engine
# ---------------------------------------------------------------------------

def _attempt_automatic_repair(
    cand: HighlightCandidate,
    words: list[dict],
) -> tuple[HighlightCandidate, str]:
    """
    Attempt ONE automatic repair on candidate boundaries (e.g. extending end boundary to complete sentence).
    Returns (repaired_candidate, repair_log_string).
    """
    import copy
    repaired = copy.deepcopy(cand)

    if not words:
        return repaired, "No word data available for boundary repair"

    curr_end = repaired.end
    end_idx = tu.get_nearest_word_index(words, curr_end)

    # Repair action: Scan forward up to 8 seconds to find sentence completion
    next_final = tu.find_sentence_end(words, end_idx, max_lookahead_sec=8.0)

    if next_final > end_idx:
        new_end = float(words[next_final]["end"])
        new_text = tu.text_in_range(words, repaired.start, new_end)
        repaired.end = round(new_end, 3)
        repaired.duration = round(new_end - repaired.start, 3)
        repaired.text = new_text
        repaired.natural_end = True
        repaired.boundary_confidence_end = 0.90
        repaired.overall_boundary_confidence = round((repaired.boundary_confidence_start * 0.45) + 0.55 * 0.90, 3)
        return repaired, f"Extended end boundary from {curr_end:.1f}s to {new_end:.1f}s to complete sentence ('{words[next_final].get('word', '')}')"

    return repaired, "No sentence completion boundary found within lookahead window"


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
                boundary_confidence_start=float(c.get("boundaryConfidenceStart", 0.8)),
                boundary_confidence_end=float(c.get("boundaryConfidenceEnd", 0.8)),
                overall_boundary_confidence=float(c.get("overallBoundaryConfidence", 0.8)),
                semantic_completeness=float(c.get("semanticCompleteness", 1.0)),
                editorial_completeness=float(c.get("editorialCompleteness", 1.0)),
                standalone_score=int(c.get("standaloneScore", 4)),
                estimated_retention=float(c.get("estimatedRetention", 0.75)),
                viral_patterns=c.get("viralPatterns", []),
                speakers=c.get("speakers", []),
                text=c.get("text", ""),
                natural_end=bool(c.get("naturalEnd", True)),
                selected=bool(c.get("selected", True)),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _load_final_rankings(temp_dir: Path) -> list[RankingCandidate]:
    path = temp_dir / "final_ranking.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            RankingCandidate(
                rank=int(r.get("rank", 1)),
                candidate_id=r.get("candidateId", r.get("candidate_id", "")),
                ranking_score=float(r.get("rankingScore", 0.85)),
                final_production_score=float(r.get("finalProductionScore", 0.85)),
                diversity_score=float(r.get("diversityScore", 1.0)),
                selected=bool(r.get("selected", True)),
                selection_reason=r.get("selectionReason", ""),
                rejection_reason=r.get("rejectionReason", ""),
            )
            for r in data.get("rankedCandidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load final_ranking.json: %s", exc)
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


def _load_transcript_words(temp_dir: Path) -> list[dict]:
    path = temp_dir / "transcript.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("words", [])
    except Exception:
        return []


def _write_qa_report(
    entries: list[QAReportEntry],
    temp_dir: Path,
    elapsed_sec: float,
) -> None:
    output = {
        "evaluatedCount": len(entries),
        "passedCount": sum(1 for e in entries if e.qa_status == "PASSED"),
        "repairedCount": sum(1 for e in entries if e.qa_status == "REPAIRED_AND_PASSED"),
        "rejectedCount": sum(1 for e in entries if e.qa_status == "REJECTED"),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "finalApprovedCount": sum(1 for e in entries if e.final_approval),
        },
        "qaReports": [e.to_dict() for e in entries],
    }
    out_path = temp_dir / "qa_report.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
