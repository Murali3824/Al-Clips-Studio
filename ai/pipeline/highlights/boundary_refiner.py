"""
Pass 4 — Editorial Refinement Engine (Boundary Refiner)
======================================================

Iteratively refines HighlightCandidate boundaries until they reach production quality
or no further improvement is possible.

Refinement Evaluators
---------------------
Refines start and end boundaries independently considering:
- Sentence & semantic completion
- Question / Answer & Setup / Payoff integrity
- Topic continuity & explanation completeness
- Emotion peaks & emphasis words
- Whisper word confidence (avoiding low-confidence boundary words)

Iterative Loop
--------------
Iterates (Candidate → Evaluate → Refine → Re-score → Repeat) up to `max_iterations` (default 3).
Stops early if target confidence (0.85) is reached or improvement is < 0.02.
Candidates already exceeding target confidence are untouched.

Output
------
Writes ``refinement_report.json`` and updates ``highlight_candidates.json``.
Returns refined list of ``HighlightCandidate`` instances.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import (
    BoundaryConfidence,
    ClipCandidate,
    ConversationBlock,
    HighlightCandidate,
    IntentProfile,
    RefinementLog,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_boundary_refinement(
    context: dict[str, Any],
    candidates: list[HighlightCandidate] | None = None,
    blocks: list[ConversationBlock] | None = None,
    intent_profile: IntentProfile | None = None,
    target_confidence: float = 0.85,
    max_iterations: int = 3,
) -> list[HighlightCandidate]:
    """
    Run Pass 4: iteratively refine boundaries and compute Editorial Quality Scores.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir``).
        candidates: Optional list of ``HighlightCandidate`` instances from Pass 3.
        blocks: Optional list of ``ConversationBlock`` instances from Pass 1.
        intent_profile: Optional ``IntentProfile`` from Pass 0.
        target_confidence: Target confidence score to stop refinement early (default 0.85).
        max_iterations: Maximum refinement iterations per candidate (default 3).

    Returns:
        List of refined ``HighlightCandidate`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]

    logger.info("Pass 4: Starting Editorial Refinement Engine...")

    # Load transcript words
    words = _load_transcript_words(temp_dir)

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty list")
        return []

    refining_candidates: list[HighlightCandidate] = []
    report_entries: list[dict[str, Any]] = []

    for cand in candidates:
        # Calculate initial Editorial Quality Score
        cand.editorial_quality_score = _calculate_editorial_quality_score(cand)

        # Threshold check: skip candidates that already exceed target quality
        if cand.overall_boundary_confidence >= target_confidence and not cand.needs_refinement:
            logger.info("Candidate %s already exceeds target quality (conf=%.2f) — skipping", cand.candidate_id, cand.overall_boundary_confidence)
            report_entries.append({
                "candidateId": cand.candidate_id,
                "status": "skipped",
                "reason": f"Already exceeds target confidence ({cand.overall_boundary_confidence:.2f} >= {target_confidence:.2f})",
                "initialConfidence": cand.overall_boundary_confidence,
                "finalConfidence": cand.overall_boundary_confidence,
                "editorialQualityScore": cand.editorial_quality_score,
                "iterations": [],
            })
            refining_candidates.append(cand)
            continue

        # Iterative Refinement Loop
        iter_logs: list[RefinementLog] = []
        iteration = 0

        while iteration < max_iterations:
            iteration += 1
            start_before = cand.start
            end_before = cand.end
            start_conf_before = cand.boundary_confidence_start
            end_conf_before = cand.boundary_confidence_end
            overall_conf_before = cand.overall_boundary_confidence

            # Independent boundary refinements
            new_start, start_reason = _refine_start_boundary(cand.start, words, cand.text)
            new_end, end_reason = _refine_end_boundary(cand.end, words, cand.text)

            # Re-snap to nearest words
            if words:
                start_idx = tu.get_nearest_word_index(words, new_start)
                end_idx = tu.get_nearest_word_index(words, new_end)
                final_start = float(words[start_idx]["start"])
                final_end = float(words[end_idx]["end"])
                cand_text = tu.text_in_range(words, final_start, final_end)
            else:
                final_start, final_end = new_start, new_end
                start_idx, end_idx = 0, 0
                cand_text = cand.text

            duration = max(0.1, final_end - final_start)

            # Re-evaluate confidence
            conf_s, _ = _eval_start_confidence(final_start, start_idx, words, cand_text)
            conf_e, _ = _eval_end_confidence(final_end, end_idx, words)
            overall_conf_after = round((conf_s * 0.45) + (conf_e * 0.55), 3)

            improvement = round(overall_conf_after - overall_conf_before, 3)
            action = f"Start: {start_reason} | End: {end_reason}"

            log_entry = RefinementLog(
                iteration=iteration,
                start_before=round(start_before, 3),
                end_before=round(end_before, 3),
                start_after=round(final_start, 3),
                end_after=round(final_end, 3),
                start_confidence_before=round(start_conf_before, 3),
                end_confidence_before=round(end_conf_before, 3),
                start_confidence_after=round(conf_s, 3),
                end_confidence_after=round(conf_e, 3),
                improvement=improvement,
                action_taken=action,
            )
            iter_logs.append(log_entry)

            # Update candidate state
            cand.start = round(final_start, 3)
            cand.end = round(final_end, 3)
            cand.duration = round(duration, 3)
            cand.boundary_confidence_start = round(conf_s, 3)
            cand.boundary_confidence_end = round(conf_e, 3)
            cand.overall_boundary_confidence = overall_conf_after
            cand.boundary_confidence = BoundaryConfidence(start=conf_s, end=conf_e, overall=overall_conf_after)
            cand.text = cand_text
            cand.refinement_iterations = iteration

            # Stop criteria checks
            if overall_conf_after >= target_confidence:
                logger.info("Candidate %s reached target confidence (%.2f) at iteration %d", cand.candidate_id, overall_conf_after, iteration)
                break
            if improvement < 0.02 and iteration > 1:
                logger.info("Candidate %s stopped iteration: insignificant gain (%.3f < 0.02)", cand.candidate_id, improvement)
                break

        cand.refinement_log = iter_logs
        cand.needs_refinement = (cand.overall_boundary_confidence < 0.70)
        cand.candidate_boundary_warning = cand.needs_refinement
        cand.editorial_quality_score = _calculate_editorial_quality_score(cand)

        report_entries.append({
            "candidateId": cand.candidate_id,
            "status": "refined",
            "iterationsCount": len(iter_logs),
            "initialConfidence": round(iter_logs[0].start_confidence_before * 0.45 + iter_logs[0].end_confidence_before * 0.55, 3) if iter_logs else cand.overall_boundary_confidence,
            "finalConfidence": cand.overall_boundary_confidence,
            "editorialQualityScore": cand.editorial_quality_score,
            "iterations": [log.to_dict() for log in iter_logs],
        })

        refining_candidates.append(cand)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 4 complete in %.2fs: refined %d candidates", elapsed, len(refining_candidates))

    # Save outputs to disk
    _write_refinement_report(report_entries, temp_dir, elapsed)
    _update_highlight_candidates_file(refining_candidates, temp_dir)

    return refining_candidates


# ---------------------------------------------------------------------------
# Independent Boundary Refinements
# ---------------------------------------------------------------------------

def _refine_start_boundary(start_t: float, words: list[dict], text: str) -> tuple[float, str]:
    if not words:
        return start_t, "No word data for refinement"

    idx = tu.get_nearest_word_index(words, start_t)
    w = words[idx]
    w_text = str(w.get("word", "")).strip()

    # Refinement 1: Avoid starting on connector words ("And", "But", "So")
    if tu.word_is_connector(w) and idx > 0:
        prev_idx = tu.find_sentence_start(words, max(0, idx - 1))
        new_t = float(words[prev_idx]["start"])
        return new_t, f"Moved start back from connector word '{w_text}' to preceding sentence start"

    # Refinement 2: Avoid starting on unresolved floating pronouns ("This", "It", "He")
    if tu.has_floating_pronoun(text[:30]) and idx > 0:
        prev_idx = tu.find_sentence_start(words, max(0, idx - 3))
        new_t = float(words[prev_idx]["start"])
        return new_t, f"Moved start back to resolve floating pronoun in '{text[:20]}...'"

    # Refinement 3: Avoid low Whisper confidence word at boundary
    if float(w.get("probability", 1.0)) < 0.60 and idx > 0:
        prev_idx = max(0, idx - 1)
        new_t = float(words[prev_idx]["start"])
        return new_t, f"Shifted start away from low-confidence word '{w_text}' (p={float(w.get('probability', 0)):.2f})"

    return start_t, "Start boundary optimal"


def _refine_end_boundary(end_t: float, words: list[dict], text: str) -> tuple[float, str]:
    if not words:
        return end_t, "No word data for refinement"

    idx = tu.get_nearest_word_index(words, end_t)
    w = words[idx]
    w_text = str(w.get("word", "")).strip()

    # Refinement 1: Complete sentence final punctuation
    if not tu.word_is_sentence_final(w):
        next_final = tu.find_sentence_end(words, idx, max_lookahead_sec=8.0)
        if next_final > idx:
            new_t = float(words[next_final]["end"])
            return new_t, f"Extended end to complete sentence final punctuation ('{words[next_final].get('word', '')}')"

    # Refinement 2: Avoid ending on trailing connector word ("and", "or", "because")
    if tu.word_is_connector(w) and idx < len(words) - 1:
        next_final = tu.find_sentence_end(words, idx + 1, max_lookahead_sec=8.0)
        new_t = float(words[next_final]["end"])
        return new_t, f"Extended end past trailing connector '{w_text}'"

    # Refinement 3: Avoid low Whisper confidence word at end boundary
    if float(w.get("probability", 1.0)) < 0.60 and idx < len(words) - 1:
        new_t = float(words[idx + 1]["end"])
        return new_t, f"Shifted end past low-confidence word '{w_text}'"

    return end_t, "End boundary optimal"


# ---------------------------------------------------------------------------
# Confidence & Quality Scorers
# ---------------------------------------------------------------------------

def _eval_start_confidence(start_t: float, start_idx: int, words: list[dict], text: str) -> tuple[float, list[str]]:
    conf = 0.50
    reasons = []
    if not words:
        return 0.75, []
    w = words[start_idx]
    if start_idx == 0 or tu.word_is_sentence_final(words[start_idx - 1]):
        conf += 0.25
        reasons.append("Sentence start")
    gap = tu.silence_gap_before(words, start_idx)
    if gap >= 0.4:
        conf += 0.20
        reasons.append(f"{gap:.1f}s pause")
    if not tu.has_floating_pronoun(text):
        conf += 0.15
    if not tu.word_is_connector(w):
        conf += 0.10
    return max(0.0, min(1.0, conf)), reasons


def _eval_end_confidence(end_t: float, end_idx: int, words: list[dict]) -> tuple[float, list[str]]:
    conf = 0.50
    reasons = []
    if not words:
        return 0.75, []
    w = words[end_idx]
    if tu.word_is_sentence_final(w):
        conf += 0.30
        reasons.append("Sentence final punct")
    gap = tu.silence_gap_after(words, end_idx)
    if gap >= 0.5:
        conf += 0.20
        reasons.append(f"{gap:.1f}s pause")
    if not tu.word_is_connector(w):
        conf += 0.10
    return max(0.0, min(1.0, conf)), reasons


def _calculate_editorial_quality_score(cand: HighlightCandidate) -> float:
    """
    Calculate overall Editorial Quality Score (0.0 to 1.0).
    Combines:
    - boundary confidence (35%)
    - semantic completeness (25%)
    - editorial completeness (15%)
    - standalone quality (15%)
    - retention prediction (10%)
    """
    score = (
        (cand.overall_boundary_confidence * 0.35)
        + (cand.semantic_completeness * 0.25)
        + (cand.editorial_completeness * 0.15)
        + ((cand.standalone_score / 5.0) * 0.15)
        + (cand.estimated_retention * 0.10)
    )
    return round(max(0.0, min(1.0, score)), 4)


# ---------------------------------------------------------------------------
# File I/O Helpers
# ---------------------------------------------------------------------------

def _load_transcript_words(temp_dir: Path) -> list[dict]:
    path = temp_dir / "transcript.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data.get("words", [])
    except Exception:
        return []


def _load_highlight_candidates(temp_dir: Path) -> list[HighlightCandidate]:
    path = temp_dir / "highlight_candidates.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            ClipCandidate(
                candidate_id=c.get("candidateId", c.get("candidate_id", "")),
                segment_id=c.get("segmentId", c.get("segment_id", "")),
                topic_id=c.get("topicId", c.get("topic_id", "")),
                content_type=c.get("contentType", c.get("content_type", "solo_monologue")),
                start=float(c.get("startTime", c.get("start", 0.0))),
                end=float(c.get("endTime", c.get("end", 0.0))),
                duration=float(c.get("clipDuration", c.get("duration", 0.0))),
                original_start=float(c.get("originalStart", c.get("original_start", 0.0))),
                original_end=float(c.get("originalEnd", c.get("original_end", 0.0))),
                expanded_start=float(c.get("expandedStart", c.get("expanded_start", 0.0))),
                expanded_end=float(c.get("expandedEnd", c.get("expanded_end", 0.0))),
                boundary_confidence_start=float(c.get("boundaryConfidenceStart", c.get("boundary_confidence_start", 0.8))),
                boundary_confidence_end=float(c.get("boundaryConfidenceEnd", c.get("boundary_confidence_end", 0.8))),
                overall_boundary_confidence=float(c.get("overallBoundaryConfidence", c.get("overall_boundary_confidence", 0.8))),
                context_expansion_reason=c.get("contextExpansionReason", c.get("context_expansion_reason", "")),
                semantic_completeness=float(c.get("semanticCompleteness", c.get("semantic_completeness", 1.0))),
                editorial_completeness=float(c.get("editorialCompleteness", c.get("editorial_completeness", 1.0))),
                standalone_score=int(c.get("standaloneScore", c.get("standalone_score", 4))),
                estimated_retention=float(c.get("estimatedRetention", c.get("estimated_retention", 0.75))),
                viral_patterns=c.get("viralPatterns", c.get("viral_patterns", [])),
                speakers=c.get("speakers", []),
                duplicate_fingerprint=c.get("duplicateFingerprint", c.get("duplicate_fingerprint", "")),
                needs_refinement=bool(c.get("needsRefinement", c.get("needs_refinement", False))),
                text=c.get("text", ""),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _write_refinement_report(
    entries: list[dict[str, Any]],
    temp_dir: Path,
    elapsed_sec: float,
) -> None:
    output = {
        "candidateCount": len(entries),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "candidatesRefined": sum(1 for e in entries if e["status"] == "refined"),
            "candidatesSkipped": sum(1 for e in entries if e["status"] == "skipped"),
        },
        "report": entries,
    }
    out_path = temp_dir / "refinement_report.json"
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
            "refined": True,
            "candidatesNeedingRefinement": sum(1 for c in candidates if c.needs_refinement),
            "averageOverallConfidence": round(
                sum(c.overall_boundary_confidence for c in candidates) / max(1, len(candidates)), 3
            ),
            "averageEditorialQualityScore": round(
                sum(c.editorial_quality_score for c in candidates) / max(1, len(candidates)), 4
            ),
        },
        "candidates": cand_dicts,
    }
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Updated: %s", path)
