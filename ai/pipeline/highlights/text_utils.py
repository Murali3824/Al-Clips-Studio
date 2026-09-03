"""
Shared text utility functions for the editorial intelligence highlight system.

Design constraints
------------------
- Pure functions only.  No external dependencies beyond the Python standard
  library.  No ML models, no network calls, no file I/O, no side effects.
- Every function is independently unit-testable.
- All functions accept and return plain Python types (str, list, dict, float,
  bool) so they can be called from any pipeline pass without importing schemas.
- Performance: functions operate on the word list from ``transcript.json``
  (typically 1,000–15,000 items for a 5–60 min video) and run in O(n) time.
"""

from __future__ import annotations

import re
from typing import Optional


# ===========================================================================
# Constants
# ===========================================================================

# Characters that end a sentence when they are the final character of a word.
SENTENCE_FINAL: frozenset[str] = frozenset({".", "?", "!"})

# Connector / conjunction words.  A clip boundary that falls immediately
# before or after one of these is at a semantically poor position.
CONNECTOR_WORDS: frozenset[str] = frozenset({
    "and", "but", "or", "so", "yet", "nor", "for",
    "because", "although", "however", "therefore", "thus",
    "then", "while", "since", "when", "where", "which", "that",
    "who", "whom", "whose", "if", "unless", "until", "though",
    "even", "just", "also", "either", "neither",
})

# First words of a question.  Used for role detection and hook analysis.
QUESTION_STARTERS: frozenset[str] = frozenset({
    "what", "how", "why", "when", "where", "who", "whom", "whose",
    "which", "do", "does", "did", "have", "has", "had", "is", "are",
    "was", "were", "will", "would", "could", "should", "can", "may",
    "might", "shall",
})

# Phrases that signal a topic change (checked via substring match on turn text).
TRANSITION_PHRASES: tuple[str, ...] = (
    "let's move on",
    "let's talk about",
    "moving on",
    "switching gears",
    "on a different note",
    "speaking of which",
    "that brings me to",
    "now let's",
    "next up",
    "another thing i want",
    "one more thing",
    "before i forget",
    "changing topics",
    "on another note",
    "but anyway",
    "anyway moving",
)

# Phrases that signal a conclusion (checked via substring match on turn text).
CONCLUSION_SIGNALS: tuple[str, ...] = (
    "so the point is",
    "in summary",
    "to summarize",
    "the bottom line",
    "at the end of the day",
    "what this means",
    "the lesson",
    "the takeaway",
    "in conclusion",
    "ultimately",
    "basically what",
    "so basically",
    "the moral",
    "what i learned",
    "what we learned",
    "the key insight",
    "and that's why",
    "and that's how",
    "that's the thing",
    "so that's",
    "and so that's",
)

# Pronouns that, when they open a clip, indicate missing context.
FLOATING_PRONOUNS: frozenset[str] = frozenset({
    "he", "she", "they", "it", "him", "her", "them", "his", "hers",
    "their", "its", "this", "that", "these", "those",
})

# Standard English stop words (excluded from content-word analysis).
STOP_WORDS: frozenset[str] = frozenset({
    "a", "an", "the", "and", "or", "but", "in", "on", "at", "to",
    "for", "of", "with", "by", "from", "up", "about", "into",
    "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further",
    "then", "once", "here", "there", "when", "where", "why", "how",
    "all", "both", "each", "few", "more", "most", "other", "some",
    "such", "no", "nor", "not", "only", "own", "same", "so", "than",
    "too", "very", "just", "that", "this", "these", "those", "i",
    "me", "my", "myself", "we", "our", "ours", "ourselves", "you",
    "your", "yours", "yourself", "he", "him", "his", "himself",
    "she", "her", "hers", "herself", "it", "its", "itself", "they",
    "them", "their", "theirs", "themselves", "what", "which", "who",
    "whom", "is", "am", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would",
    "could", "should", "may", "might", "shall", "can", "need",
    "dare", "ought", "used", "get", "got", "go", "went",
    "like", "yeah", "um", "uh", "okay", "ok", "right", "well",
    "actually", "literally", "basically", "sort", "kind",
})

# Emotional vocabulary (lightweight; no external models required).
_POSITIVE_WORDS: frozenset[str] = frozenset({
    "love", "amazing", "wonderful", "great", "fantastic", "excellent",
    "brilliant", "incredible", "awesome", "happy", "joy", "proud",
    "grateful", "thankful", "excited", "thrilled", "delighted",
    "beautiful", "perfect", "best", "outstanding",
})

