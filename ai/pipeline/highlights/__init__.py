"""
Editorial Intelligence Highlight Selection System
=================================================

This package contains the production-grade highlight selection pipeline
that replaces the monolithic stage_04_highlights.py with a modular,
semantic-first 8-pass architecture.

Architecture overview
---------------------
Each "pass" is a self-contained module that reads from the previous
pass's JSON output and writes its own intermediate JSON file.  All
passes share the dataclass definitions in ``schemas`` and the pure
utility functions in ``text_utils``.  LLM communication is routed
through the provider abstraction in ``llm_provider`` so any backend
(Ollama, OpenAI, Anthropic, …) can be swapped at configuration time.

Modules
-------
schemas
    Typed dataclass definitions for every intermediate data structure
    produced and consumed by the 8 passes.

llm_provider
    Abstract LLM provider interface with concrete implementations for
    Ollama (local), and a NullProvider for heuristic-only mode.

text_utils
    Pure, dependency-free text utility functions: sentence boundary
    detection, Whisper confidence analysis, Jaccard similarity, emotion
    detection, viral-type classification, and more.

The following modules will be added in subsequent phases:

intent_detector        (Phase B)  Pass 0 — video content-type classification
conversation_blocks    (Phase C)  Pass 1 — speaker turn grouping + memory
semantic_segmenter     (Phase D)  Pass 2 — semantic topic detection
clip_candidate_builder (Phase E)  Pass 3 — dynamic boundary computation
boundary_refiner       (Phase F)  Pass 4 — iterative boundary refinement
llm_highlights         (Phase G)  Pass 5 — LLM editorial evaluation
editorial_scorer       (Phase H)  Pass 6 — multi-dimensional scoring + tiers
editorial_qa           (Phase I)  Pass 7 — QA gate + topic deduplication
editorial_selector     (Phase J)  Pass 8 — final selection → highlights.json

Backward compatibility
----------------------
The final output of Pass 8 (highlights.json) preserves the exact same
schema consumed by downstream stages 05–15.  No downstream stage requires
any modification.
"""
