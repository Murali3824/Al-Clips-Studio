"""
Shared data schemas for the editorial intelligence highlight selection system.

All types are plain Python dataclasses with no external dependencies.
They serve as typed containers that flow from one pipeline pass to the next.

Design principles
-----------------
- Every field has a safe default so instances can be created with minimal
  arguments during testing or when optional data is unavailable.
- Optional fields use ``Optional[T]`` with a default of ``None`` so callers
  can distinguish "not computed" from a real zero/empty value.
- No serialisation logic lives here; each module is responsible for
  converting its dataclasses to/from JSON using ``dataclasses.asdict``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# ===========================================================================
# Pass 0 — Video Intent Detection
# ===========================================================================

@dataclass
class AcousticSignals:
    """Raw measurements extracted from audio and transcript before classification."""

    speaker_count: int = 1
    """Number of distinct speakers detected (from diarization or heuristic)."""

    speech_rate_wpm: float = 140.0
    """Average words-per-minute across the full video."""

    silence_ratio: float = 0.10
    """Fraction of total duration that is silent (silence_sec / total_sec)."""

    question_density: float = 0.03
    """Question marks per word in the transcript."""

    instruction_density: float = 0.01
    """Imperative verb count per word (do/start/stop/avoid/build/use …)."""

    narrative_markers: int = 0
    """Count of past-tense personal-story markers (e.g. "I was", "it happened")."""

    debate_markers: int = 0
    """Count of disagreement / contradiction markers."""


@dataclass
class EditorialRules:
    """
    Per-content-type editorial rules applied during candidate building and QA.

    These are populated by ``intent_detector.get_editorial_rules()`` based on
    the detected ``IntentProfile.primary_type`` and remain immutable for the
    rest of the pipeline run.
    """

    require_question: bool = False
    """For interview content: a clip MUST include the question before the answer."""

    require_answer: bool = False
    """For interview content: a clip MUST include a full answer."""

    require_conclusion: bool = False
    """A conclusion signal must be present before the clip ends."""

    allow_single_speaker_clips: bool = True
    """If False (interview mode), do not export clips with only one speaker."""

    min_conversation_turns: int = 1
    """Minimum number of conversation turns required in an approved clip."""

    preferred_pattern: str = "monologue_block"
    """
    Preferred conversation pattern for this content type.
    Values: ``monologue_block`` | ``question_answer`` |
            ``question_answer_expansion`` | ``story_arc`` | ``debate_exchange``
    """

    semantic_lookback_sec: float = 6.0
    """Maximum seconds to look backward when finding a natural clip start."""

    semantic_lookahead_sec: float = 8.0
    """Maximum seconds to look forward when finding a natural clip end."""


@dataclass
class IntentProfile:
    """
    Detected intent/content-type profile for the video.

    Produced by Pass 0 (intent_detector) and threaded through all subsequent
    passes so that editorial rules adapt to the content type.
    """

    primary_type: str = "solo_monologue"
    """
    Dominant content type. One of:
    ``interview`` | ``solo_monologue`` | ``tutorial_explainer`` |
    ``personal_story`` | ``debate_argument`` | ``comedy`` |
    ``panel_discussion`` | ``motivation_speech`` | ``news_update``
    """

    secondary_type: Optional[str] = None
    """Optional secondary characteristic (e.g. a ``personal_story`` within an ``interview``)."""

    confidence: float = 0.5
    """Classification confidence 0.0–1.0."""

    signals: AcousticSignals = field(default_factory=AcousticSignals)
    """Raw signals that drove the classification."""

    editorial_rules: EditorialRules = field(default_factory=EditorialRules)
    """Derived editorial rules for this content type."""


# ===========================================================================
# Pass 1 — Conversation Block Detection
# ===========================================================================

@dataclass
class MemoryWindow:
    """
    Precomputed surrounding conversation context for a turn.

    Stored directly on every ``ConversationTurn`` so that downstream passes
    always have the preceding and following context without re-querying the
    full transcript — this is the Conversation Memory mechanism.
    """

    prev2_text: str = ""
    """Text of the turn two positions before this one (empty if not available)."""

    prev1_text: str = ""
    """Text of the immediately preceding turn."""

    next1_text: str = ""
    """Text of the immediately following turn."""

    next2_text: str = ""
    """Text of the turn two positions after this one."""


@dataclass
class ConversationTurn:
    """
    A single speaker's uninterrupted speech segment.

    Turns are the atomic editorial unit.  Every clip candidate is constructed
    from one or more consecutive turns.
    """

    turn_id: str = ""
    """Unique identifier, e.g. ``turn_001``."""

    speaker: str = "SPEAKER_00"
    """Speaker label from diarization (or ``SPEAKER_00`` in single-speaker mode)."""

    role: str = "monologue_statement"
    """
    Conversational role. One of:
    ``question`` | ``answer`` | ``explanation`` | ``conclusion`` |
    ``transition`` | ``monologue_statement`` | ``hook_opener``
    """

    start: float = 0.0
    """Turn start time in seconds (word-level precision)."""

    end: float = 0.0
    """Turn end time in seconds (word-level precision)."""

    start_word_idx: int = 0
    """Index of the first word of this turn in the flat word list."""

    end_word_idx: int = 0
    """Index of the last word of this turn in the flat word list."""

    text: str = ""
    """Full transcript text of this turn."""

    avg_whisper_confidence: float = 1.0
    """
    Mean Whisper word probability across all words in the turn.
    Turns below 0.70 are flagged as low-confidence.
    """

    linked_turn_id: Optional[str] = None
    """
    Semantic link to the directly related turn:
    - For a ``question``: the ID of the ``answer`` turn that follows.
    - For an ``answer``: the ID of the ``question`` turn that preceded it.
    """

    prev_turn_id: Optional[str] = None
    """ID of the chronologically preceding turn (regardless of speaker)."""

    next_turn_id: Optional[str] = None
    """ID of the chronologically following turn."""

    memory_window: MemoryWindow = field(default_factory=MemoryWindow)
    """Precomputed surrounding context (see ``MemoryWindow``)."""

    pattern_signals: list[str] = field(default_factory=list)
    """
    List of signals that drove the role assignment, e.g.:
    ``["ends_with_question_mark", "starts_with_what"]``
    """

    low_confidence_flag: bool = False
    """True when avg_whisper_confidence < 0.70."""


@dataclass
class ConversationBlock:
    """
    Primary editorial semantic unit representing an uninterrupted speech block
    with rich precomputed metadata. Every downstream pass consumes these objects.
    """

    block_id: str = ""
    """Unique identifier, e.g. ``block_001``."""

    start_time: float = 0.0
    """Block start time in seconds (word-level precision)."""

    end_time: float = 0.0
    """Block end time in seconds (word-level precision)."""

    speaker_id: str = "SPEAKER_00"
    """Speaker label from diarization (or ``SPEAKER_00`` in single-speaker mode)."""

    speaker_role: str = "speaker"
    """Conversational role of the speaker (e.g. ``host``, ``guest``, ``narrator``, ``solo``)."""

    content_type: str = "solo_monologue"
    """Detected video intent format from IntentProfile."""

    block_role: str = "monologue_statement"
    """
    Editorial block role:
    ``question`` | ``answer`` | ``explanation`` | ``conclusion`` |
    ``rebuttal`` | ``hook`` | ``story`` | ``joke`` | ``transition`` | ``monologue_statement``
    """

    topic_id: Optional[str] = None
    """ID of the semantic topic segment this block belongs to."""

    topic_confidence: float = 1.0
    """Confidence that this block belongs to its assigned topic."""

    previous_block_id: Optional[str] = None
    """ID of the chronologically preceding block."""

    next_block_id: Optional[str] = None
    """ID of the chronologically following block."""

    linked_block_id: Optional[str] = None
    """ID of linked Q/A or setup/punchline block."""

    memory_window: MemoryWindow = field(default_factory=MemoryWindow)
    """Precomputed surrounding context (prev2, prev1, next1, next2 text)."""

    semantic_embedding: Optional[list[float]] = None
    """Placeholder for vector embedding (e.g. 768-dim float array)."""

    emotion_score: float = 0.0
    """Emotional intensity score 0.0–1.0."""

    emotion_valence: str = "neutral"
    """Emotional valence: ``positive`` | ``negative`` | ``excited`` | ``solemn`` | ``humorous`` | ``neutral``."""

    information_density: float = 0.0
    """Unique content words per minute in this block."""

    editorial_importance: float = 0.5
    """Overall calculated editorial importance score 0.0–1.0."""

    llm_reasoning: Optional[str] = None
    """Optional LLM classification reasoning."""

    text: str = ""
    """Full transcript text of this block."""

    start_word_idx: int = 0
    """Index of first word in global transcript word list."""

    end_word_idx: int = 0
    """Index of last word in global transcript word list."""

    avg_whisper_confidence: float = 1.0
    """Mean word probability across all words in this block."""

    pattern_signals: list[str] = field(default_factory=list)
    """List of signals driving role assignment."""

    low_confidence_flag: bool = False
    """True when avg_whisper_confidence < 0.70."""

    def to_dict(self) -> dict:
        """
        Convert to dictionary with both snake_case and camelCase field aliases
        for full JSON & API compatibility.
        """
        import dataclasses
        d = dataclasses.asdict(self)
        # Add camelCase aliases required by editorial specifications
        d["blockId"] = self.block_id
        d["startTime"] = self.start_time
        d["endTime"] = self.end_time
        d["speakerId"] = self.speaker_id
        d["speakerRole"] = self.speaker_role
        d["contentType"] = self.content_type
        d["blockRole"] = self.block_role
        d["topicId"] = self.topic_id
        d["topicConfidence"] = self.topic_confidence
        d["previousBlock"] = self.previous_block_id
        d["nextBlock"] = self.next_block_id
        d["linkedBlock"] = self.linked_block_id
        d["memoryWindow"] = dataclasses.asdict(self.memory_window)
        d["semanticEmbedding"] = self.semantic_embedding
        d["emotionScore"] = self.emotion_score
        d["emotionValence"] = self.emotion_valence
        d["informationDensity"] = self.information_density
        d["editorialImportance"] = self.editorial_importance
        d["llmReasoning"] = self.llm_reasoning
        return d


# ===========================================================================
# Pass 2 — Semantic Topic Detection
# ===========================================================================

@dataclass
class CompletenessSignals:
    """
    Boolean completeness indicators for an editorial segment.

    Used both in candidate scoring and in the editorial QA gate.
    """

    opens_with_question: bool = False
    answer_delivered: bool = False
    explanation_complete: bool = False
    conclusion_present: bool = False
    has_opening_hook: bool = False
    has_context: bool = False
    is_standalone_intelligible: bool = False


@dataclass
class ViralPotential:
    """
    Set of viral content signals detected in an editorial segment.

    Each flag is independently computed from linguistic patterns in the
    segment's transcript text.
    """

    has_personal_story: bool = False
    has_transformation: bool = False
    has_controversy: bool = False
    has_surprising_fact: bool = False
    has_expert_advice: bool = False
    has_emotional_peak: bool = False
    has_humor: bool = False
    has_argument: bool = False
    has_lesson: bool = False
    has_secret: bool = False
    has_hot_take: bool = False
    has_prediction: bool = False

    def strongest_type(self) -> str:
        """
        Return the single strongest detected viral type.

        Types are checked in editorial priority order — the type most likely
        to drive audience retention is returned first.
        """
        priority: list[tuple[str, str]] = [
            ("has_personal_story", "personal_story"),
            ("has_transformation", "transformation"),
            ("has_controversy", "controversy"),
            ("has_surprising_fact", "surprising_fact"),
            ("has_secret", "secret_revealed"),
            ("has_expert_advice", "expert_advice"),
            ("has_emotional_peak", "emotional_peak"),
            ("has_lesson", "lesson_learned"),
            ("has_hot_take", "hot_take"),
            ("has_argument", "argument"),
            ("has_humor", "humor"),
            ("has_prediction", "prediction"),
        ]
        for attr, name in priority:
            if getattr(self, attr):
                return name
        return "story_hook"


@dataclass
class EditorialSegment:
    """
    Primary editorial segment object created by Pass 2 (Editorial Segment Builder).
    Represents a self-contained, topically coherent unit of content constructed
    from one or more ConversationBlocks.
    """

    segment_id: str = ""
    """Unique identifier, e.g. ``seg_001``."""

    topic_id: str = "topic_001"
    """Unique topic identifier."""

    topic_title: str = ""
    """Human-readable title or summary of what this segment covers."""

    topic_summary: str = ""
    """Short description of segment topic (alias for topic_title)."""

    topic_confidence: float = 1.0
    """Confidence score 0.0–1.0 that this segment forms a single topic."""

    content_type: str = "solo_monologue"
    """Video intent format from IntentProfile."""

    start: float = 0.0
    """Segment start time in seconds."""

    end: float = 0.0
    """Segment end time in seconds."""

    duration: float = 0.0
    """``end - start`` duration in seconds."""

    conversation_blocks: list[str] = field(default_factory=list)
    """Ordered list of ConversationBlock IDs in this segment."""

    turn_ids: list[str] = field(default_factory=list)
    """Ordered list of ConversationTurn IDs (backward compatibility)."""

    speakers: list[str] = field(default_factory=list)
    """Distinct speaker IDs present in this segment."""

    conversation_pattern: str = "monologue_block"
    """Dominant conversational pattern."""

    opens_with_question: bool = False
    """True if segment opens with a question."""

    answer_delivered: bool = False
    """True if question in segment is followed by an answer."""

    explanation_complete: bool = False
    """True if key explanation or concept is fully explained."""

    conclusion_present: bool = False
    """True if segment finishes with a conclusion or wrap-up signal."""

    semantic_completeness: float = 1.0
    """Semantic idea completeness score 0.0–1.0."""

    editorial_completeness: float = 1.0
    """Overall editorial completeness score 0.0–1.0."""

    completeness: CompletenessSignals = field(default_factory=CompletenessSignals)
    """Nested completeness signals struct (backward compatibility)."""

    viral_patterns_detected: list[str] = field(default_factory=list)
    """List of detected viral pattern names (e.g. ['secret_revealed', 'personal_story'])."""

    viral_potential: ViralPotential = field(default_factory=ViralPotential)
    """Nested viral potential struct (backward compatibility)."""

    emotion_profile: dict = field(default_factory=dict)
    """Emotion metrics: ``{'intensity': float, 'valence': str, 'peakTimestamp': float}``."""

    information_density: float = 0.0
    """Unique content words per minute across segment."""

    estimated_viewer_retention: float = 0.75
    """Predicted retention score 0.0–1.0."""

    standalone_score: int = 4
    """1–5 rating of standalone intelligibility."""

    duplicate_fingerprint: str = ""
    """Content-word fingerprint used for topic deduplication."""

    raw_turn_count: int = 0
    """Total number of blocks/turns in segment."""

    llm_reasoning: Optional[str] = None
    """Optional LLM classification reasoning."""

    llm_summary: str = ""
    llm_standalone_score: int = 3
    llm_viral_type: str = "story_hook"
    llm_has_clear_hook: bool = False
    llm_has_payoff: bool = False

    diagnostics: dict = field(default_factory=dict)
    """Detailed explanation of why segment starts and ends."""

    def to_dict(self) -> dict:
        """Convert to dictionary with both snake_case and camelCase aliases."""
        import dataclasses
        d = dataclasses.asdict(self)
        d["segmentId"] = self.segment_id
        d["topicId"] = self.topic_id
        d["topicTitle"] = self.topic_title or self.topic_summary
        d["topicConfidence"] = self.topic_confidence
        d["contentType"] = self.content_type
        d["startTime"] = self.start
        d["endTime"] = self.end
        d["conversationBlocks"] = self.conversation_blocks
        d["speakers"] = self.speakers
        d["opensWithQuestion"] = self.opens_with_question
        d["answerDelivered"] = self.answer_delivered
        d["explanationComplete"] = self.explanation_complete
        d["conclusionPresent"] = self.conclusion_present
        d["semanticCompleteness"] = self.semantic_completeness
        d["editorialCompleteness"] = self.editorial_completeness
        d["viralPatternsDetected"] = self.viral_patterns_detected
        d["emotionProfile"] = self.emotion_profile
        d["informationDensity"] = self.information_density
        d["estimatedViewerRetention"] = self.estimated_viewer_retention
        d["standaloneScore"] = self.standalone_score
        d["duplicateFingerprint"] = self.duplicate_fingerprint
        d["llmReasoning"] = self.llm_reasoning
        d["diagnostics"] = self.diagnostics
        return d


# ===========================================================================
# Pass 3 — Clip Candidate Building
# ===========================================================================

@dataclass
class BoundaryConfidence:
    """
    Confidence scores for the start and end boundaries of a clip candidate.

    Confidence is computed from multiple signals (punctuation, silence gaps,
    speaker context, Whisper word probability).  Scores range 0.0–1.0.
    The iterative refiner (Pass 4) improves low-confidence boundaries.
    """

    start: float = 0.5
    """Confidence that the clip starts at a natural semantic boundary (0.0–1.0)."""

    end: float = 0.5
    """Confidence that the clip ends at a natural semantic boundary (0.0–1.0)."""

    overall: float = 0.5
    """
    Weighted overall confidence: ``(start * 0.45) + (end * 0.55)``.
    End is weighted slightly higher because abrupt endings are more noticeable
    to viewers than slightly early starts.
    """


@dataclass
class WhisperConfidenceRegion:
    """Whisper transcription confidence statistics for a clip's time range."""

    start_word_confidence: float = 1.0
    """Mean probability of words in the first 1s of the clip."""

    end_word_confidence: float = 1.0
    """Mean probability of words in the last 1s of the clip."""

    region_avg: float = 1.0
    """Mean probability of all words within the clip."""

    low_confidence_word_count: int = 0
    """Count of words with probability < 0.65 in the clip region."""

    low_confidence_at_boundary: bool = False
    """True if any boundary word (first or last 2s) has probability < 0.50."""