_NEGATIVE_WORDS: frozenset[str] = frozenset({
    "hate", "terrible", "awful", "horrible", "devastating", "tragic",
    "sad", "depressed", "frustrated", "angry", "furious", "disgusted",
    "disappointed", "failure", "failed", "lost", "destroyed", "broken",
    "hurt", "pain", "struggle", "difficult", "worst",
})

_EXCITED_WORDS: frozenset[str] = frozenset({
    "incredible", "unbelievable", "shocking", "explosive", "wild",
    "crazy", "insane", "mindblowing", "insane", "game-changing",
    "revolutionary", "massive",
})

_SOLEMN_WORDS: frozenset[str] = frozenset({
    "death", "died", "passed away", "tragedy", "loss", "grief",
    "sorrow", "suffering", "struggling", "alone", "helpless",
})

_HUMOROUS_WORDS: frozenset[str] = frozenset({
    "haha", "lol", "funny", "hilarious", "laugh", "joke", "absurd",
    "ridiculous", "ironic", "sarcastic", "silly",
})

_ALL_EMOTIONAL_WORDS: frozenset[str] = (
    _POSITIVE_WORDS | _NEGATIVE_WORDS | _EXCITED_WORDS |
    _SOLEMN_WORDS | _HUMOROUS_WORDS
)

# Viral pattern vocabulary signals (ordered by editorial priority).
_VIRAL_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("secret_revealed", (
        "nobody talks about", "hidden", "revealed", "what they don't tell",
        "secret", "they don't want", "nobody knows", "nobody told me",
    )),
    ("controversy", (
        "i disagree", "that's wrong", "actually no", "the real truth",
        "most people think", "popular belief", "controversial",
        "they lied", "they were wrong",
    )),
    ("transformation", (
        "used to be", "now i", "changed my", "realized", "transformed",
        "before and after", "completely different", "turning point",
    )),
    ("mistake_admission", (
        "i made a mistake", "i failed", "i was wrong", "i regret",
        "i wish i had", "don't do what i did", "i messed up",
    )),
    ("personal_story", (
        "when i was", "it happened", "one day", "i remember",
        "growing up", "back then", "i was sitting", "i was working",
        "i got a call", "i received",
    )),
    ("lesson_learned", (
        "the lesson is", "what i learned", "takeaway", "the key insight",
        "what this teaches", "the moral", "what we can learn",
    )),
    ("expert_advice", (
        "step 1", "step 2", "first you", "the way to do",
        "here's how", "the process is", "you should", "make sure you",
        "the best approach",
    )),
    ("prediction", (
        "i think in the future", "i predict", "what's going to happen",
        "in 5 years", "the next decade", "this will change",
    )),
    ("hot_take", (
        "hot take", "unpopular opinion", "fight me on this",
        "controversial opinion", "i know this is controversial",
        "people are gonna hate this",
    )),
)


# ===========================================================================
# Text cleaning
# ===========================================================================

def clean_text(text: str) -> str:
    """Normalise whitespace and strip leading/trailing spaces."""
    return re.sub(r"\s+", " ", text).strip()


# ===========================================================================
# Word-level boundary utilities
# ===========================================================================

def find_sentence_start(
    words: list[dict],
    start_idx: int,
    max_lookback_sec: float = 6.0,
) -> int:
    """
    Walk backward from ``start_idx`` to find the beginning of the sentence.

    A sentence boundary is detected when:
    - The immediately preceding word ends with ``.``, ``?``, or ``!``.
    - The silence gap between the preceding word's end and the current
      word's start exceeds 1.2 seconds.
    - Looking further back would exceed ``max_lookback_sec``.

    This function intentionally does NOT use fixed-duration windows —
    it expands backward until a *semantic* stopping condition is met.

    Args:
        words:            Flat word list from ``transcript.json``.
                          Each element must have ``'word'``, ``'start'``,
                          ``'end'`` keys.
        start_idx:        Index in ``words`` to begin searching backward from.
        max_lookback_sec: Maximum seconds to search backward.

    Returns:
        Index of the first word of the sentence that contains ``start_idx``.
        Always a valid index (clamped to 0).
    """
    if not words or start_idx <= 0:
        return max(0, start_idx)

    anchor_time = float(words[start_idx]["start"])
    current = start_idx

    while current > 0:
        prev_word = words[current - 1]
        curr_word = words[current]

        # Hard time limit
        if anchor_time - float(prev_word["start"]) > max_lookback_sec:
            return current

        # Sentence boundary: previous word ends a sentence
        prev_text = str(prev_word.get("word", "")).strip()
        if prev_text and prev_text[-1] in SENTENCE_FINAL:
            return current

        # Pause boundary: natural gap between two words
        silence_gap = float(curr_word["start"]) - float(prev_word["end"])
        if silence_gap > 1.2:
            return current

        current -= 1

    return 0


