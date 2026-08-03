"""
Pass 3 — Editorial Clip Constructor (Clip Candidate Builder)
============================================================

Transforms EditorialSegments into production-ready HighlightCandidate objects.

Dynamic Semantic Context Expansion
----------------------------------
Context expansion is strictly semantic — never using fixed look-back or look-ahead
windows. Boundaries are expanded until:
- Complete context exists (Question preceding Answer is included)
- Main explanation or story arc concludes
- Setup is paired with its Payoff
- Problem is paired with its Solution

Independent Boundary Confidence
-------------------------------
Calculates `boundary_confidence_start` and `boundary_confidence_end` independently (0.0-1.0).
If overall confidence < 0.70, sets `needs_refinement = True` so Pass 4 (Boundary Refiner)
can iteratively refine the clip boundary.

Output
------
Writes ``highlight_candidates.json`` to the job's ``temp_dir``.
Returns a list of ``HighlightCandidate`` instances.
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
    EditorialSegment,
    HighlightCandidate,
    IntentProfile,
    WhisperConfidenceRegion,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_clip_candidate_building(
    context: dict[str, Any],
    segments: list[EditorialSegment] | None = None,
    blocks: list[ConversationBlock] | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[HighlightCandidate]:
    """
    Run Pass 3: construct production-ready HighlightCandidate objects from EditorialSegments.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir`` and ``settings``).
        segments: Optional list of ``EditorialSegment`` instances from Pass 2.
        blocks: Optional list of ``ConversationBlock`` instances from Pass 1.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of ``HighlightCandidate`` (or ``ClipCandidate``) objects.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]
    settings: dict[str, Any] = context.get("settings", {})

    logger.info("Pass 3: Starting Editorial Clip Construction...")

    # Load transcript words
    words = _load_transcript_words(temp_dir)

    # Load segments if not passed
    if segments is None:
        segments = _load_semantic_segments(temp_dir)

    if not segments:
        logger.warning("No editorial segments found — returning empty candidate list")
        return []

    # Load blocks if not passed
    if blocks is None:
        blocks = _load_conversation_blocks(temp_dir)

    block_map = {b.block_id: b for b in blocks}

    # Minimum and maximum duration settings
    pref_dur = settings.get("preferredDuration", "auto")
    if pref_dur == "short":
        min_dur, max_dur = 15.0, 30.0
    elif pref_dur == "medium":
        min_dur, max_dur = 30.0, 60.0
    elif pref_dur == "long":
        min_dur, max_dur = 60.0, 90.0
    else:  # auto
        min_dur, max_dur = 15.0, 90.0

    candidates: list[HighlightCandidate] = []

    for idx, seg in enumerate(segments):
        cand_id = f"cand_{idx + 1:03d}"
        cand_blocks = [block_map[bid] for bid in seg.conversation_blocks if bid in block_map]

        if not cand_blocks:
            # Fallback if block IDs missing
            start_t, end_t = seg.start, seg.end
        else:
            start_t = cand_blocks[0].start_time
            end_t = cand_blocks[-1].end_time

        orig_start, orig_end = start_t, end_t

        # Step A: Semantic Context Expansion
        exp_start, exp_end, expansion_reason = _apply_semantic_context_expansion(
            seg, cand_blocks, blocks, min_dur, max_dur, words
        )

        # Step B: Word-Level Sentence Boundary Snapping
        if words:
            start_idx = tu.get_nearest_word_index(words, exp_start)
            end_idx = tu.get_nearest_word_index(words, exp_end)

            snapped_start_idx = tu.find_sentence_start(words, start_idx, max_lookback_sec=12.0)
            snapped_end_idx = tu.find_sentence_end(words, end_idx, max_lookahead_sec=12.0)

            final_start = float(words[snapped_start_idx]["start"])
            final_end = float(words[snapped_end_idx]["end"])
            start_word = str(words[snapped_start_idx].get("word", "")).strip()
            end_word = str(words[snapped_end_idx].get("word", "")).strip()
        else:
            final_start, final_end = exp_start, exp_end
            snapped_start_idx, snapped_end_idx = 0, 0
            start_word, end_word = "", ""

        duration = max(0.1, final_end - final_start)
        cand_text = tu.text_in_range(words, final_start, final_end) if words else seg.topic_title

        # Step C: Independent Boundary Confidence Calculation
        conf_start, start_reasons = _compute_boundary_confidence_start(
            final_start, snapped_start_idx, words, cand_text
        )
        conf_end, end_reasons = _compute_boundary_confidence_end(
            final_end, snapped_end_idx, words, seg
        )
        overall_conf = round((conf_start * 0.45) + (conf_end * 0.55), 3)

        needs_refine = (overall_conf < 0.70)

        # Whisper confidence region calculation
        wh_stats = tu.compute_whisper_confidence_region(words, final_start, final_end) if words else {}
        wh_region = WhisperConfidenceRegion(
            start_word_confidence=wh_stats.get("start_word_confidence", 1.0),
            end_word_confidence=wh_stats.get("end_word_confidence", 1.0),
            region_avg=wh_stats.get("region_avg", 1.0),
            low_confidence_word_count=wh_stats.get("low_confidence_word_count", 0),
            low_confidence_at_boundary=wh_stats.get("low_confidence_at_boundary", False),
        )

        # Key moment timestamps
        hook_t = final_start
        payoff_t = final_end - 2.0 if duration > 4.0 else final_end
        expl_start = final_start + 3.0 if duration > 6.0 else final_start
        expl_end = final_end - 4.0 if duration > 8.0 else final_end

        candidate = HighlightCandidate(
            candidate_id=cand_id,
            segment_id=seg.segment_id,
            topic_id=seg.topic_id,
            content_type=seg.content_type,
            start=round(final_start, 3),
            end=round(final_end, 3),
            duration=round(duration, 3),
            original_start=round(orig_start, 3),
            original_end=round(orig_end, 3),
            expanded_start=round(exp_start, 3),
            expanded_end=round(exp_end, 3),
            boundary_confidence_start=round(conf_start, 3),
            boundary_confidence_end=round(conf_end, 3),
            overall_boundary_confidence=overall_conf,
            context_expansion_reason=expansion_reason,
            hook_timestamp=round(hook_t, 3),
            payoff_timestamp=round(payoff_t, 3),
            explanation_start=round(expl_start, 3),
            explanation_end=round(expl_end, 3),
            semantic_completeness=seg.semantic_completeness,
            editorial_completeness=seg.editorial_completeness,
            standalone_score=seg.standalone_score,
            estimated_retention=seg.estimated_viewer_retention,
            viral_patterns=list(seg.viral_patterns_detected),
            speakers=list(seg.speakers),
            duplicate_fingerprint=seg.duplicate_fingerprint,
            llm_reasoning=seg.llm_reasoning,
            needs_refinement=needs_refine,
            long_form=(duration > max_dur and duration <= max_dur * 1.3),
            context_expanded=(exp_start < orig_start or exp_end > orig_end),
            context_expansion_seconds=round((orig_start - exp_start) + (exp_end - orig_end), 3),
            natural_start=(conf_start >= 0.70),
            natural_end=(conf_end >= 0.70),
            start_word=start_word,
            end_word=end_word,
            conversation_pattern=seg.conversation_pattern,
            boundary_confidence=BoundaryConfidence(
                start=conf_start, end=conf_end, overall=overall_conf
            ),
            whisper_confidence=wh_region,
            memory_context={"topicTitle": seg.topic_title},
            text=cand_text,
            speaker_turn_ids=list(seg.conversation_blocks),
            candidate_boundary_warning=needs_refine,
            diagnostics={
                "startChoiceReason": f"Snapped to sentence start ('{start_word}'): {', '.join(start_reasons)}",
                "endChoiceReason": f"Snapped to sentence completion ('{end_word}'): {', '.join(end_reasons)}",
                "contextExpansionReason": expansion_reason,
                "confidenceBreakdown": {
                    "start": round(conf_start, 3),
                    "end": round(conf_end, 3),
                    "overall": overall_conf,
                    "needsRefinement": needs_refine,
                },
            },
        )
        candidates.append(candidate)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 3 complete in %.2fs: constructed %d highlight candidates", elapsed, len(candidates))

    # Save highlight_candidates.json to disk
    _write_highlight_candidates(candidates, temp_dir, elapsed, intent_profile.primary_type if intent_profile else "solo_monologue")

    return candidates