@dataclass
class RefinementLog:
    """Records one iteration of the boundary refinement loop (Pass 4)."""

    iteration: int = 0
    start_before: float = 0.0
    end_before: float = 0.0
    start_after: float = 0.0
    end_after: float = 0.0
    start_confidence_before: float = 0.0
    end_confidence_before: float = 0.0
    start_confidence_after: float = 0.0
    end_confidence_after: float = 0.0
    improvement: float = 0.0
    action_taken: str = ""

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["iteration"] = self.iteration
        d["startBefore"] = self.start_before
        d["endBefore"] = self.end_before
        d["startAfter"] = self.start_after
        d["endAfter"] = self.end_after
        d["startConfidenceBefore"] = self.start_confidence_before
        d["endConfidenceBefore"] = self.end_confidence_before
        d["startConfidenceAfter"] = self.start_confidence_after
        d["endConfidenceAfter"] = self.end_confidence_after
        d["improvement"] = self.improvement
        d["actionTaken"] = self.action_taken
        return d


@dataclass
class ClipCandidate:
    """
    Primary editorial candidate object created by Pass 3 (Editorial Clip Constructor).
    Represents a production-ready clip candidate with precise semantic boundaries,
    independent boundary confidence scores, and rich editorial metadata.
    """

    candidate_id: str = ""
    """Unique identifier, e.g. ``cand_001``."""

    segment_id: str = ""
    """ID of the ``EditorialSegment`` this candidate was derived from."""

    topic_id: str = ""
    """ID of the topic segment."""

    content_type: str = "solo_monologue"
    """Video content format from IntentProfile."""

    start: float = 0.0
    """Clip start time in seconds (word-level precision)."""

    end: float = 0.0
    """Clip end time in seconds (word-level precision)."""

    duration: float = 0.0
    """Clip duration in seconds (``end - start``)."""

    original_start: float = 0.0
    """Unexpanded segment start time."""

    original_end: float = 0.0
    """Unexpanded segment end time."""

    expanded_start: float = 0.0
    """Semantically expanded start time."""

    expanded_end: float = 0.0
    """Semantically expanded end time."""

    boundary_confidence_start: float = 0.8
    """Confidence score 0.0–1.0 for start boundary."""

    boundary_confidence_end: float = 0.8
    """Confidence score 0.0–1.0 for end boundary."""

    overall_boundary_confidence: float = 0.8
    """Weighted overall boundary confidence."""

    context_expansion_reason: str = "No expansion required"
    """Detailed reason for why boundaries were expanded."""

    hook_timestamp: float = 0.0
    """Timestamp of opening hook moment."""

    payoff_timestamp: float = 0.0
    """Timestamp of key payoff / conclusion moment."""

    explanation_start: float = 0.0
    """Start time of main explanation body."""

    explanation_end: float = 0.0
    """End time of main explanation body."""

    semantic_completeness: float = 1.0
    """Semantic completeness score 0.0–1.0."""

    editorial_completeness: float = 1.0
    """Editorial completeness score 0.0–1.0."""

    standalone_score: int = 4
    """1–5 standalone intelligibility rating."""

    estimated_retention: float = 0.75
    """Predicted audience retention score 0.0–1.0."""

    viral_patterns: list[str] = field(default_factory=list)
    """List of detected viral pattern names."""

    speakers: list[str] = field(default_factory=list)
    """Speaker IDs present in clip."""

    duplicate_fingerprint: str = ""
    """Vocabulary fingerprint for deduplication."""

    information_density: float = 80.0
    """Unique content words per minute in clip."""

    llm_reasoning: Optional[str] = None
    """Optional LLM reasoning."""

    needs_refinement: bool = False
    """True when overall_boundary_confidence < 0.70."""

    long_form: bool = False
    """True when clip duration exceeds max_duration by <= 30% to preserve full thought."""

    context_expanded: bool = False
    """True when start boundary was expanded backward to include context."""

    context_expansion_seconds: float = 0.0
    """Seconds added at start for context expansion."""

    natural_start: bool = True
    """True when start is at sentence beginning."""

    natural_end: bool = True
    """True when end is at sentence completion."""

    start_word: str = ""
    """First word of clip."""

    end_word: str = ""
    """Last word of clip."""

    conversation_pattern: str = "monologue_block"
    """Dominant conversation pattern."""

    boundary_confidence: BoundaryConfidence = field(default_factory=BoundaryConfidence)

    whisper_confidence: WhisperConfidenceRegion = field(default_factory=WhisperConfidenceRegion)

    memory_context: dict = field(default_factory=dict)
    """Surrounding topic context."""

    text: str = ""
    """Full transcript text of candidate."""

    speaker_turn_ids: list[str] = field(default_factory=list)

    refinement_log: list[RefinementLog] = field(default_factory=list)

    refinement_iterations: int = 0

    candidate_boundary_warning: bool = False

    context_limited: bool = False

    editorial_quality_score: float = 0.80
    """Overall Editorial Quality Score (0.0–1.0) combining boundary confidence, completeness, standalone score, and retention prediction."""

    final_production_score: float = 0.80
    """Final Production Score from Pass 6."""

    duplicate_cluster_id: str = ""
    """Cluster ID from Phase I."""

    duplicate_status: str = "UNIQUE"
    """"RETAINED", "REJECTED_DUPLICATE", or "UNIQUE"."""

    retained_reason: str = ""
    """Reason candidate was retained."""

    rejected_reason: str = ""
    """Reason candidate was rejected."""

    diversity_score: float = 1.0
    """Diversity score 0.0–1.0."""

    rank: int = 0
    """Final rank from Pass 7."""

    ranking_score: float = 0.0
    """Final RankingScore from Pass 7."""

    selected: bool = False
    """True if selected for final production clip pool."""

    selection_reason: str = ""
    """Reason candidate was selected or rejected by selection constraints."""

    qa_status: str = "PASSED"
    """QA status from Pass 8 (PASSED, REPAIRED_AND_PASSED, REJECTED)."""

    final_approval: bool = True
    """True if approved by Senior Editor QA Gate (Pass 8)."""

    qa_diagnostics: dict = field(default_factory=dict)
    """Diagnostics from Pass 8 QA Gate."""

    score_breakdown: dict = field(default_factory=dict)
    weighting_profile: dict = field(default_factory=dict)
    ranking_breakdown: dict = field(default_factory=dict)

    diagnostics: dict = field(default_factory=dict)
    """Diagnostics recording why start and end timestamps were chosen."""

    def to_dict(self) -> dict:
        """Convert to dictionary with both snake_case and camelCase aliases."""
        import dataclasses
        d = dataclasses.asdict(self)
        d["candidateId"] = self.candidate_id
        d["segmentId"] = self.segment_id
        d["topicId"] = self.topic_id
        d["contentType"] = self.content_type
        d["startTime"] = self.start
        d["endTime"] = self.end
        d["clipDuration"] = self.duration
        d["originalStart"] = self.original_start
        d["originalEnd"] = self.original_end
        d["expandedStart"] = self.expanded_start
        d["expandedEnd"] = self.expanded_end
        d["boundaryConfidenceStart"] = self.boundary_confidence_start
        d["boundaryConfidenceEnd"] = self.boundary_confidence_end
        d["overallBoundaryConfidence"] = self.overall_boundary_confidence
        d["contextExpansionReason"] = self.context_expansion_reason
        d["hookTimestamp"] = self.hook_timestamp
        d["payoffTimestamp"] = self.payoff_timestamp
        d["explanationStart"] = self.explanation_start
        d["explanationEnd"] = self.explanation_end
        d["semanticCompleteness"] = self.semantic_completeness
        d["editorialCompleteness"] = self.editorial_completeness
        d["standaloneScore"] = self.standalone_score
        d["estimatedRetention"] = self.estimated_retention
        d["viralPatterns"] = self.viral_patterns
        d["speakers"] = self.speakers
        d["duplicateFingerprint"] = self.duplicate_fingerprint
        d["llmReasoning"] = self.llm_reasoning
        d["needsRefinement"] = self.needs_refinement
        d["informationDensity"] = self.information_density
        d["editorialQualityScore"] = self.editorial_quality_score
        d["refinementIterations"] = self.refinement_iterations
        d["refinementLog"] = [log.to_dict() for log in self.refinement_log]
        d["finalProductionScore"] = getattr(self, "final_production_score", 0.80)
        d["scoreBreakdown"] = getattr(self, "score_breakdown", {})
        d["weightingProfile"] = getattr(self, "weighting_profile", {})
        d["duplicateClusterId"] = getattr(self, "duplicate_cluster_id", "")
        d["duplicateStatus"] = getattr(self, "duplicate_status", "UNIQUE")
        d["retainedReason"] = getattr(self, "retained_reason", "")
        d["rejectedReason"] = getattr(self, "rejected_reason", "")
        d["diversityScore"] = getattr(self, "diversity_score", 1.0)
        d["rank"] = getattr(self, "rank", 0)
        d["rankingScore"] = getattr(self, "ranking_score", 0.0)
        d["selected"] = getattr(self, "selected", False)
        d["selectionReason"] = getattr(self, "selection_reason", "")
        d["qaStatus"] = getattr(self, "qa_status", "PASSED")
        d["finalApproval"] = getattr(self, "final_approval", True)
        d["qaDiagnostics"] = getattr(self, "qa_diagnostics", {})
        d["diagnostics"] = self.diagnostics
        return d