def find_sentence_end(
    words: list[dict],
    end_idx: int,
    max_lookahead_sec: float = 8.0,
) -> int:
    """
    Walk forward from ``end_idx`` to find the end of the current sentence.

    A sentence boundary is detected when:
    - The current word ends with ``.``, ``?``, or ``!``.
    - The silence gap between this word's end and the next word's start
      exceeds 1.5 seconds.
    - Looking further forward would exceed ``max_lookahead_sec``.

    Args:
        words:             Flat word list from ``transcript.json``.
        end_idx:           Index in ``words`` to begin searching forward from.
        max_lookahead_sec: Maximum seconds to search forward.

    Returns:
        Index of the last word of the sentence that contains ``end_idx``.
        Always a valid index (clamped to ``len(words) - 1``).
    """
    if not words:
        return 0
    n = len(words)
    if end_idx >= n - 1:
        return n - 1

    anchor_time = float(words[end_idx]["end"])
    current = end_idx

    while current < n - 1:
        curr_word = words[current]

        # Hard time limit
        if float(curr_word["end"]) - anchor_time > max_lookahead_sec:
            return current

        # Sentence boundary: current word ends a sentence
        curr_text = str(curr_word.get("word", "")).strip()
        if curr_text and curr_text[-1] in SENTENCE_FINAL:
            return current

        # Pause boundary
        next_word = words[current + 1]
        silence_gap = float(next_word["start"]) - float(curr_word["end"])
        if silence_gap > 1.5:
            return current

        current += 1

    return n - 1


def text_in_range(words: list[dict], start: float, end: float) -> str:
    """
    Extract and join word text for all words within the time range
    ``[start, end)`` (seconds).

    Uses *end > start* semantics: a word is included when its ``end``
    timestamp is greater than ``start`` AND its ``start`` timestamp is
    less than ``end``.  This matches standard half-open interval logic
    and is consistent with Whisper's timestamp conventions.

    Args:
        words: Flat word list from ``transcript.json``.
        start: Range start in seconds (inclusive-ish).
        end:   Range end in seconds (exclusive-ish).

    Returns:
        Cleaned joined string of all matching words.
    """
    parts = [
        str(w.get("word", "")).strip()
        for w in words
        if (
            float(w.get("end", 0.0)) > start
            and float(w.get("start", 0.0)) < end
            and str(w.get("word", "")).strip()
        )
    ]
    return clean_text(" ".join(parts))


def get_nearest_word_index(words: list[dict], time: float) -> int:
    """
    Return the index of the word whose ``start`` time is closest to ``time``.

    Args:
        words: Flat word list from ``transcript.json``.
        time:  Target time in seconds.

    Returns:
        Best-matching index.  Returns 0 for an empty list.
    """
    if not words:
        return 0
    best_idx = 0
    best_diff = abs(float(words[0].get("start", 0.0)) - time)
    for idx, w in enumerate(words[1:], start=1):
        diff = abs(float(w.get("start", 0.0)) - time)
        if diff < best_diff:
            best_diff = diff
            best_idx = idx
    return best_idx


def word_is_sentence_final(word_dict: dict) -> bool:
    """
    Return True when the word text ends with a sentence-final punctuation mark.

    Args:
        word_dict: A single word dict from the flat word list.

    Returns:
        True if the last character of the word is in ``SENTENCE_FINAL``.
    """
    text = str(word_dict.get("word", "")).strip()
    return bool(text) and text[-1] in SENTENCE_FINAL