# ---------------------------------------------------------------------------
# Semantic Context Expansion & Boundary Confidence Logic
# ---------------------------------------------------------------------------

def _apply_semantic_context_expansion(
    seg: EditorialSegment,
    cand_blocks: list[ConversationBlock],
    all_blocks: list[ConversationBlock],
    min_dur: float,
    max_dur: float,
    words: list[dict],
) -> tuple[float, float, str]:
    """
    Applies strict semantic rules to expand boundaries.

    Rules:
    1. If first block is an 'answer' and preceding block in all_blocks is its linked 'question':
       expand start backward to include question block.
    2. If first block has a floating pronoun ("He", "This", "It"), expand start backward.
    3. If segment duration < min_dur, expand start backward to preceding block if same topic.
    """
    if not cand_blocks:
        return seg.start, seg.end, "No blocks in segment"

    start_t = cand_blocks[0].start_time
    end_t = cand_blocks[-1].end_time
    reasons = []

    # Find position of first block in all_blocks list
    all_block_ids = [b.block_id for b in all_blocks]
    first_b_id = cand_blocks[0].block_id

    if first_b_id in all_block_ids:
        idx = all_block_ids.index(first_b_id)

        # Rule 1: Include preceding Question if current block is Answer
        if cand_blocks[0].block_role == "answer" and idx > 0:
            prev_b = all_blocks[idx - 1]
            if prev_b.block_role == "question" or prev_b.block_id == cand_blocks[0].linked_block_id:
                start_t = prev_b.start_time
                reasons.append("Expanded start backward to include preceding Question block")

        # Rule 2: Unresolved floating pronoun in opening text
        if tu.has_floating_pronoun(cand_blocks[0].text) and idx > 0:
            prev_b = all_blocks[idx - 1]
            start_t = prev_b.start_time
            reasons.append(f"Expanded start backward to resolve floating pronoun in '{cand_blocks[0].text[:30]}...'")

    # Rule 3: Minimum duration expansion
    if end_t - start_t < min_dur and first_b_id in all_block_ids:
        idx = all_block_ids.index(first_b_id)
        if idx > 0:
            prev_b = all_blocks[idx - 1]
            start_t = prev_b.start_time
            reasons.append("Expanded start backward to reach minimum clip duration")

    expansion_reason = "; ".join(reasons) if reasons else "No semantic expansion required"
    return start_t, end_t, expansion_reason