#: HighlightCandidate is an alias for ClipCandidate
HighlightCandidate = ClipCandidate


# ===========================================================================
# Pass 5 — LLM Editorial Ratings
# ===========================================================================

@dataclass
class LLMRating:
    """
    Editorial evaluation returned by the LLM (Pass 5).

    When the LLM is unavailable the same dataclass is populated with
    heuristically derived values so downstream passes never need to
    branch on LLM availability.
    """

    candidate_id: str = ""

    hook_strength: int = 5
    """LLM's hook strength rating 0–10."""

    context_complete: bool = True
    """True when the LLM considers the clip self-contained."""

    context_explanation: str = ""
    """LLM's reasoning for the context_complete assessment."""

    narrative_arc: str = "partial"
    """``"strong"`` | ``"partial"`` | ``"weak"``"""

    ending_quality: str = "acceptable"
    """``"strong"`` | ``"acceptable"`` | ``"weak"``"""

    viral_type: str = "story_hook"
    """Best-matching viral content type from the standard taxonomy."""

    editorial_decision: str = "PUBLISH"
    """``"PUBLISH"`` | ``"REVISE_BOUNDARIES"`` | ``"REJECT"``"""

    editorial_score: int = 65
    """LLM's holistic editorial score 0–100."""

    suggested_hook: str = ""
    """4–7 word hook text specific to this clip's content."""

    rejection_reason: Optional[str] = None
    """Populated when ``editorial_decision == "REJECT"``."""

    revise_boundaries_note: Optional[str] = None
    """Populated when ``editorial_decision == "REVISE_BOUNDARIES"``."""

    source: str = "heuristic"
    """``"llm"`` when rated by the LLM; ``"heuristic"`` when computed locally."""