def word_is_connector(word_dict: dict) -> bool:
    """
    Return True when the word is a connector/conjunction.

    A clip boundary at a connector word is at a poor semantic position
    because the sentence is clearly continuing.

    Args:
        word_dict: A single word dict from the flat word list.

    Returns:
        True if the lower-cased, punctuation-stripped word is in
        ``CONNECTOR_WORDS``.
    """
    text = re.sub(r"[^a-zA-Z']", "", str(word_dict.get("word", ""))).lower()
    return text in CONNECTOR_WORDS


def silence_gap_before(words: list[dict], idx: int) -> float:
    """
    Return the silence gap (seconds) between words[idx-1].end and words[idx].start.

    Returns 0.0 when ``idx <= 0`` or the gap is negative.

    Args:
        words: Flat word list.
        idx:   Index of the word whose preceding gap to measure.

    Returns:
        Silence duration in seconds (>= 0.0).
    """
    if idx <= 0 or idx >= len(words):
        return 0.0
    gap = float(words[idx]["start"]) - float(words[idx - 1]["end"])
    return max(0.0, gap)


def silence_gap_after(words: list[dict], idx: int) -> float:
    """
    Return the silence gap (seconds) between words[idx].end and words[idx+1].start.

    Returns 0.0 when ``idx >= len(words) - 1`` or the gap is negative.

    Args:
        words: Flat word list.
        idx:   Index of the word whose following gap to measure.

    Returns:
        Silence duration in seconds (>= 0.0).
    """
    if idx < 0 or idx >= len(words) - 1:
        return 0.0
    gap = float(words[idx + 1]["start"]) - float(words[idx]["end"])
    return max(0.0, gap)


# ===========================================================================
# Whisper confidence analysis
# ===========================================================================

def compute_whisper_confidence_region(
    words: list[dict],
    start: float,
    end: float,
    boundary_window_sec: float = 2.0,
    low_confidence_threshold: float = 0.65,
    critical_threshold: float = 0.50,
) -> dict:
    """
    Compute Whisper transcription confidence statistics for a clip region.

    The ``probability`` field on each Whisper word represents the model's
    confidence that it transcribed the word correctly.  Low-probability
    words are potential hallucinations or acoustically uncertain regions.
    Boundaries landing in low-confidence zones produce unreliable clip
    start/end points.

    Args:
        words:                  Flat word list from ``transcript.json``.
        start:                  Clip start time in seconds.
        end:                    Clip end time in seconds.
        boundary_window_sec:    Seconds around each boundary to inspect for
                                critical low-confidence words.
        low_confidence_threshold: Words below this probability are counted
                                  as low-confidence.
        critical_threshold:     Words below this probability at a boundary
                                trigger ``low_confidence_at_boundary = True``.

    Returns:
        Dict with keys::

            start_word_confidence   float  Mean probability of words in first 1s
            end_word_confidence     float  Mean probability of words in last 1s
            region_avg              float  Mean probability across the full region
            low_confidence_word_count int  Words below low_confidence_threshold
            low_confidence_at_boundary bool  Any boundary word below critical_threshold
    """
    region_words = [
        w for w in words
        if float(w.get("end", 0.0)) > start and float(w.get("start", 0.0)) < end
    ]

    if not region_words:
        return {
            "start_word_confidence": 1.0,
            "end_word_confidence": 1.0,
            "region_avg": 1.0,
            "low_confidence_word_count": 0,
            "low_confidence_at_boundary": False,
        }

    confidences = [float(w.get("probability", 1.0)) for w in region_words]
    region_avg = sum(confidences) / len(confidences)
    low_confidence_count = sum(1 for c in confidences if c < low_confidence_threshold)

    # Boundary inspection
    start_boundary_words = [
        w for w in region_words
        if float(w.get("start", 0.0)) < start + boundary_window_sec
    ]
    end_boundary_words = [
        w for w in region_words
        if float(w.get("end", 0.0)) > end - boundary_window_sec
    ]
    boundary_words = start_boundary_words + end_boundary_words
    low_confidence_at_boundary = any(
        float(w.get("probability", 1.0)) < critical_threshold
        for w in boundary_words
    )

    # Per-boundary averages (first 1s / last 1s)
    start_words_1s = [
        w for w in region_words
        if float(w.get("start", 0.0)) < start + 1.0
    ]
    end_words_1s = [
        w for w in region_words
        if float(w.get("end", 0.0)) > end - 1.0
    ]

    start_conf = (
        sum(float(w.get("probability", 1.0)) for w in start_words_1s) / len(start_words_1s)
        if start_words_1s else 1.0
    )
    end_conf = (
        sum(float(w.get("probability", 1.0)) for w in end_words_1s) / len(end_words_1s)
        if end_words_1s else 1.0
    )

    return {
        "start_word_confidence": round(start_conf, 4),
        "end_word_confidence": round(end_conf, 4),
        "region_avg": round(region_avg, 4),
        "low_confidence_word_count": low_confidence_count,
        "low_confidence_at_boundary": low_confidence_at_boundary,
    }


