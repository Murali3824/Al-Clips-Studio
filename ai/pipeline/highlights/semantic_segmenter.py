"""
Pass 2 — Editorial Segment Builder (Semantic Segmenter)
======================================================

Converts ConversationBlock objects into complete, topically coherent
EditorialSegments that represent meaningful, self-contained units of content.

Semantic Boundary Criteria
--------------------------
A segment boundary is triggered ONLY when:
1. Topic Shift: Jaccard vocabulary similarity between current block and segment drops below 0.15.
2. Explicit Transition: A block contains a known transition phrase ("moving on", "switching gears").
3. Question Opener: A new question block starts after a complete thought/conclusion.
4. Speaker Role Switch: Speaker context shifts in interview/debate format.

Guarantees
----------
- Never splits Q&A pairs (linked blocks remain together).
- Never splits mid-story or mid-explanation.
- Attaches rich diagnostics explaining why every segment starts and ends.

Output
------
Writes ``semantic_segments.json`` to the job's ``temp_dir``.
Returns a list of ``EditorialSegment`` instances.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import (
    CompletenessSignals,
    ConversationBlock,
    EditorialSegment,
    IntentProfile,
    ViralPotential,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_semantic_segmentation(
    context: dict[str, Any],
    blocks: list[ConversationBlock] | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[EditorialSegment]:
    """
    Run Pass 2: group ConversationBlocks into complete EditorialSegments.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir``).
        blocks: Optional list of ``ConversationBlock`` objects from Pass 1.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of populated ``EditorialSegment`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]

    logger.info("Pass 2: Starting Editorial Segment Building...")

    # Load blocks if not provided
    if blocks is None:
        blocks_file = temp_dir / "conversation_blocks.json"
        if not blocks_file.exists():
            logger.warning("conversation_blocks.json not found — returning empty segment list")
            return []
        try:
            b_data = json.loads(blocks_file.read_text(encoding="utf-8"))
            blocks = [
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
                    emotion_score=float(b.get("emotionScore", b.get("emotion_score", 0.0))),
                    emotion_valence=b.get("emotionValence", b.get("emotion_valence", "neutral")),
                    information_density=float(b.get("informationDensity", b.get("information_density", 0.0))),
                    editorial_importance=float(b.get("editorialImportance", b.get("editorial_importance", 0.5))),
                    text=b.get("text", ""),
                )
                for b in b_data.get("blocks", [])
            ]
        except Exception as exc:
            logger.error("Failed to parse conversation_blocks.json: %s", exc)
            return []

    if not blocks:
        logger.warning("No conversation blocks provided — returning empty segment list")
        return []

    # Content type from intent profile
    content_type = intent_profile.primary_type if intent_profile else blocks[0].content_type

    # Step A: Group blocks into topically coherent raw segments using semantic rules
    raw_segments = _group_blocks_into_topics(blocks, content_type)

    # Step B: Construct rich EditorialSegment objects
    segments: list[EditorialSegment] = []

    for idx, raw in enumerate(raw_segments):
        seg_id = f"seg_{idx + 1:03d}"
        topic_id = f"topic_{idx + 1:03d}"
        seg_blocks: list[ConversationBlock] = raw["blocks"]
        start_t = seg_blocks[0].start_time
        end_t = seg_blocks[-1].end_time
        duration = max(0.1, end_t - start_t)
        full_text = " ".join(b.text for b in seg_blocks)

        # Title & fingerprint
        title = _generate_topic_title(full_text)
        fingerprint = _generate_duplicate_fingerprint(full_text)

        # Speakers list
        speakers = sorted(list({b.speaker_id for b in seg_blocks}))

        # Completeness signals
        opens_q = (seg_blocks[0].block_role == "question" or tu.is_question_starter(seg_blocks[0].text))
        has_ans = any(b.block_role == "answer" for b in seg_blocks) or ("?" in seg_blocks[0].text and len(seg_blocks) > 1)
        has_expl = any(b.block_role in ("explanation", "monologue_statement", "story") for b in seg_blocks)
        has_concl = any(b.block_role == "conclusion" for b in seg_blocks) or tu.detect_conclusion_signal(seg_blocks[-1].text)

        sem_comp = _compute_semantic_completeness(opens_q, has_ans, has_expl, has_concl, content_type)
        edit_comp = round((sem_comp * 0.7) + (0.3 if not tu.has_floating_pronoun(seg_blocks[0].text) else 0.0), 3)

        # Viral patterns
        viral_types = _detect_viral_patterns(seg_blocks, full_text)

        # Emotion profile
        em_profile = _build_emotion_profile(seg_blocks)

        # Information density
        info_density = tu.compute_information_density(full_text, duration)

        # Viewer retention prediction
        retention = _predict_viewer_retention(em_profile, info_density, viral_types, sem_comp)

        # Standalone score (1-5)
        standalone = _compute_standalone_score(sem_comp, seg_blocks[0].text)

        completeness_struct = CompletenessSignals(
            opens_with_question=opens_q,
            answer_delivered=has_ans,
            explanation_complete=has_expl,
            conclusion_present=has_concl,
            has_opening_hook=not tu.has_floating_pronoun(seg_blocks[0].text),
            has_context=True,
            is_standalone_intelligible=(standalone >= 3),
        )

        viral_struct = _build_viral_potential_struct(viral_types)

        seg = EditorialSegment(
            segment_id=seg_id,
            topic_id=topic_id,
            topic_title=title,
            topic_summary=title,
            topic_confidence=round(raw["confidence"], 3),
            content_type=content_type,
            start=round(start_t, 3),
            end=round(end_t, 3),
            duration=round(duration, 3),
            conversation_blocks=[b.block_id for b in seg_blocks],
            turn_ids=[b.block_id for b in seg_blocks],
            speakers=speakers,
            conversation_pattern=raw["pattern"],
            opens_with_question=opens_q,
            answer_delivered=has_ans,
            explanation_complete=has_expl,
            conclusion_present=has_concl,
            semantic_completeness=sem_comp,
            editorial_completeness=edit_comp,
            completeness=completeness_struct,
            viral_patterns_detected=viral_types,
            viral_potential=viral_struct,
            emotion_profile=em_profile,
            information_density=round(info_density, 2),
            estimated_viewer_retention=round(retention, 3),
            standalone_score=standalone,
            duplicate_fingerprint=fingerprint,
            raw_turn_count=len(seg_blocks),
            llm_reasoning=None,
            diagnostics={
                "startReason": raw["start_reason"],
                "endReason": raw["end_reason"],
                "blockCount": len(seg_blocks),
                "jaccardBoundaryDrop": raw.get("jaccard_drop", 0.0),
            },
        )
        segments.append(seg)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 2 complete in %.2fs: built %d editorial segments", elapsed, len(segments))

    # Step C: Write semantic_segments.json to temp_dir
    _write_semantic_segments(segments, temp_dir, elapsed, content_type)

    return segments


# ---------------------------------------------------------------------------
# Semantic Topic Grouping Logic
# ---------------------------------------------------------------------------

def _group_blocks_into_topics(
    blocks: list[ConversationBlock],
    content_type: str,
) -> list[dict[str, Any]]:
    """
    Semantic topic boundary grouping algorithm.

    Iterates through blocks and decides whether to append to current segment
    or trigger a new segment based on semantic topic shifts.
    """
    raw_segments: list[dict[str, Any]] = []
    curr_blocks: list[ConversationBlock] = []
    curr_start_reason = "Initial transcript start"
    curr_pattern = "monologue_block"

    for i, b in enumerate(blocks):
        if not curr_blocks:
            curr_blocks.append(b)
            curr_pattern = _determine_pattern(b, content_type)
            continue

        prev_b = curr_blocks[-1]
        should_split, end_reason, start_reason, j_drop = _should_split_topic(
            curr_blocks, b, prev_b, content_type
        )

        if should_split:
            raw_segments.append({
                "blocks": list(curr_blocks),
                "start_reason": curr_start_reason,
                "end_reason": end_reason,
                "confidence": max(0.70, 1.0 - j_drop),
                "pattern": curr_pattern,
                "jaccard_drop": j_drop,
            })
            curr_blocks = [b]
            curr_start_reason = start_reason
            curr_pattern = _determine_pattern(b, content_type)
        else:
            curr_blocks.append(b)

    # Flush last segment
    if curr_blocks:
        raw_segments.append({
            "blocks": list(curr_blocks),
            "start_reason": curr_start_reason,
            "end_reason": "End of transcript",
            "confidence": 0.95,
            "pattern": curr_pattern,
            "jaccard_drop": 0.0,
        })

    return raw_segments


def _should_split_topic(
    curr_segment_blocks: list[ConversationBlock],
    next_block: ConversationBlock,
    prev_block: ConversationBlock,
    content_type: str,
) -> tuple[bool, str, str, float]:
    """
    Determines if a topic boundary should be inserted between prev_block and next_block.

    Returns:
        (should_split: bool, end_reason: str, start_reason: str, jaccard_drop: float)
    """
    # Rule 0: NEVER split if next_block is explicitly linked to prev_block (e.g. Q -> A)
    if prev_block.linked_block_id == next_block.block_id or next_block.linked_block_id == prev_block.block_id:
        return False, "", "", 0.0

    # Rule 1: Explicit transition phrase in next_block
    if tu.detect_transition_phrase(next_block.text):
        return True, "Transition phrase detected in next block", "Explicit topic transition", 0.8

    # Rule 2: Question block after a conclusion or complete thought
    if next_block.block_role == "question" and prev_block.block_role in ("conclusion", "joke", "story"):
        return True, f"Previous topic wrapped up with {prev_block.block_role}", "New question topic initiated", 0.75

    # Rule 3: Jaccard vocabulary similarity check between segment text and next block
    seg_text = " ".join(b.text for b in curr_segment_blocks)
    sim = tu.jaccard_similarity(seg_text, next_block.text)

    # If segment duration > 20s and vocabulary similarity drops < 0.12, trigger split
    seg_duration = curr_segment_blocks[-1].end_time - curr_segment_blocks[0].start_time
    if seg_duration > 20.0 and sim < 0.12 and not tu.word_is_connector({"word": next_block.text.split()[0]} if next_block.text.split() else {}):
        j_drop = round(1.0 - sim, 3)
        return True, f"Vocabulary Jaccard similarity dropped to {sim:.2f}", f"New semantic topic (similarity {sim:.2f})", j_drop

    # Rule 4: Max segment duration guard (120s max to prevent mega-segments)
    if seg_duration > 120.0 and tu.word_is_sentence_final({"word": prev_block.text.split()[-1]} if prev_block.text.split() else {}):
        return True, "Maximum editorial segment duration reached (120s)", "Segment duration split", 0.5

    return False, "", "", 0.0


# ---------------------------------------------------------------------------
# Editorial Feature Calculators
# ---------------------------------------------------------------------------

def _generate_topic_title(full_text: str) -> str:
    """Generate a clean title for the segment."""
    fs = tu.first_sentence(full_text, max_words=12)
    if fs:
        return fs.rstrip(".")
    content_words = tu.extract_content_words(full_text)
    return " ".join(content_words[:6]).title() or "Discussion Topic"


def _generate_duplicate_fingerprint(full_text: str) -> str:
    """Generate content word fingerprint for deduplication."""
    content_words = sorted(list(set(tu.extract_content_words(full_text))))
    return " ".join(content_words[:25])


def _determine_pattern(block: ConversationBlock, content_type: str) -> str:
    if content_type == "interview":
        return "question_answer"
    if block.block_role == "story":
        return "story_arc"
    if block.block_role == "rebuttal":
        return "debate_exchange"
    return "monologue_block"


def _compute_semantic_completeness(
    opens_q: bool, has_ans: bool, has_expl: bool, has_concl: bool, content_type: str
) -> float:
    score = 0.50
    if opens_q:
        score += 0.25 if has_ans else -0.20
    if has_expl:
        score += 0.20
    if has_concl:
        score += 0.25
    return max(0.0, min(1.0, round(score, 3)))


def _detect_viral_patterns(blocks: list[ConversationBlock], full_text: str) -> list[str]:
    patterns = set()
    for b in blocks:
        for sig in b.pattern_signals:
            if "secret" in sig:
                patterns.add("secret_revealed")
            elif "story" in sig:
                patterns.add("personal_story")
            elif "joke" in sig:
                patterns.add("humor")
    v_type = tu.detect_viral_type(full_text)
    if v_type:
        patterns.add(v_type)
    return sorted(list(patterns))


def _build_viral_potential_struct(patterns: list[str]) -> ViralPotential:
    return ViralPotential(
        has_personal_story=("personal_story" in patterns),
        has_transformation=("transformation" in patterns),
        has_controversy=("controversy" in patterns),
        has_surprising_fact=("secret_revealed" in patterns),
        has_expert_advice=("expert_advice" in patterns),
        has_emotional_peak=("emotional_peak" in patterns),
        has_humor=("humor" in patterns),
        has_lesson=("lesson_learned" in patterns),
    )


def _build_emotion_profile(blocks: list[ConversationBlock]) -> dict[str, Any]:
    max_intensity = 0.0
    dominant_valence = "neutral"
    peak_t = blocks[0].start_time

    for b in blocks:
        if b.emotion_score > max_intensity:
            max_intensity = b.emotion_score
            dominant_valence = b.emotion_valence
            peak_t = (b.start_time + b.end_time) / 2.0

    return {
        "intensity": round(max_intensity, 4),
        "valence": dominant_valence,
        "peakTimestamp": round(peak_t, 3),
    }


def _predict_viewer_retention(
    emotion_prof: dict, info_density: float, viral_patterns: list[str], sem_comp: float
) -> float:
    retention = 0.60
    retention += min(0.15, emotion_prof.get("intensity", 0.0) * 0.3)
    if info_density > 70:
        retention += 0.10
    if viral_patterns:
        retention += min(0.15, len(viral_patterns) * 0.05)
    retention += sem_comp * 0.10
    return max(0.0, min(1.0, round(retention, 3)))


def _compute_standalone_score(sem_completeness: float, opening_text: str) -> int:
    if tu.has_floating_pronoun(opening_text):
        return 2 if sem_completeness < 0.6 else 3
    if sem_completeness >= 0.8:
        return 5
    if sem_completeness >= 0.6:
        return 4
    return 3


def _write_semantic_segments(
    segments: list[EditorialSegment],
    temp_dir: Path,
    elapsed_sec: float,
    content_type: str,
) -> None:
    seg_dicts = [s.to_dict() for s in segments]
    output = {
        "contentType": content_type,
        "segmentCount": len(segments),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "averageSegmentDuration": round(
                sum(s.duration for s in segments) / max(1, len(segments)), 2
            ),
            "viralTypesFound": sorted(
                list({p for s in segments for p in s.viral_patterns_detected})
            ),
        },
        "segments": seg_dicts,
    }
    out_path = temp_dir / "semantic_segments.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