@dataclass
class EditorialReview:
    """
    Structured editorial review object produced by Pass 5 (Editorial Review Board).
    Evaluates every candidate across 12 structured metrics, computes an overall
    editorialReviewScore, and records detailed reasoning & rejection reasons.
    """

    candidate_id: str = ""
    hook_strength: float = 0.8
    curiosity_level: float = 0.8
    payoff_quality: float = 0.8
    standalone_understanding: float = 0.8
    context_completeness: float = 0.85
    emotional_impact: float = 0.75
    information_value: float = 0.80
    story_completeness: float = 0.80
    conversation_completeness: float = 0.85
    viral_potential: float = 0.80
    replay_value: float = 0.75
    shareability: float = 0.80
    editorial_review_score: float = 0.82
    detailed_reasoning: str = ""
    rejection_reasons: list[str] = field(default_factory=list)
    confidence: float = 0.90
    source: str = "heuristic"  # "llm" or "heuristic"
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["candidateId"] = self.candidate_id
        d["hookStrength"] = self.hook_strength
        d["curiosityLevel"] = self.curiosity_level
        d["payoffQuality"] = self.payoff_quality
        d["standaloneUnderstanding"] = self.standalone_understanding
        d["contextCompleteness"] = self.context_completeness
        d["emotionalImpact"] = self.emotional_impact
        d["informationValue"] = self.information_value
        d["storyCompleteness"] = self.story_completeness
        d["conversationCompleteness"] = self.conversation_completeness
        d["viralPotential"] = self.viral_potential
        d["replayValue"] = self.replay_value
        d["shareability"] = self.shareability
        d["editorialReviewScore"] = self.editorial_review_score
        d["detailedReasoning"] = self.detailed_reasoning
        d["rejectionReasons"] = self.rejection_reasons
        d["confidence"] = self.confidence
        d["source"] = self.source
        d["diagnostics"] = self.diagnostics
        return d