def _compute_boundary_confidence_start(
    start_t: float, start_idx: int, words: list[dict], text: str
) -> tuple[float, list[str]]:
    reasons = []
    conf = 0.50

    if not words:
        return 0.75, ["No word timing data available"]

    w = words[start_idx]
    w_text = str(w.get("word", "")).strip()

    # Sentence start bonus
    if start_idx == 0 or tu.word_is_sentence_final(words[start_idx - 1]):
        conf += 0.25
        reasons.append("Preceded by sentence end punctuation")

    # Silence gap before start
    gap_before = tu.silence_gap_before(words, start_idx)
    if gap_before >= 0.4:
        conf += 0.20
        reasons.append(f"Preceded by {gap_before:.2f}s silence pause")

    # Check floating pronoun
    if not tu.has_floating_pronoun(text):
        conf += 0.15
        reasons.append("Opening sentence has clear subject (no floating pronoun)")
    else:
        conf -= 0.15
        reasons.append("Opening sentence contains unresolved floating pronoun")

    # Check connector word
    if not tu.word_is_connector(w):
        conf += 0.10
    else:
        conf -= 0.15
        reasons.append(f"Starts on connector word '{w_text}'")

    return max(0.0, min(1.0, conf)), reasons


def _compute_boundary_confidence_end(
    end_t: float, end_idx: int, words: list[dict], seg: EditorialSegment
) -> tuple[float, list[str]]:
    reasons = []
    conf = 0.50

    if not words:
        return 0.75, ["No word timing data available"]

    w = words[end_idx]
    w_text = str(w.get("word", "")).strip()

    # Sentence final punctuation
    if tu.word_is_sentence_final(w):
        conf += 0.30
        reasons.append(f"Ends with final sentence punctuation ('{w_text}')")

    # Silence gap after end
    gap_after = tu.silence_gap_after(words, end_idx)
    if gap_after >= 0.5:
        conf += 0.20
        reasons.append(f"Followed by {gap_after:.2f}s silence pause")

    # Conclusion delivered
    if seg.conclusion_present or seg.explanation_complete:
        conf += 0.15
        reasons.append("Complete thought/conclusion delivered before end")

    # Check connector word at end
    if not tu.word_is_connector(w):
        conf += 0.10
    else:
        conf -= 0.20
        reasons.append(f"Ends on trailing connector word '{w_text}'")

    return max(0.0, min(1.0, conf)), reasons