# ===========================================================================
# Speech rate analysis
# ===========================================================================

def compute_speech_rate_wpm(
    words: list[dict],
    start: float,
    end: float,
) -> float:
    """
    Compute words per minute for a time range.

    Args:
        words: Flat word list from ``transcript.json``.
        start: Range start in seconds.
        end:   Range end in seconds.

    Returns:
        Words per minute.  Returns 0.0 if the range is shorter than 1 second.
    """
    duration_minutes = (end - start) / 60.0
    if duration_minutes < 1 / 60:   # < 1 second → undefined
        return 0.0
    region_words = [
        w for w in words
        if float(w.get("end", 0.0)) > start and float(w.get("start", 0.0)) < end
    ]
    return round(len(region_words) / duration_minutes, 1)


# ===========================================================================
# Content word analysis
# ===========================================================================

def extract_content_words(text: str) -> list[str]:
    """
    Extract content words (non-stop-words) from a text string.

    Content words are lowercase tokens longer than 2 characters that are
    not in ``STOP_WORDS``.  These form the semantic fingerprint of a clip
    and are used for topic-similarity (Jaccard) comparisons.

    Args:
        text: Raw text string.

    Returns:
        List of lowercase content word tokens.
    """
    tokens = re.findall(r"[a-zA-Z']+", text.lower())
    return [t for t in tokens if t not in STOP_WORDS and len(t) > 2]


def compute_information_density(text: str, duration_sec: float) -> float:
    """
    Compute the information density of a clip.

    Information density = unique content words per minute.  Higher values
    indicate educational or substantive content; very low values suggest
    filler, repetition, or silence-heavy sections.

    Args:
        text:         Full transcript text of the clip.
        duration_sec: Clip duration in seconds.

    Returns:
        Unique content words per minute (float).  Returns 0.0 for very
        short durations to avoid division-by-near-zero artefacts.
    """
    if duration_sec < 1.0:
        return 0.0
    unique_content_words = set(extract_content_words(text))
    return round(len(unique_content_words) / (duration_sec / 60.0), 2)


def jaccard_similarity(text_a: str, text_b: str) -> float:
    """
    Compute Jaccard similarity between two text strings using content words.

    Used for topic deduplication in Pass 7: if two clips share more than
    60% of their content vocabulary, they are likely discussing the same topic.

    Jaccard(A, B) = |A ∩ B| / |A ∪ B|

    Args:
        text_a: First text string.
        text_b: Second text string.

    Returns:
        Similarity score between 0.0 (completely different) and 1.0 (identical).
    """
    words_a = set(extract_content_words(text_a))
    words_b = set(extract_content_words(text_b))

    if not words_a and not words_b:
        return 1.0
    if not words_a or not words_b:
        return 0.0

    intersection = len(words_a & words_b)
    union = len(words_a | words_b)
    return round(intersection / union, 4)


# ===========================================================================
# Semantic signal detection
# ===========================================================================

def detect_emotion_valence(text: str) -> str:
    """
    Classify the dominant emotional valence of a text block.

    Uses a lightweight vocabulary-based approach with no external models.
    Humorous and solemn content is weighted higher because those emotions
    are more distinctive and less ambiguous than positive/negative polarity.

    Args:
        text: Text to analyse.

    Returns:
        One of: ``"positive"`` | ``"negative"`` | ``"excited"`` |
        ``"solemn"`` | ``"humorous"`` | ``"neutral"``.
    """
    words_lower = set(re.findall(r"[a-z]+", text.lower()))

    scores: dict[str, float] = {
        "humorous": len(words_lower & _HUMOROUS_WORDS) * 3.0,
        "solemn":   len(words_lower & _SOLEMN_WORDS)   * 2.5,
        "excited":  len(words_lower & _EXCITED_WORDS)  * 2.0,
        "positive": len(words_lower & _POSITIVE_WORDS) * 1.0,
        "negative": len(words_lower & _NEGATIVE_WORDS) * 1.0,
    }

    best = max(scores, key=scores.get)  # type: ignore[arg-type]
    return best if scores[best] > 0 else "neutral"