# ===========================================================================
# Pass 6 — Production Scoring Engine
# ===========================================================================

@dataclass
class ProductionScore:
    """
    Multi-dimensional production score object produced by Pass 6 (Production Scoring Engine).
    Combines 15 signal dimensions using dynamic content-type-weighted profiles.
    """

    candidate_id: str = ""
    final_production_score: float = 0.80
    score_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    weighting_profile: dict[str, float] = field(default_factory=dict)
    confidence: float = 0.90
    content_type: str = "solo_monologue"
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["candidateId"] = self.candidate_id
        d["finalProductionScore"] = self.final_production_score
        d["scoreBreakdown"] = self.score_breakdown
        d["weightingProfile"] = self.weighting_profile
        d["confidence"] = self.confidence
        d["contentType"] = self.content_type
        d["diagnostics"] = self.diagnostics
        return d


@dataclass
class DuplicateCluster:
    """
    Represents a cluster of duplicate or highly overlapping candidates (Pass I).
    """

    cluster_id: str = ""
    candidate_ids: list[str] = field(default_factory=list)
    retained_candidate_id: str = ""
    rejected_candidate_ids: list[str] = field(default_factory=list)
    cluster_reason: str = ""
    max_similarity: float = 0.0

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["clusterId"] = self.cluster_id
        d["candidateIds"] = self.candidate_ids
        d["retainedCandidateId"] = self.retained_candidate_id
        d["rejectedCandidateIds"] = self.rejected_candidate_ids
        d["clusterReason"] = self.cluster_reason
        d["maxSimilarity"] = self.max_similarity
        return d


