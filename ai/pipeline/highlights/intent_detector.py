"""
Pass 0 — Video Intent Detection
================================

Classifies the video into a content type before any highlight selection
logic runs.  All downstream passes read ``IntentProfile`` and adapt their
editorial rules accordingly.

Content types
-------------
interview           Two or more speakers; host asks questions, guest answers.
solo_monologue      Single speaker addressing the camera continuously.
tutorial_explainer  Step-by-step instructional content with clear structure.
personal_story      Speaker recounts a personal experience with narrative arc.
debate_argument     Opposing viewpoints; claim + counter-claim structure.
comedy              Humour-driven; setup + punchline structure required.
panel_discussion    Three or more speakers with turn-taking.
motivation_speech   Inspirational delivery; emotional climax + call to action.
news_update         Factual reporting; who/what/when/where completeness.

Classification strategy
-----------------------
Step A — Acoustic signals (always runs, no LLM, O(n)):
  Speaker count from diarization.
  Average speech rate (words per minute).
  Silence ratio (silence / total duration).
  Question density (question marks per word).
  Instruction density (imperative verbs per word).
  Narrative markers (personal story indicators).
  Debate markers (contradiction / disagreement phrases).

Step B — Linguistic signals (always runs, no LLM, O(n)):
  Refines the acoustic classification by analysing vocabulary patterns
  across the first and last segments of the transcript.

Step C — LLM refinement (optional, only when provider is available):
  Sends the first and last 2 minutes of transcript to the LLM with a
  lightweight classification prompt.  Result is merged with the heuristic
  classification.  A higher-confidence LLM result overrides the heuristic
  when they disagree.

Fallback
--------
If no diarization data is available, speaker count is estimated from
acoustic signals (long silence gaps between different vocal registers).
The module always produces a complete ``IntentProfile`` — it never raises.

Output
------
Writes ``intent_profile.json`` to the job's ``temp_dir``.
Returns an ``IntentProfile`` dataclass for use by downstream passes.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

from highlights.schemas import AcousticSignals, EditorialRules, IntentProfile
from highlights.llm_provider import LLMProvider, LLMUnavailable
from highlights import text_utils as tu

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Content type definitions + editorial rule factory
# ---------------------------------------------------------------------------

#: All supported content type identifiers.
CONTENT_TYPES: tuple[str, ...] = (
    "interview",
    "solo_monologue",
    "tutorial_explainer",
    "personal_story",
    "debate_argument",
    "comedy",
    "panel_discussion",
    "motivation_speech",
    "news_update",
)

#: Default editorial rules per content type.
_EDITORIAL_RULES: dict[str, dict[str, Any]] = {
    "interview": {
        "require_question": True,
        "require_answer": True,
        "require_conclusion": False,
        "allow_single_speaker_clips": False,
        "min_conversation_turns": 2,
        "preferred_pattern": "question_answer",
        "semantic_lookback_sec": 15.0,   # include question
        "semantic_lookahead_sec": 12.0,  # allow full answer + brief close
    },
    "solo_monologue": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "monologue_block",
        "semantic_lookback_sec": 6.0,
        "semantic_lookahead_sec": 8.0,
    },
    "tutorial_explainer": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "monologue_block",
        "semantic_lookback_sec": 8.0,   # include step opener
        "semantic_lookahead_sec": 10.0,  # include completion marker
    },
    "personal_story": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "story_arc",
        "semantic_lookback_sec": 12.0,  # include scene-setting sentence
        "semantic_lookahead_sec": 10.0,
    },
    "debate_argument": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": False,
        "allow_single_speaker_clips": False,
        "min_conversation_turns": 2,
        "preferred_pattern": "debate_exchange",
        "semantic_lookback_sec": 6.0,
        "semantic_lookahead_sec": 8.0,
    },
    "comedy": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "monologue_block",
        "semantic_lookback_sec": 8.0,   # include setup
        "semantic_lookahead_sec": 3.0,   # stop right after punchline
    },
    "panel_discussion": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": False,
        "allow_single_speaker_clips": False,
        "min_conversation_turns": 2,
        "preferred_pattern": "question_answer",
        "semantic_lookback_sec": 6.0,
        "semantic_lookahead_sec": 8.0,
    },
    "motivation_speech": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "monologue_block",
        "semantic_lookback_sec": 6.0,
        "semantic_lookahead_sec": 10.0,  # include call to action
    },
    "news_update": {
        "require_question": False,
        "require_answer": False,
        "require_conclusion": True,
        "allow_single_speaker_clips": True,
        "min_conversation_turns": 1,
        "preferred_pattern": "monologue_block",
        "semantic_lookback_sec": 4.0,
        "semantic_lookahead_sec": 6.0,
    },
}


def get_editorial_rules(content_type: str) -> EditorialRules:
    """
    Return the ``EditorialRules`` dataclass for ``content_type``.

    Falls back to ``solo_monologue`` rules when ``content_type`` is not
    recognised so the pipeline always has safe defaults.

    Args:
        content_type: One of the supported content type identifiers.

    Returns:
        ``EditorialRules`` instance populated for that type.
    """
    rule_dict = _EDITORIAL_RULES.get(content_type, _EDITORIAL_RULES["solo_monologue"])
    return EditorialRules(**rule_dict)


# ---------------------------------------------------------------------------
# Acoustic signal computation
# ---------------------------------------------------------------------------

def compute_acoustic_signals(
    transcript: dict[str, Any],
    diarization: dict[str, Any] | None,
) -> AcousticSignals:
    """
    Compute raw acoustic and transcript-level signals for intent classification.

    This function runs in O(n) over the word list and requires no external
    models or APIs.

    Args:
        transcript:   Parsed ``transcript.json`` (must have ``words`` and
                      ``segments`` keys).
        diarization:  Parsed ``speaker_diarization.json`` or ``None``.

    Returns:
        ``AcousticSignals`` populated with measured values.
    """
    words: list[dict] = transcript.get("words", [])
    segments: list[dict] = transcript.get("segments", [])
    duration: float = float(transcript.get("duration") or 1.0)

    # --- Speaker count ---
    speaker_count = _estimate_speaker_count(diarization, transcript)
    logger.debug("Speaker count: %d", speaker_count)

    # --- Speech rate (WPM) ---
    speech_rate_wpm = tu.compute_speech_rate_wpm(words, 0.0, duration) if words else 140.0
    logger.debug("Speech rate: %.1f wpm", speech_rate_wpm)

    # --- Silence ratio ---
    silence_ratio = _compute_silence_ratio(words, duration)
    logger.debug("Silence ratio: %.3f", silence_ratio)

    # --- Question density ---
    all_text = " ".join(str(w.get("word", "")) for w in words)
    total_words = max(len(words), 1)
    q_count = tu.count_question_marks(all_text)
    question_density = q_count / total_words
    logger.debug("Question density: %.4f (%d marks / %d words)", question_density, q_count, total_words)

    # --- Instruction density ---
    _INSTRUCTION_VERBS = {
        "do", "don't", "start", "stop", "avoid", "make", "build",
        "use", "try", "follow", "learn", "click", "open", "close",
        "add", "remove", "install", "download", "check", "ensure",
        "remember", "note", "keep", "set", "create", "write",
    }
    word_texts_lower = [str(w.get("word", "")).strip().lower().rstrip(".,!?") for w in words]
    instruction_count = sum(1 for w in word_texts_lower if w in _INSTRUCTION_VERBS)
    instruction_density = instruction_count / total_words
    logger.debug("Instruction density: %.4f", instruction_density)

    # --- Narrative markers (personal story signals) ---
    _NARRATIVE_PHRASES = [
        "i was", "i used to", "i remember", "i had", "i got",
        "it happened", "one day", "growing up", "back then",
        "in those days", "i couldn't believe", "i decided",
        "i realized", "that moment", "years ago",
    ]
    all_text_lower = all_text.lower()
    narrative_count = sum(
        all_text_lower.count(phrase) for phrase in _NARRATIVE_PHRASES
    )
    logger.debug("Narrative markers: %d", narrative_count)

    # --- Debate markers ---
    _DEBATE_PHRASES = [
        "i disagree", "that's wrong", "actually no", "but wait",
        "the problem with that", "that's not true", "incorrect",
        "i challenge", "counter-argument", "on the other hand",
        "however i think", "but you said",
    ]
    debate_count = sum(all_text_lower.count(phrase) for phrase in _DEBATE_PHRASES)
    logger.debug("Debate markers: %d", debate_count)

    return AcousticSignals(
        speaker_count=speaker_count,
        speech_rate_wpm=round(speech_rate_wpm, 1),
        silence_ratio=round(silence_ratio, 4),
        question_density=round(question_density, 5),
        instruction_density=round(instruction_density, 5),
        narrative_markers=narrative_count,
        debate_markers=debate_count,
    )


def _estimate_speaker_count(
    diarization: dict[str, Any] | None,
    transcript: dict[str, Any],
) -> int:
    """
    Estimate the number of speakers.

    Uses diarization data when available.  Falls back to 1 when
    diarization is absent (conservative — better to under-estimate
    than falsely assume an interview format).

    Args:
        diarization: Parsed ``speaker_diarization.json`` or ``None``.
        transcript:  Parsed ``transcript.json`` (for fallback estimation).

    Returns:
        Estimated speaker count (minimum 1).
    """
    if diarization and not diarization.get("skipped", False):
        # pyannote diarization output
        speakers: set[str] = set()
        for turn in diarization.get("turns", []):
            label = turn.get("speaker") or turn.get("label", "")
            if label:
                speakers.add(label)
        if speakers:
            return max(1, len(speakers))

    # Fallback: look for speaker labels in transcript words
    words = transcript.get("words", [])
    speakers_in_transcript: set[str] = set()
    for w in words:
        speaker = w.get("speaker", "")
        if speaker:
            speakers_in_transcript.add(speaker)
    if speakers_in_transcript:
        return max(1, len(speakers_in_transcript))

    return 1  # conservative default


def _compute_silence_ratio(words: list[dict], duration: float) -> float:
    """
    Compute the fraction of the video that is silent.

    Silence = total duration minus the sum of all word audio spans.

    Args:
        words:    Word list with ``start`` and ``end`` timestamps.
        duration: Total video duration in seconds.

    Returns:
        Float 0.0–1.0.
    """
    if not words or duration <= 0:
        return 0.0
    speech_duration = sum(
        max(0.0, float(w.get("end", 0.0)) - float(w.get("start", 0.0)))
        for w in words
    )
    return max(0.0, min(1.0, (duration - speech_duration) / duration))


# ---------------------------------------------------------------------------
# Linguistic signal computation
# ---------------------------------------------------------------------------

def compute_linguistic_signals(
    transcript: dict[str, Any],
) -> dict[str, float]:
    """
    Compute linguistic signals from the transcript text.

    Analyses vocabulary patterns that are strongly predictive of content type
    but require reading the actual words (not just their timing).

    Args:
        transcript: Parsed ``transcript.json``.

    Returns:
        Dict of signal name → signal value.
    """
    segments: list[dict] = transcript.get("segments", [])
    if not segments:
        return {}

    # Analyse first 20% and last 20% of segments for richer signal
    n = len(segments)
    sample_segs = segments[: max(1, n // 5)] + segments[max(0, 4 * n // 5) :]
    sample_text = " ".join(str(s.get("text", "")) for s in sample_segs).lower()
    full_text = " ".join(str(s.get("text", "")) for s in segments).lower()

    signals: dict[str, float] = {}

    # Comedy signal: laughter / explicit humour markers
    _COMEDY = {"haha", "hehe", "lol", "funny", "hilarious", "laugh", "joke"}
    comedy_words = [w for w in full_text.split() if w.rstrip(".,!?") in _COMEDY]
    signals["comedy_density"] = len(comedy_words) / max(len(full_text.split()), 1)

    # Tutorial signal: numbered steps / instructional phrases
    _TUTORIAL = [
        "step one", "step two", "step three", "step 1", "step 2", "step 3",
        "first thing", "second thing", "third thing", "number one", "number two",
        "how to", "in order to", "the process", "you need to",
    ]
    tutorial_hits = sum(full_text.count(p) for p in _TUTORIAL)
    signals["tutorial_density"] = tutorial_hits / max(len(segments), 1)

    # Debate signal: strong contradiction language
    _DEBATE = [
        "you are wrong", "that is incorrect", "i completely disagree",
        "actually that", "but the truth", "the real issue", "let me push back",
    ]
    debate_hits = sum(full_text.count(p) for p in _DEBATE)
    signals["debate_density"] = debate_hits / max(len(segments), 1)

    # News signal: journalistic language
    _NEWS = [
        "according to", "sources say", "officials say", "as of today",
        "breaking news", "reported that", "confirmed that",
    ]
    news_hits = sum(full_text.count(p) for p in _NEWS)
    signals["news_density"] = news_hits / max(len(segments), 1)

    # Motivation signal: inspirational language
    _MOTIVATION = [
        "you can do it", "believe in yourself", "never give up",
        "you are capable", "change your life", "transform your",
        "achieve your", "your potential", "mindset",
    ]
    motivation_hits = sum(full_text.count(p) for p in _MOTIVATION)
    signals["motivation_density"] = motivation_hits / max(len(segments), 1)

    logger.debug("Linguistic signals: %s", signals)
    return signals


# ---------------------------------------------------------------------------
# Heuristic classification
# ---------------------------------------------------------------------------

def classify_intent_heuristic(
    acoustic: AcousticSignals,
    linguistic: dict[str, float],
) -> tuple[str, str | None, float]:
    """
    Classify the video content type using acoustic and linguistic signals alone.

    This function applies a decision-tree-style classification with explicit
    confidence scoring.  It runs in O(1) after signal computation.

    Args:
        acoustic:   Computed ``AcousticSignals``.
        linguistic: Computed linguistic signal dict.

    Returns:
        Tuple of (primary_type, secondary_type, confidence).
    """
    s = acoustic
    lx = linguistic

    # --- Panel discussion: 3+ speakers ---
    if s.speaker_count >= 3:
        secondary = "interview" if s.question_density > 0.02 else None
        confidence = 0.80 + min(0.10, (s.speaker_count - 3) * 0.05)
        logger.info("Classified as panel_discussion (speakers=%d)", s.speaker_count)
        return "panel_discussion", secondary, min(confidence, 0.90)

    # --- Comedy: strong humour density ---
    if lx.get("comedy_density", 0) > 0.015:
        confidence = min(0.90, 0.65 + lx["comedy_density"] * 10)
        logger.info("Classified as comedy (comedy_density=%.4f)", lx.get("comedy_density", 0))
        return "comedy", None, confidence

    # --- Interview: 2 speakers + high question density ---
    if s.speaker_count == 2 and s.question_density > 0.02:
        secondary = "personal_story" if s.narrative_markers > 3 else None
        confidence = 0.75 + min(0.15, s.question_density * 10)
        logger.info(
            "Classified as interview (speakers=2, q_density=%.4f)", s.question_density
        )
        return "interview", secondary, min(confidence, 0.90)

    # --- Debate: 2 speakers + strong debate markers ---
    if s.speaker_count == 2 and s.debate_markers >= 2:
        confidence = min(0.85, 0.65 + s.debate_markers * 0.05)
        logger.info("Classified as debate_argument (debate_markers=%d)", s.debate_markers)
        return "debate_argument", None, confidence

    # --- Tutorial/explainer: high instruction density ---
    if (
        lx.get("tutorial_density", 0) > 0.5
        or s.instruction_density > 0.04
    ):
        secondary = "personal_story" if s.narrative_markers > 2 else None
        confidence = min(0.85, 0.65 + s.instruction_density * 5)
        logger.info(
            "Classified as tutorial_explainer (instruction_density=%.4f)", s.instruction_density
        )
        return "tutorial_explainer", secondary, confidence

    # --- News: journalistic patterns ---
    if lx.get("news_density", 0) > 0.3:
        confidence = min(0.85, 0.65 + lx["news_density"])
        logger.info("Classified as news_update (news_density=%.4f)", lx.get("news_density", 0))
        return "news_update", None, confidence

    # --- Motivation speech: inspirational vocabulary + fast speech ---
    if lx.get("motivation_density", 0) > 0.2 and s.speech_rate_wpm > 150:
        confidence = min(0.80, 0.60 + lx["motivation_density"])
        logger.info("Classified as motivation_speech")
        return "motivation_speech", None, confidence

    # --- Personal story: strong narrative markers, single speaker ---
    if s.speaker_count == 1 and s.narrative_markers >= 5:
        confidence = min(0.80, 0.60 + s.narrative_markers * 0.04)
        logger.info(
            "Classified as personal_story (narrative_markers=%d)", s.narrative_markers
        )
        return "personal_story", None, confidence

    # --- Default: solo monologue ---
    # Low silence ratio = dense continuous speech = monologue
    confidence = 0.55 if s.silence_ratio < 0.15 else 0.50
    logger.info(
        "Classified as solo_monologue (default, silence_ratio=%.3f)", s.silence_ratio
    )
    return "solo_monologue", None, confidence


# ---------------------------------------------------------------------------
# LLM refinement (optional)
# ---------------------------------------------------------------------------

_LLM_INTENT_PROMPT_TEMPLATE = """\
You are analyzing a video transcript to classify its content format.

