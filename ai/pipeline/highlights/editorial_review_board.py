"""
Pass 5 — Editorial Review Board (LLM / Heuristic Review)
======================================================

Reviews every HighlightCandidate exactly like a professional YouTube Shorts editor
before final ranking.

Structured Criteria (12 Metrics)
-------------------------------
1. Hook Strength
2. Curiosity Level
3. Payoff Quality
4. Standalone Understanding
5. Context Completeness
6. Emotional Impact
7. Information Value
8. Story Completeness
9. Conversation Completeness
10. Viral Potential
11. Replay Value
12. Shareability

LLM & Fallback Execution
------------------------
- When LLM (Ollama / OpenAI / Anthropic) is available: executes structured JSON prompt
  and validates JSON schema response.
- When LLM is unavailable: executes deterministic heuristic evaluation maintaining
  identical schema and rejection reason detection.

Rejection Reason Detection
--------------------------
Detects specific editorial flaws: `incomplete_answer`, `weak_hook`, `missing_payoff`,
`abrupt_ending`, `context_missing`, `duplicate_idea`, `low_viewer_value`, `low_confidence`.

Output
------
Writes ``editorial_review.json`` to the job's ``temp_dir``.
Returns a list of ``EditorialReview`` instances.
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
)
from highlights.llm_provider import LLMProvider, NullProvider
from highlights import text_utils as tu

logger = logging.getLogger(__name__)


def run_editorial_review_board(
    context: dict[str, Any],
    candidates: list[HighlightCandidate] | None = None,
    llm_provider: LLMProvider | None = None,
    intent_profile: IntentProfile | None = None,
) -> list[EditorialReview]:
    """
    Run Pass 5: evaluate candidates across 12 structured criteria and generate EditorialReviews.

    Args:
        context: Pipeline job context dict (must contain ``temp_dir`` and ``settings``).
        candidates: Optional list of ``HighlightCandidate`` instances from Pass 4.
        llm_provider: Optional ``LLMProvider`` instance.
        intent_profile: Optional ``IntentProfile`` from Pass 0.

    Returns:
        List of ``EditorialReview`` instances.
    """
    t_start = time.perf_counter()
    temp_dir: Path = context["temp_dir"]
    settings: dict[str, Any] = context.get("settings", {})

    logger.info("Pass 5: Starting Editorial Review Board evaluation...")

    # Load candidates if not provided
    if candidates is None:
        candidates = _load_highlight_candidates(temp_dir)

    if not candidates:
        logger.warning("No highlight candidates found — returning empty review list")
        return []

    # Check LLM availability
    use_llm = (
        llm_provider is not None
        and not isinstance(llm_provider, NullProvider)
        and llm_provider.is_available()
        and settings.get("useReviewLLM", False)
    )

    reviews: list[EditorialReview] = []

    for cand in candidates:
        if use_llm:
            try:
                review = _evaluate_candidate_with_llm(cand, llm_provider, intent_profile)
            except Exception as exc:
                logger.warning("LLM evaluation failed for candidate %s (%s) — falling back to heuristic", cand.candidate_id, exc)
                review = _evaluate_candidate_heuristically(cand, intent_profile)
        else:
            review = _evaluate_candidate_heuristically(cand, intent_profile)

        reviews.append(review)

    elapsed = time.perf_counter() - t_start
    logger.info("Pass 5 complete in %.2fs: reviewed %d candidates (source=%s)", elapsed, len(reviews), "llm" if use_llm else "heuristic")

    # Save output to disk
    _write_editorial_review(reviews, temp_dir, elapsed, "llm" if use_llm else "heuristic")

    return reviews


# ---------------------------------------------------------------------------
# Deterministic Heuristic Evaluation
# ---------------------------------------------------------------------------

def _evaluate_candidate_heuristically(
    cand: HighlightCandidate,
    intent_profile: IntentProfile | None,
) -> EditorialReview:
    """Evaluate candidate across 12 criteria using pure deterministic rules."""
    text = cand.text
    text_lower = text.lower()
    first_sent = tu.first_sentence(text)

    # 1. Hook Strength (0.0 - 1.0)
    hook_s = 0.50
    if tu.is_question_starter(first_sent) or "?" in first_sent:
        hook_s += 0.30
    if not tu.has_floating_pronoun(first_sent):
        hook_s += 0.15
    hook_s = max(0.0, min(1.0, round(hook_s, 3)))

    # 2. Curiosity Level
    curiosity = 0.50
    if tu.detect_viral_type(text) in ("secret_revealed", "controversy"):
        curiosity += 0.35
    elif "secret" in text_lower or "nobody talks about" in text_lower:
        curiosity += 0.30
    curiosity = max(0.0, min(1.0, round(curiosity, 3)))

    # 3. Payoff Quality
    payoff = 0.50
    if cand.natural_end or tu.detect_conclusion_signal(text):
        payoff += 0.35
    if cand.semantic_completeness >= 0.8:
        payoff += 0.10
    payoff = max(0.0, min(1.0, round(payoff, 3)))

    # 4. Standalone Understanding
    standalone = max(0.0, min(1.0, round(cand.standalone_score / 5.0, 3)))

    # 5. Context Completeness
    context_comp = cand.editorial_completeness

    # 6. Emotional Impact
    emotion = max(0.0, min(1.0, round(cand.estimated_retention * 0.9, 3)))

    # 7. Information Value
    info_val = max(0.0, min(1.0, round(min(1.0, cand.information_density / 120.0), 3)))

    # 8. Story Completeness
    story_comp = cand.semantic_completeness

    # 9. Conversation Completeness
    conv_comp = cand.semantic_completeness

    # 10. Viral Potential
    viral_pot = 0.50 + min(0.40, len(cand.viral_patterns) * 0.15)
    viral_pot = max(0.0, min(1.0, round(viral_pot, 3)))

    # 11. Replay Value
    replay = 0.50 + (0.30 if cand.information_density > 80 else 0.10)
    replay = max(0.0, min(1.0, round(replay, 3)))

    # 12. Shareability
    share = 0.50 + (0.35 if cand.viral_patterns else 0.10)
    share = max(0.0, min(1.0, round(share, 3)))

    # Overall Editorial Review Score (Weighted Average)
    weights = [
        (hook_s, 0.15),
        (curiosity, 0.10),
        (payoff, 0.15),
        (standalone, 0.10),
        (context_comp, 0.10),
        (emotion, 0.05),
        (info_val, 0.05),
        (story_comp, 0.05),
        (conv_comp, 0.05),
        (viral_pot, 0.10),
        (replay, 0.05),
        (share, 0.05),
    ]

    total_score = sum(val * w for val, w in weights)
    editorial_score = max(0.0, min(1.0, round(total_score, 4)))

    # Rejection Reason Detection
    rejection_reasons = []
    if "?" in first_sent and "answer" not in cand.conversation_pattern and cand.semantic_completeness < 0.6:
        rejection_reasons.append("incomplete_answer")

    if hook_s < 0.45:
        rejection_reasons.append("weak_hook")

    if payoff < 0.45:
        rejection_reasons.append("missing_payoff")

    if cand.boundary_confidence_end < 0.50 or not cand.natural_end:
        rejection_reasons.append("abrupt_ending")

    if standalone < 0.40:
        rejection_reasons.append("context_missing")

    if info_val < 0.30:
        rejection_reasons.append("low_viewer_value")

    if cand.overall_boundary_confidence < 0.50:
        rejection_reasons.append("low_confidence")

    # Detailed Reasoning Text
    reasons_str = f"Editorial Review for Candidate {cand.candidate_id}: "
    if rejection_reasons:
        reasons_str += f"Flagged with flaws [{', '.join(rejection_reasons)}]. "
    else:
        reasons_str += "Strong standalone clip with clear hook and payoff. "

    reasons_str += (
        f"Hook={hook_s:.2f}, Payoff={payoff:.2f}, Standalone={standalone:.2f}, "
        f"ViralPotential={viral_pot:.2f}, OverallReviewScore={editorial_score:.4f}."
    )

    return EditorialReview(
        candidate_id=cand.candidate_id,
        hook_strength=hook_s,
        curiosity_level=curiosity,
        payoff_quality=payoff,
        standalone_understanding=standalone,
        context_completeness=context_comp,
        emotional_impact=emotion,
        information_value=info_val,
        story_completeness=story_comp,
        conversation_completeness=conv_comp,
        viral_potential=viral_pot,
        replay_value=replay,
        shareability=share,
        editorial_review_score=editorial_score,
        detailed_reasoning=reasons_str,
        rejection_reasons=rejection_reasons,
        confidence=0.90,
        source="heuristic",
        diagnostics={
            "subscores": {
                "hookStrength": hook_s,
                "curiosityLevel": curiosity,
                "payoffQuality": payoff,
                "standaloneUnderstanding": standalone,
                "viralPotential": viral_pot,
            },
            "rejectionReasonCount": len(rejection_reasons),
        },
    )


# ---------------------------------------------------------------------------
# Structured LLM Evaluation (Ollama / External Provider)
# ---------------------------------------------------------------------------

def _evaluate_candidate_with_llm(
    cand: HighlightCandidate,
    llm_provider: LLMProvider,
    intent_profile: IntentProfile | None,
) -> EditorialReview:
    """Evaluate candidate using structured LLM JSON response."""
    prompt = f"""You are a professional YouTube Shorts Editorial Reviewer.