# ---------------------------------------------------------------------------
# File I/O & Loaders
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


def _load_semantic_segments(temp_dir: Path) -> list[EditorialSegment]:
    path = temp_dir / "semantic_segments.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            EditorialSegment(
                segment_id=s.get("segmentId", s.get("segment_id", "")),
                topic_id=s.get("topicId", s.get("topic_id", "")),
                topic_title=s.get("topicTitle", s.get("topic_title", "")),
                topic_summary=s.get("topicTitle", s.get("topic_summary", "")),
                topic_confidence=float(s.get("topicConfidence", s.get("topic_confidence", 1.0))),
                content_type=s.get("contentType", s.get("content_type", "solo_monologue")),
                start=float(s.get("startTime", s.get("start", 0.0))),
                end=float(s.get("endTime", s.get("end", 0.0))),
                duration=float(s.get("endTime", s.get("end", 0.0))) - float(s.get("startTime", s.get("start", 0.0))),
                conversation_blocks=s.get("conversationBlocks", s.get("conversation_blocks", [])),
                speakers=s.get("speakers", []),
                opens_with_question=bool(s.get("opensWithQuestion", s.get("opens_with_question", False))),
                answer_delivered=bool(s.get("answerDelivered", s.get("answer_delivered", False))),
                explanation_complete=bool(s.get("explanationComplete", s.get("explanation_complete", False))),
                conclusion_present=bool(s.get("conclusionPresent", s.get("conclusion_present", False))),
                semantic_completeness=float(s.get("semanticCompleteness", s.get("semantic_completeness", 1.0))),
                editorial_completeness=float(s.get("editorialCompleteness", s.get("editorial_completeness", 1.0))),
                viral_patterns_detected=s.get("viralPatternsDetected", s.get("viral_patterns_detected", [])),
                emotion_profile=s.get("emotionProfile", s.get("emotion_profile", {})),
                information_density=float(s.get("informationDensity", s.get("information_density", 0.0))),
                estimated_viewer_retention=float(s.get("estimatedViewerRetention", s.get("estimated_viewer_retention", 0.75))),
                standalone_score=int(s.get("standaloneScore", s.get("standalone_score", 4))),
                duplicate_fingerprint=s.get("duplicateFingerprint", s.get("duplicate_fingerprint", "")),
            )
            for s in data.get("segments", [])
        ]
    except Exception as exc:
        logger.error("Failed to load semantic_segments.json: %s", exc)
        return []


def _load_conversation_blocks(temp_dir: Path) -> list[ConversationBlock]:
    path = temp_dir / "conversation_blocks.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [
            ConversationBlock(
                block_id=b.get("blockId", b.get("block_id", "")),
                start_time=float(b.get("startTime", b.get("start_time", 0.0))),
                end_time=float(b.get("endTime", b.get("end_time", 0.0))),
                speaker_id=b.get("speakerId", b.get("speaker_id", "SPEAKER_00")),
                speaker_role=b.get("speakerRole", b.get("speaker_role", "speaker")),
                content_type=b.get("contentType", b.get("content_type", "solo_monologue")),
                block_role=b.get("blockRole", b.get("block_role", "monologue_statement")),
                previous_block_id=b.get("previousBlock", b.get("previous_block_id")),
                next_block_id=b.get("nextBlock", b.get("next_block_id")),
                linked_block_id=b.get("linkedBlock", b.get("linked_block_id")),
                text=b.get("text", ""),
            )
            for b in data.get("blocks", [])
        ]
    except Exception:
        return []


def _write_highlight_candidates(
    candidates: list[HighlightCandidate],
    temp_dir: Path,
    elapsed_sec: float,
    content_type: str,
) -> None:
    cand_dicts = [c.to_dict() for c in candidates]
    output = {
        "contentType": content_type,
        "candidateCount": len(candidates),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "candidatesNeedingRefinement": sum(1 for c in candidates if c.needs_refinement),
            "averageOverallConfidence": round(
                sum(c.overall_boundary_confidence for c in candidates) / max(1, len(candidates)), 3
            ),
        },
        "candidates": cand_dicts,
    }
    out_path = temp_dir / "highlight_candidates.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