Read the two excerpts below (opening minutes and closing minutes).
Classify the video into ONE primary type and optionally ONE secondary type.

AVAILABLE TYPES:
  interview | solo_monologue | tutorial_explainer | personal_story |
  debate_argument | comedy | panel_discussion | motivation_speech | news_update

Provide:
  - primaryType: the dominant format
  - secondaryType: a secondary characteristic or null
  - confidence: 0.0-1.0 (how certain you are)
  - keySignals: list of 2-4 specific signals that led to your classification

RESPOND ONLY IN VALID JSON with this exact schema:
{{
  "primaryType": "interview",
  "secondaryType": null,
  "confidence": 0.85,
  "keySignals": ["host asks questions", "guest answers in detail", "two voices alternate"]
}}

TRANSCRIPT — OPENING EXCERPT:
{opening}

TRANSCRIPT — CLOSING EXCERPT:
{closing}
"""

_VALID_LLM_TYPES = set(CONTENT_TYPES)


def _llm_classify_intent(
    transcript: dict[str, Any],
    provider: LLMProvider,
) -> tuple[str, str | None, float] | None:
    """
    Ask the LLM to classify the video content type.

    Sends only the first and last 2 minutes of transcript text to keep
    the request small and focused.  Returns ``None`` on any failure —
    the caller always falls back to heuristic classification.

    Args:
        transcript: Parsed ``transcript.json``.
        provider:   Active ``LLMProvider`` instance.

    Returns:
        ``(primary_type, secondary_type, confidence)`` or ``None``.
    """
    if not provider.is_available():
        logger.debug("LLM unavailable — skipping LLM intent classification")
        return None

    words: list[dict] = transcript.get("words", [])
    duration: float = float(transcript.get("duration") or 0)

    # Extract first 120s and last 120s of transcript text
    opening = tu.text_in_range(words, 0.0, min(120.0, duration / 3))
    closing = tu.text_in_range(words, max(0.0, duration - 120.0), duration)

    if not opening and not closing:
        logger.debug("Empty transcript — skipping LLM intent classification")
        return None

    prompt = _LLM_INTENT_PROMPT_TEMPLATE.format(
        opening=opening[:1500] or "(no opening content)",
        closing=closing[:1500] or "(no closing content)",
    )

    try:
        raw = provider.complete(prompt, temperature=0.2, max_tokens=256)
        result = _parse_llm_intent_response(raw)
        if result:
            logger.info(
                "LLM classified as '%s' (secondary='%s', confidence=%.2f)",
                result[0], result[1], result[2],
            )
        return result
    except Exception as exc:
        logger.warning("LLM intent classification failed: %s", exc)
        return None


def _parse_llm_intent_response(
    raw: str,
) -> tuple[str, str | None, float] | None:
    """
    Parse the LLM's intent classification response.

    Tolerates minor JSON formatting issues (leading/trailing whitespace,
    markdown fences).

    Args:
        raw: Raw string returned by the LLM.

    Returns:
        ``(primary_type, secondary_type, confidence)`` or ``None`` on parse failure.
    """
    import re as _re

    # Strip markdown fences
    cleaned = _re.sub(r"```(?:json)?", "", raw).strip()
    # Find first JSON object
    match = _re.search(r"\{.*\}", cleaned, _re.DOTALL)
    if not match:
        logger.warning("LLM intent response contains no JSON object: %r", raw[:200])
        return None

    try:
        data = json.loads(match.group(0))
    except json.JSONDecodeError as exc:
        logger.warning("LLM intent JSON parse error: %s | raw: %r", exc, raw[:200])
        return None

    primary = str(data.get("primaryType", "")).lower().strip()
    if primary not in _VALID_LLM_TYPES:
        logger.warning("LLM returned unknown primaryType '%s'", primary)
        return None

    secondary_raw = data.get("secondaryType")
    secondary: str | None = None
    if secondary_raw and str(secondary_raw).lower().strip() in _VALID_LLM_TYPES:
        secondary = str(secondary_raw).lower().strip()

    confidence = float(data.get("confidence", 0.5))
    confidence = max(0.0, min(1.0, confidence))

    return primary, secondary, confidence


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_intent_detection(
    context: dict[str, Any],
    provider: LLMProvider,
) -> IntentProfile:
    """
    Run Pass 0: detect video intent and write ``intent_profile.json``.

    This function is designed to be called at the very top of
    ``stage_04_highlights.run()`` before any other processing.  It is
    intentionally fast (< 1s for heuristic path, < 30s with LLM) and
    never raises — it always returns a usable ``IntentProfile``.

    Args:
        context:  Pipeline job context dict (must have ``temp_dir`` and
                  ``settings`` keys).
        provider: Instantiated ``LLMProvider`` for optional LLM refinement.

    Returns:
        ``IntentProfile`` dataclass ready for downstream passes.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]
    settings: dict[str, Any] = context.get("settings", {})

    logger.info("Pass 0: Starting intent detection...")

    # --- Load transcript ---
    transcript_path = temp_dir / "transcript.json"
    try:
        transcript: dict[str, Any] = json.loads(
            transcript_path.read_text(encoding="utf-8")
        )
    except Exception as exc:
        logger.error("Cannot read transcript.json: %s — defaulting to solo_monologue", exc)
        profile = _default_profile()
        _write_profile(profile, temp_dir)
        return profile

    # --- Load diarization (optional) ---
    diarization: dict[str, Any] | None = _load_diarization(temp_dir)

    # --- Step A: Acoustic signals ---
    logger.info("  Step A: Computing acoustic signals...")
    acoustic = compute_acoustic_signals(transcript, diarization)
    _log_acoustic_signals(acoustic)

    # --- Step B: Linguistic signals ---
    logger.info("  Step B: Computing linguistic signals...")
    linguistic = compute_linguistic_signals(transcript)
    _log_linguistic_signals(linguistic)

    # --- Heuristic classification ---
    h_primary, h_secondary, h_confidence = classify_intent_heuristic(acoustic, linguistic)
    logger.info(
        "  Heuristic result: '%s' (secondary='%s', confidence=%.2f)",
        h_primary, h_secondary, h_confidence,
    )

    # --- Step C: Optional LLM refinement ---
    final_primary = h_primary
    final_secondary = h_secondary
    final_confidence = h_confidence
    llm_used = False

    if provider.is_available() and settings.get("useIntentLLM", True):
        logger.info("  Step C: Attempting LLM intent refinement...")
        llm_result = _llm_classify_intent(transcript, provider)
        if llm_result:
            l_primary, l_secondary, l_confidence = llm_result
            # LLM overrides heuristic only when it has meaningfully higher confidence
            if l_confidence >= h_confidence + 0.10:
                logger.info(
                    "  LLM override: '%s' (%.2f) beats heuristic '%s' (%.2f)",
                    l_primary, l_confidence, h_primary, h_confidence,
                )
                final_primary = l_primary
                final_secondary = l_secondary or h_secondary
                final_confidence = l_confidence
                llm_used = True
            else:
                logger.info(
                    "  LLM deferred: heuristic '%s' (%.2f) kept over LLM '%s' (%.2f)",
                    h_primary, h_confidence, l_primary, l_confidence,
                )
                # Adopt LLM secondary if heuristic didn't detect one
                if not final_secondary and l_secondary:
                    final_secondary = l_secondary
    else:
        logger.info("  Step C: LLM refinement skipped (unavailable or disabled)")

    # --- Build editorial rules ---
    rules = get_editorial_rules(final_primary)

    # --- Build IntentProfile ---
    profile = IntentProfile(
        primary_type=final_primary,
        secondary_type=final_secondary,
        confidence=round(final_confidence, 3),
        signals=acoustic,
        editorial_rules=rules,
    )

    elapsed = time.perf_counter() - t_start
    logger.info(
        "Pass 0 complete in %.2fs: '%s' (confidence=%.2f, llm=%s)",
        elapsed, final_primary, final_confidence, llm_used,
    )

    # --- Write intermediate file ---
    _write_profile(profile, temp_dir, elapsed, h_primary, h_confidence, llm_used, linguistic)

    return profile