@dataclass
class RankingCandidate:
    """
    Candidate ranking & selection result object produced by Phase J (Pass 7).
    """

    rank: int = 1
    candidate_id: str = ""
    ranking_score: float = 0.85
    final_production_score: float = 0.85
    diversity_score: float = 1.0
    selected: bool = True
    selection_reason: str = ""
    rejection_reason: str = ""
    ranking_breakdown: dict[str, dict[str, float]] = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["rank"] = self.rank
        d["candidateId"] = self.candidate_id
        d["rankingScore"] = self.ranking_score
        d["finalProductionScore"] = self.final_production_score
        d["diversityScore"] = self.diversity_score
        d["selected"] = self.selected
        d["selectionReason"] = self.selection_reason
        d["rejectionReason"] = self.rejection_reason
        d["rankingBreakdown"] = self.ranking_breakdown
        d["diagnostics"] = self.diagnostics
        return d


@dataclass
class QAReportEntry:
    """
    Result of senior editor QA validation on a selected candidate (Pass 8 / Phase K).
    """

    candidate_id: str = ""
    qa_status: str = "PASSED"  # "PASSED", "REPAIRED_AND_PASSED", "REJECTED"
    passed_checks: list[str] = field(default_factory=list)
    failed_checks: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    rejection_reasons: list[str] = field(default_factory=list)
    final_approval: bool = True
    reviewer_confidence: float = 0.95
    qa_diagnostics: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["candidateId"] = self.candidate_id
        d["qaStatus"] = self.qa_status
        d["passedChecks"] = self.passed_checks
        d["failedChecks"] = self.failed_checks
        d["warnings"] = self.warnings
        d["rejectionReasons"] = self.rejection_reasons
        d["finalApproval"] = self.final_approval
        d["reviewerConfidence"] = self.reviewer_confidence
        d["qaDiagnostics"] = self.qa_diagnostics
        return d


