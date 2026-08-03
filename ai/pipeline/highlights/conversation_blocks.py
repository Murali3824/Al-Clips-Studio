"""
Pass 1 — Conversation Block Detection
=======================================

Groups transcript words into uninterrupted speaker turns and semantic blocks,
attaching rich precomputed metadata to each block so downstream passes operate
on reusable editorial objects.

Conversation Memory
-------------------
Every block carries a ``MemoryWindow`` containing the text of up to two preceding
and two following blocks.  This ensures that when a candidate clip is evaluated,
context (such as the question preceding an answer, or the setup preceding a punchline)
is immediately available without needing to re-parse the raw transcript.

Rich Editorial Metadata
-----------------------
Each block is instantiated as a ``ConversationBlock`` object containing:
- Timestamps, speaker ID, speaker role
- Content type (from Pass 0 IntentProfile)
- Block role (question, answer, explanation, conclusion, rebuttal, hook, story, joke, transition, monologue_statement)
- Precomputed Conversation Memory (prev2, prev1, next1, next2)
- Linked block references (question <-> answer links)
- Emotion intensity & valence
- Information density (unique content words/min)
- Editorial importance score (0.0 - 1.0)
- Low confidence flags & pattern signals

Output
------
Writes ``conversation_blocks.json`` to the job's ``temp_dir``.
Returns a list of ``ConversationBlock`` instances.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import (
    ConversationBlock,
    ConversationTurn,
    IntentProfile,
    MemoryWindow,
)
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Core Block Builder
# ---------------------------------------------------------------------------

def run_conversation_block_detection(
    context: dict[str, Any],
    intent_profile: IntentProfile | None = None,
) -> list[ConversationBlock]:
    """
    Run Pass 1: generate rich editorial ConversationBlock objects.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir``).
        intent_profile: Optional ``IntentProfile`` from Pass 0. If None,
                         loads ``intent_profile.json`` from ``temp_dir``.

    Returns:
        List of populated ``ConversationBlock`` objects.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]

    logger.info("Pass 1: Starting Conversation Block Detection...")

    # Load transcript
    transcript_path = temp_dir / "transcript.json"
    if not transcript_path.exists():
        logger.warning("transcript.json not found — returning empty block list")
        return []

    try:
        transcript: dict[str, Any] = json.loads(transcript_path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Failed to load transcript.json: %s", exc)
        return []

    # Load intent profile if not passed
    if intent_profile is None:
        intent_path = temp_dir / "intent_profile.json"
        if intent_path.exists():
            try:
                ip_data = json.loads(intent_path.read_text(encoding="utf-8"))
                primary_type = ip_data.get("primaryType", "solo_monologue")
            except Exception:
                primary_type = "solo_monologue"
        else:
            primary_type = "solo_monologue"
    else:
        primary_type = intent_profile.primary_type

    # Load diarization (optional)
    diarization = _load_diarization(temp_dir)

    words: list[dict] = transcript.get("words", [])
    segments: list[dict] = transcript.get("segments", [])

    if not words and not segments:
        logger.warning("No words or segments in transcript — returning empty block list")
        return []

    # Step A: Segment words into raw blocks based on speaker changes or speech pauses
    raw_blocks = _segment_raw_blocks(words, segments, diarization)

    # Step B: Determine speaker roles if multi-speaker
    speaker_roles = _assign_speaker_roles(raw_blocks)

    # Step C: Construct rich ConversationBlock objects
    blocks: list[ConversationBlock] = []
    total_blocks = len(raw_blocks)

    for idx, raw in enumerate(raw_blocks):
        b_id = f"block_{idx + 1:03d}"
        text = raw["text"]
        start_t = raw["start"]
        end_t = raw["end"]
        duration = max(0.1, end_t - start_t)
        speaker = raw.get("speaker", "SPEAKER_00")
        s_role = speaker_roles.get(speaker, "solo" if len(speaker_roles) <= 1 else "speaker")

        # Classify block role and extract pattern signals
        b_role, signals = _classify_block_role(text, primary_type, s_role)

        # Emotion & Information density analysis
        e_intensity = tu.detect_emotion_intensity(text)
        e_valence = tu.detect_emotion_valence(text)
        info_density = tu.compute_information_density(text, duration)

        # Calculate Editorial Importance score
        importance = _calculate_editorial_importance(
            text, b_role, e_intensity, info_density, raw["avg_confidence"], primary_type
        )

        block = ConversationBlock(
            block_id=b_id,
            start_time=round(start_t, 3),
            end_time=round(end_t, 3),
            speaker_id=speaker,
            speaker_role=s_role,
            content_type=primary_type,
            block_role=b_role,
            topic_id=None,
            topic_confidence=1.0,
            previous_block_id=f"block_{idx:03d}" if idx > 0 else None,
            next_block_id=f"block_{idx + 2:03d}" if idx < total_blocks - 1 else None,
            linked_block_id=None,  # Populated in Step D
            memory_window=MemoryWindow(),  # Populated in Step D
            semantic_embedding=None,
            emotion_score=round(e_intensity, 4),
            emotion_valence=e_valence,
            information_density=round(info_density, 2),
            editorial_importance=round(importance, 4),
            llm_reasoning=None,
            text=text,
            start_word_idx=raw["start_word_idx"],
            end_word_idx=raw["end_word_idx"],
            avg_whisper_confidence=round(raw["avg_confidence"], 4),
            pattern_signals=signals,
            low_confidence_flag=(raw["avg_confidence"] < 0.70),
        )
        blocks.append(block)

    # Step D: Precompute Memory Windows & Link Q/A or Setup/Punchline blocks
    _populate_memory_and_links(blocks)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 1 complete in %.2fs: created %d editorial conversation blocks", elapsed, len(blocks))

    # Step E: Save conversation_blocks.json to disk
    _write_conversation_blocks(blocks, temp_dir, elapsed, primary_type)

    return blocks


# ---------------------------------------------------------------------------
# Internal Segmentation & Classification Helpers
# ---------------------------------------------------------------------------

def _segment_raw_blocks(
    words: list[dict],
    segments: list[dict],
    diarization: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    """
    Divide word stream into coherent uninterrupted turns/blocks.

    Splits when:
    - Speaker label changes (if diarization is active)
    - Silence gap between words > 1.2 seconds
    - Sentence boundary is reached and turn duration > 15 seconds
    """
    if not words and segments:
        # Fallback to segment-level processing if word timing missing
        raw = []
        for idx, seg in enumerate(segments):
            text = tu.clean_text(str(seg.get("text", "")))
            if not text:
                continue
            raw.append({
                "text": text,
                "start": float(seg.get("start", 0.0)),
                "end": float(seg.get("end", 0.0)),
                "speaker": str(seg.get("speaker", "SPEAKER_00")),
                "start_word_idx": 0,
                "end_word_idx": 0,
                "avg_confidence": 0.95,
            })
        return raw

    blocks = []
    curr_words: list[dict] = []
    curr_speaker = words[0].get("speaker", "SPEAKER_00") if words else "SPEAKER_00"
    start_idx = 0

    for idx, w in enumerate(words):
        w_text = str(w.get("word", "")).strip()
        w_speaker = w.get("speaker", curr_speaker)

        # Check split conditions
        speaker_changed = (w_speaker != curr_speaker and bool(w_speaker))
        pause_gap = tu.silence_gap_before(words, idx)
        long_pause = (pause_gap >= 1.2)

        # Sentence end split for long blocks (> 15s)
        long_block = False
        if curr_words:
            dur = float(w.get("start", 0.0)) - float(curr_words[0].get("start", 0.0))
            if dur > 15.0 and tu.word_is_sentence_final(words[idx - 1]):
                long_block = True

        if curr_words and (speaker_changed or long_pause or long_block):
            # Emit block
            text = tu.clean_text(" ".join(str(x.get("word", "")).strip() for x in curr_words))
            if text:
                confs = [float(x.get("probability", 1.0)) for x in curr_words]
                avg_conf = sum(confs) / len(confs) if confs else 1.0
                blocks.append({
                    "text": text,
                    "start": float(curr_words[0].get("start", 0.0)),
                    "end": float(curr_words[-1].get("end", 0.0)),
                    "speaker": curr_speaker,
                    "start_word_idx": start_idx,
                    "end_word_idx": idx - 1,
                    "avg_confidence": avg_conf,
                })
            curr_words = []
            curr_speaker = w_speaker
            start_idx = idx

        curr_words.append(w)

    # Flush remaining words
    if curr_words:
        text = tu.clean_text(" ".join(str(x.get("word", "")).strip() for x in curr_words))
        if text:
            confs = [float(x.get("probability", 1.0)) for x in curr_words]
            avg_conf = sum(confs) / len(confs) if confs else 1.0
            blocks.append({
                "text": text,
                "start": float(curr_words[0].get("start", 0.0)),
                "end": float(curr_words[-1].get("end", 0.0)),
                "speaker": curr_speaker,
                "start_word_idx": start_idx,
                "end_word_idx": len(words) - 1,
                "avg_confidence": avg_conf,
            })

    return blocks


def _assign_speaker_roles(raw_blocks: list[dict[str, Any]]) -> dict[str, str]:
    """Determine speaker roles (host vs guest vs solo) based on question asking frequency."""
    speaker_counts: dict[str, int] = {}
    speaker_q_counts: dict[str, int] = {}

    for b in raw_blocks:
        spk = b.get("speaker", "SPEAKER_00")
        speaker_counts[spk] = speaker_counts.get(spk, 0) + 1
        if "?" in b["text"] or tu.is_question_starter(b["text"]):
            speaker_q_counts[spk] = speaker_q_counts.get(spk, 0) + 1

    if len(speaker_counts) <= 1:
        return {spk: "solo" for spk in speaker_counts}

    roles = {}
    for spk in speaker_counts:
        q_ratio = speaker_q_counts.get(spk, 0) / max(1, speaker_counts[spk])
        if q_ratio > 0.3:
            roles[spk] = "host"
        else:
            roles[spk] = "guest"
    return roles


def _classify_block_role(
    text: str,
    content_type: str,
    speaker_role: str,
) -> tuple[str, list[str]]:
    """
    Classify editorial role for a block.

    Returns:
        (block_role, pattern_signals)
    """
    signals = []
    text_lower = text.lower()

    if "?" in text or tu.is_question_starter(text):
        signals.append("question_marker")
        return "question", signals

    if tu.detect_conclusion_signal(text):
        signals.append("conclusion_signal")
        return "conclusion", signals

    if tu.detect_transition_phrase(text):
        signals.append("transition_phrase")
        return "transition", signals

    viral_type = tu.detect_viral_type(text)
    if viral_type == "secret_revealed" or "secret" in text_lower:
        signals.append("secret_marker")
        return "explanation", signals

    if viral_type == "personal_story" or "i remember" in text_lower or "when i was" in text_lower:
        signals.append("story_marker")
        return "story", signals

    if viral_type == "humor" or tu.detect_emotion_valence(text) == "humorous":
        signals.append("joke_marker")
        return "joke", signals

    if tu.has_floating_pronoun(text):
        signals.append("has_floating_pronoun")

    if tu.count_exclamation_marks(text) > 0:
        signals.append("exclamation_mark")

    # Default logic by content type
    if content_type == "interview" and speaker_role == "guest":
        return "answer", signals

    return "monologue_statement", signals


def _calculate_editorial_importance(
    text: str,
    role: str,
    emotion: float,
    density: float,
    confidence: float,
    content_type: str,
) -> float:
    """Calculate normalized editorial importance score (0.0 to 1.0)."""
    score = 0.50

    # Role bonuses
    role_weights = {
        "hook": 0.35,
        "question": 0.25,
        "answer": 0.30,
        "conclusion": 0.30,
        "story": 0.25,
        "joke": 0.25,
        "explanation": 0.20,
        "rebuttal": 0.25,
        "transition": -0.15,
        "monologue_statement": 0.05,
    }
    score += role_weights.get(role, 0.0)

    # Emotion bonus (up to +0.15)
    score += emotion * 0.15

    # Density bonus (up to +0.15)
    if density > 100:
        score += 0.15
    elif density > 60:
        score += 0.10

    # Whisper confidence penalty
    if confidence < 0.70:
        score -= 0.20

    return max(0.0, min(1.0, score))


def _populate_memory_and_links(blocks: list[ConversationBlock]) -> None:
    """Populate memoryWindow (Conversation Memory) and link Q/A blocks."""
    n = len(blocks)
    for i, b in enumerate(blocks):
        # Conversation Memory window
        mw = MemoryWindow(
            prev2_text=blocks[i - 2].text if i >= 2 else "",
            prev1_text=blocks[i - 1].text if i >= 1 else "",
            next1_text=blocks[i + 1].text if i < n - 1 else "",
            next2_text=blocks[i + 2].text if i < n - 2 else "",
        )
        b.memory_window = mw

        # Link Question -> Answer
        if b.block_role == "question" and i < n - 1:
            b.linked_block_id = blocks[i + 1].block_id
            if blocks[i + 1].block_role in ("monologue_statement", "answer", "explanation"):
                blocks[i + 1].block_role = "answer"
                blocks[i + 1].linked_block_id = b.block_id


def _load_diarization(temp_dir: Path) -> dict[str, Any] | None:
    path = temp_dir / "speaker_diarization.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return None if data.get("skipped", False) else data
    except Exception:
        return None


def _write_conversation_blocks(
    blocks: list[ConversationBlock],
    temp_dir: Path,
    elapsed_sec: float,
    content_type: str,
) -> None:
    """Save conversation_blocks.json with detailed diagnostics."""
    block_dicts = [b.to_dict() for b in blocks]
    output = {
        "contentType": content_type,
        "blockCount": len(blocks),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "roleDistribution": _compute_role_distribution(blocks),
            "lowConfidenceBlockCount": sum(1 for b in blocks if b.low_confidence_flag),
        },
        "blocks": block_dicts,
    }
    out_path = temp_dir / "conversation_blocks.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)


def _compute_role_distribution(blocks: list[ConversationBlock]) -> dict[str, int]:
    dist: dict[str, int] = {}
    for b in blocks:
        dist[b.block_role] = dist.get(b.block_role, 0) + 1
    return dist