# ---------------------------------------------------------------------------
# I/O helpers
# ---------------------------------------------------------------------------

def _load_diarization(temp_dir: Path) -> dict[str, Any] | None:
    """Load speaker_diarization.json if it exists and is not marked skipped."""
    path = temp_dir / "speaker_diarization.json"
    if not path.exists():
        logger.debug("speaker_diarization.json not found — single-speaker mode")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if data.get("skipped", False):
            logger.debug("speaker_diarization.json is marked skipped")
            return None
        return data
    except Exception as exc:
        logger.warning("Could not load speaker_diarization.json: %s", exc)
        return None


def _write_profile(
    profile: IntentProfile,
    temp_dir: Path,
    elapsed_sec: float = 0.0,
    heuristic_type: str = "",
    heuristic_confidence: float = 0.0,
    llm_used: bool = False,
    linguistic: dict | None = None,
) -> None:
    """
    Serialise ``IntentProfile`` to ``intent_profile.json``.

    Writes a rich diagnostics object so the intent classification can be
    inspected and debugged without re-running the pipeline.
    """
    import dataclasses as _dc
    output = {
        # Core classification result
        "primaryType": profile.primary_type,
        "secondaryType": profile.secondary_type,
        "confidence": profile.confidence,
        "editorialRules": _dc.asdict(profile.editorial_rules),
        # Diagnostics
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "heuristicType": heuristic_type,
            "heuristicConfidence": round(heuristic_confidence, 3),
            "llmRefinementUsed": llm_used,
            "acousticSignals": _dc.asdict(profile.signals),
            "linguisticSignals": linguistic or {},
        },
    }
    path = temp_dir / "intent_profile.json"
    path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", path)