@dataclass
class FinalHighlight:
    """
    Final production highlight object exported to highlights.json (Pass 9 / Phase L).
    Fully backward compatible with downstream video renderers.
    """

    clip_id: str = ""
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    score: float = 0.85
    ranking: int = 1
    production_score: float = 0.85
    editorial_quality: float = 0.85
    qa_status: str = "PASSED"
    topic_id: str = ""
    speaker_ids: list[str] = field(default_factory=list)
    hook_timestamp: float = 0.0
    payoff_timestamp: float = 0.0
    text: str = ""
    # Legacy backward-compatible fields consumed by stage_09_cut_crop.py & stage_11_metadata.py
    hook: str = ""
    reason: str = ""
    source: str = "editorial-intelligence"
    model: str = "editorial-intelligence-pipeline"
    content_type: str = "story_hook"

    def to_dict(self) -> dict:
        import dataclasses
        d = dataclasses.asdict(self)
        d["id"] = self.clip_id
        d["clipId"] = self.clip_id
        d["clip_id"] = self.clip_id
        d["start"] = self.start
        d["end"] = self.end
        d["duration"] = self.duration
        d["score"] = self.score
        d["ranking"] = self.ranking
        d["productionScore"] = self.production_score
        d["editorialQuality"] = self.editorial_quality
        d["qaStatus"] = self.qa_status
        d["topicId"] = self.topic_id
        d["speakerIds"] = self.speaker_ids
        d["hookTimestamp"] = self.hook_timestamp
        d["payoffTimestamp"] = self.payoff_timestamp
        d["text"] = self.text
        # Legacy backward-compatible fields for downstream stages
        d["hook"] = self.hook
        d["reason"] = self.reason
        d["source"] = self.source
        d["model"] = self.model
        d["type"] = self.content_type
        return d


@dataclass
class EditorialScoreDimensions:
    """
    Eight independent scoring dimensions (0–12 each, total max 96).

    The raw total is normalised to 0–100 in ``EditorialScore.normalized``.
    """

    hook_strength: int = 0
    """Does the opening 5 seconds stop a scrolling viewer?"""

    context_completeness: int = 0
    """Does the viewer have all the context they need from the start?"""

    narrative_arc: int = 0
    """Is there a discernible Setup → Development → Payoff structure?"""

    explanation_completeness: int = 0
    """Is the explanation or answer fully delivered before the clip ends?"""

    ending_quality: int = 0
    """Does the clip end in a natural, satisfying way?"""

    standalone_intelligibility: int = 0
    """Would a viewer who has never seen the full video understand this clip?"""

    whisper_confidence: int = 0
    """How reliable is the transcription quality in this clip's region?"""

    audience_retention: int = 0
    """Predicted probability that a viewer watches the clip to the end."""