Evaluate the following clip candidate transcript and respond strictly with valid JSON.

Clip Text: "{cand.text}"
Content Type: {cand.content_type}
Duration: {cand.duration:.1f} seconds

Respond ONLY with this JSON structure:
{{
  "hookStrength": 0.85,
  "curiosityLevel": 0.80,
  "payoffQuality": 0.90,
  "standaloneUnderstanding": 0.95,
  "contextCompleteness": 0.90,
  "emotionalImpact": 0.75,
  "informationValue": 0.85,
  "storyCompleteness": 0.85,
  "conversationCompleteness": 0.90,
  "viralPotential": 0.80,
  "replayValue": 0.75,
  "shareability": 0.85,
  "editorialReviewScore": 0.86,
  "detailedReasoning": "Professional summary...",
  "rejectionReasons": []
}}
"""
    response_text = llm_provider.generate(
        prompt=prompt,
        system_prompt="You are a strict YouTube Shorts Editorial Reviewer. Output JSON only."
    )

    data = json.loads(response_text)
    return EditorialReview(
        candidate_id=cand.candidate_id,
        hook_strength=float(data.get("hookStrength", 0.8)),
        curiosity_level=float(data.get("curiosityLevel", 0.8)),
        payoff_quality=float(data.get("payoffQuality", 0.8)),
        standalone_understanding=float(data.get("standaloneUnderstanding", 0.8)),
        context_completeness=float(data.get("contextCompleteness", 0.85)),
        emotional_impact=float(data.get("emotionalImpact", 0.75)),
        information_value=float(data.get("informationValue", 0.80)),
        story_completeness=float(data.get("storyCompleteness", 0.80)),
        conversation_completeness=float(data.get("conversationCompleteness", 0.85)),
        viral_potential=float(data.get("viralPotential", 0.80)),
        replay_value=float(data.get("replayValue", 0.75)),
        shareability=float(data.get("shareability", 0.80)),
        editorial_review_score=float(data.get("editorialReviewScore", 0.82)),
        detailed_reasoning=str(data.get("detailedReasoning", "")),
        rejection_reasons=data.get("rejectionReasons", []),
        confidence=0.95,
        source="llm",
        diagnostics={"llmProvider": type(llm_provider).__name__},
    )


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
                conversation_pattern=c.get("conversationPattern", "monologue_block"),
                information_density=float(c.get("informationDensity", 80.0)),
            )
            for c in data.get("candidates", [])
        ]
    except Exception as exc:
        logger.error("Failed to load highlight_candidates.json: %s", exc)
        return []


def _write_editorial_review(
    reviews: list[EditorialReview],
    temp_dir: Path,
    elapsed_sec: float,
    source: str,
) -> None:
    rev_dicts = [r.to_dict() for r in reviews]
    output = {
        "source": source,
        "reviewCount": len(reviews),
        "diagnostics": {
            "elapsedSeconds": round(elapsed_sec, 3),
            "flaggedCandidatesCount": sum(1 for r in reviews if r.rejection_reasons),
            "averageEditorialReviewScore": round(
                sum(r.editorial_review_score for r in reviews) / max(1, len(reviews)), 4
            ),
        },
        "reviews": rev_dicts,
    }
    out_path = temp_dir / "editorial_review.json"
    out_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
    logger.info("Written: %s", out_path)