def _default_profile() -> IntentProfile:
    """Return a safe default ``IntentProfile`` when classification is impossible."""
    return IntentProfile(
        primary_type="solo_monologue",
        secondary_type=None,
        confidence=0.5,
        signals=AcousticSignals(),
        editorial_rules=get_editorial_rules("solo_monologue"),
    )


# ---------------------------------------------------------------------------
# Logging helpers
# ---------------------------------------------------------------------------

def _log_acoustic_signals(s: AcousticSignals) -> None:
    logger.info(
        "  Acoustic: speakers=%d | wpm=%.0f | silence=%.1f%% | "
        "q_density=%.4f | instr_density=%.4f | narrative=%d | debate=%d",
        s.speaker_count,
        s.speech_rate_wpm,
        s.silence_ratio * 100,
        s.question_density,
        s.instruction_density,
        s.narrative_markers,
        s.debate_markers,
    )


def _log_linguistic_signals(lx: dict) -> None:
    if lx:
        logger.info(
            "  Linguistic: comedy=%.4f | tutorial=%.4f | debate=%.4f | "
            "news=%.4f | motivation=%.4f",
            lx.get("comedy_density", 0),
            lx.get("tutorial_density", 0),
            lx.get("debate_density", 0),
            lx.get("news_density", 0),
            lx.get("motivation_density", 0),
        )