@dataclass
class EditorialScore:
    """Full editorial score for one clip candidate (Pass 6 output)."""

    dimensions: EditorialScoreDimensions = field(default_factory=EditorialScoreDimensions)

    total: int = 0
    """Raw sum of all 8 dimensions (0–96)."""

    normalized: int = 0
    """Score normalised to 0–100: ``round(total / 96 * 100)``."""

    tier: str = "B"
    """
    Editorial tier assignment:
    - ``"S"`` — 80–100: Publish immediately
    - ``"A"`` — 62–79: Strong clip, minor imperfections
    - ``"B"`` — 45–61: Acceptable, only to fill count
    - ``"Rejected"`` — 0–44: Do not publish
    """

    information_density: float = 0.0
    """Unique content words per minute in the clip."""

    emotional_peak_timestamp: Optional[float] = None
    """Timestamp (seconds) of the most emotionally intense moment in the clip."""

    thumbnail_timestamp: Optional[float] = None
    """
    Recommended frame timestamp for thumbnail extraction.
    Passed through to ``highlights.json`` for stage_13 to use.
    """


@dataclass
class ScoredCandidate:
    """A fully evaluated clip candidate ready for the QA gate (Pass 7)."""

    candidate: ClipCandidate = field(default_factory=ClipCandidate)
    llm_rating: LLMRating = field(default_factory=LLMRating)
    editorial_score: EditorialScore = field(default_factory=EditorialScore)
    viral_type: str = "story_hook"
    suggested_hook: str = ""


# ===========================================================================
# Pass 7 — QA Gate
# ===========================================================================

@dataclass
class QAChecklistResult:
    """
    Result of the 6-point editorial QA checklist for one clip candidate.

    A clip passes the QA gate when ``overall_decision == "APPROVED"``.
    """

    qa1_standalone: str = "PASS"
    """Is the clip understandable without the original video?"""

    qa2_hook: str = "PASS"
    """Does the clip open with a complete, attention-grabbing hook?"""

    qa3_payoff: str = "PASS"
    """Does the clip deliver on its opening promise?"""

    qa4_ending: str = "PASS"
    """Does the clip end in a satisfying way?  (WARN is acceptable.)"""

    qa5_confidence: str = "PASS"
    """Is the transcription reliable enough to trust the clip?"""

    qa6_editorial: str = "PASS"
    """Would a professional editor publish this?  (Tier-based.)"""

    overall_decision: str = "APPROVED"
    """``"APPROVED"`` | ``"REJECTED"`` | ``"CONDITIONALLY_APPROVED"``"""

    flags: list[str] = field(default_factory=list)
    """List of issue codes, e.g. ``["missing_context", "incomplete_payoff"]``."""

    rejection_reason: Optional[str] = None
    """Human-readable rejection reason for logging and debugging."""


@dataclass
class QAReport:
    """Aggregate QA results for all candidates in a pipeline run (Pass 7)."""

    approved_candidate_ids: list[str] = field(default_factory=list)
    rejected_candidate_ids: list[str] = field(default_factory=list)
    checklist: dict[str, QAChecklistResult] = field(default_factory=dict)

    contradiction_pairs: list[tuple[str, str]] = field(default_factory=list)
    """
    Pairs of candidate IDs whose main claims contradict each other.
    These are flagged for user review but not automatically rejected.
    """

    topic_diversity_report: dict = field(default_factory=dict)
    """
    Summary of viral-type distribution after deduplication:
    ``{ "personal_story": 2, "controversy": 1, ... }``
    """


# ===========================================================================
# Pass 8 — Final Highlight Output
# ===========================================================================

@dataclass
class HighlightOutput:
    """
    Final per-clip output written to highlights.json.

    Schema is backward-compatible with the format consumed by downstream
    stages 05–15.  All existing field names are preserved exactly.
    New fields (``tier``, ``editorial_score``, ``boundary_confidence``,
    ``viral_type``, ``intent_type``, ``quality_flag``,
    ``thumbnail_timestamp``) are additions only — no existing field is
    renamed or removed.
    """

    # --- Existing fields (unchanged) ---
    id: str = ""
    start: float = 0.0
    end: float = 0.0
    duration: float = 0.0
    score: int = 70
    hook: str = ""
    text: str = ""
    reason: str = ""
    type: str = "story_hook"
    source: str = "editorial_intelligence_v2"
    model: Optional[str] = None
    min_duration: float = 15.0
    quality_checklist: list[str] = field(default_factory=list)

    # --- New fields (additions only) ---
    tier: str = "B"
    """Editorial tier: ``"S"`` | ``"A"`` | ``"B"``."""

    editorial_score: int = 70
    """Normalised 0–100 editorial score from Pass 6."""

    boundary_confidence: float = 0.5
    """Overall boundary confidence from Pass 3/4 (0.0–1.0)."""

    viral_type: str = "story_hook"
    """Best-matching viral pattern type."""

    intent_type: str = "solo_monologue"
    """Content type detected by Pass 0."""

    quality_flag: Optional[str] = None
    """
    ``None`` for normal clips.
    ``"below_threshold"`` for clips below the editorial bar but included to
    fill the requested count.
    ``"coverage_fill"`` for clips added to satisfy timeline zone coverage.
    """

    thumbnail_timestamp: Optional[float] = None
    """
    Recommended frame for thumbnail extraction (seconds).
    ``None`` means stage_13 uses its default mid-clip extraction.
    """