def detect_emotion_intensity(text: str) -> float:
    """
    Compute an emotional intensity score for a text block.

    Measures the proportion of words that carry emotional signal.

    Args:
        text: Text to analyse.

    Returns:
        Float 0.0–1.0.  Higher values indicate more emotionally loaded text.
    """
    words = re.findall(r"[a-z]+", text.lower())
    if not words:
        return 0.0
    emotional_count = sum(1 for w in words if w in _ALL_EMOTIONAL_WORDS)
    return round(min(emotional_count / len(words), 1.0), 4)


def detect_transition_phrase(text: str) -> bool:
    """
    Return True if ``text`` contains a known topic-transition phrase.

    The check is done on the lower-cased text to catch phrase at any
    position in the turn (start, middle, or end).

    Args:
        text: Speaker turn text.

    Returns:
        True if a transition phrase is detected.
    """
    text_lower = text.lower()
    return any(phrase in text_lower for phrase in TRANSITION_PHRASES)


def detect_conclusion_signal(text: str) -> bool:
    """
    Return True if ``text`` contains a known conclusion/wrap-up signal.

    Args:
        text: Speaker turn text.

    Returns:
        True if a conclusion signal is found.
    """
    text_lower = text.lower()
    return any(signal in text_lower for signal in CONCLUSION_SIGNALS)


def is_question_starter(text: str) -> bool:
    """
    Return True if the text begins with a question-starter word.

    Used in Pass 1 role detection to identify ``question`` turns.

    Args:
        text: Speaker turn text (leading whitespace is stripped).

    Returns:
        True if the first word (alpha characters only) is in
        ``QUESTION_STARTERS``.
    """
    match = re.match(r"[a-zA-Z']+", text.strip())
    if not match:
        return False
    return match.group(0).lower() in QUESTION_STARTERS


def has_floating_pronoun(text: str) -> bool:
    """
    Return True if the text begins with an unresolved (floating) pronoun.

    A floating pronoun at the start of a clip means the viewer doesn't
    know who or what is being referred to — a strong signal of missing
    context that lowers the hook strength and context completeness scores.

    Args:
        text: Clip text (should be the clip's opening sentence).

    Returns:
        True if the first word is in ``FLOATING_PRONOUNS``.
    """
    match = re.match(r"[a-zA-Z']+", text.strip())
    if not match:
        return False
    return match.group(0).lower() in FLOATING_PRONOUNS


def detect_viral_type(text: str) -> str:
    """
    Detect the most likely viral content type from vocabulary signals.

    Patterns are checked in editorial priority order — the type with the
    strongest audience retention signal is returned first when multiple
    signals co-occur.

    Args:
        text: Full text of the clip.

    Returns:
        Viral type string from the standard taxonomy.
        Falls back to ``"story_hook"`` when no pattern is detected.
    """
    text_lower = text.lower()
    for viral_type, phrases in _VIRAL_PATTERNS:
        if any(phrase in text_lower for phrase in phrases):
            return viral_type

    # Final heuristic: high emotional intensity → emotional_peak
    if detect_emotion_intensity(text) > 0.15:
        valence = detect_emotion_valence(text)
        if valence in ("solemn", "excited"):
            return "emotional_peak"
        if valence == "humorous":
            return "humor"

    return "story_hook"


def count_question_marks(text: str) -> int:
    """Return the number of question marks in ``text``."""
    return text.count("?")


def count_exclamation_marks(text: str) -> int:
    """Return the number of exclamation marks in ``text``."""
    return text.count("!")


def first_sentence(text: str, max_words: int = 20) -> str:
    """
    Extract the first sentence from ``text``.

    Splits on the first ``.``, ``?``, or ``!`` followed by whitespace or
    end-of-string.  Falls back to the first ``max_words`` words if no
    sentence boundary is found.

    Args:
        text:      Source text.
        max_words: Fallback word limit if no sentence boundary is found.

    Returns:
        The first sentence (or first ``max_words`` words).
    """
    match = re.search(r"[.?!](?:\s|$)", text)
    if match:
        return text[: match.start() + 1].strip()
    words = text.split()
    return " ".join(words[:max_words])
