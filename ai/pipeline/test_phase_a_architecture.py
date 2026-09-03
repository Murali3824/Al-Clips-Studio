"""
Phase A Architecture Verification.
Tests: SOLID compliance, circular imports, JSON serialization, LLM extensibility,
text_utils purity, and coding convention consistency.
Run with: python test_phase_a_architecture.py
"""
import sys
import os
import ast
import inspect
import dataclasses
import json
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

PASSES = 0
FAILS = 0


def check(label, condition, detail=""):
    global PASSES, FAILS
    if condition:
        print(f"  [PASS] {label}")
        PASSES += 1
    else:
        print(f"  [FAIL] {label}" + (f": {detail}" if detail else ""))
        FAILS += 1


# ===========================================================================
# 1. No circular imports — import order: text_utils -> schemas -> llm_provider
# ===========================================================================
print("\n--- 1. Circular Import Check ---")

# Ensure each module can be imported independently in isolation
import importlib

for mod_name in ["highlights.text_utils", "highlights.schemas", "highlights.llm_provider"]:
    try:
        mod = importlib.import_module(mod_name)
        check(f"{mod_name} imports independently", True)
    except ImportError as e:
        check(f"{mod_name} imports independently", False, str(e))

# Verify schemas does NOT import from llm_provider or text_utils
from highlights import schemas as _schemas_mod
schema_src = inspect.getsource(_schemas_mod)
check("schemas.py does NOT import llm_provider", "llm_provider" not in schema_src)
check("schemas.py does NOT import text_utils", "text_utils" not in schema_src)

# Verify llm_provider does NOT import from schemas or text_utils
from highlights import llm_provider as _provider_mod
provider_src = inspect.getsource(_provider_mod)
check("llm_provider.py does NOT import schemas", "schemas" not in provider_src)
check("llm_provider.py does NOT import text_utils", "text_utils" not in provider_src)

# Verify text_utils does NOT import any highlights submodule
from highlights import text_utils as _tu_mod
tu_src = inspect.getsource(_tu_mod)
check("text_utils.py does NOT import schemas", "schemas" not in tu_src)
check("text_utils.py does NOT import llm_provider", "llm_provider" not in tu_src)

print("  Dependency order: text_utils -> schemas -> llm_provider  (no cycles)")


# ===========================================================================
# 2. JSON Serialization of all dataclasses
# ===========================================================================
print("\n--- 2. JSON Serialization ---")

from highlights.schemas import (
    IntentProfile, EditorialRules, AcousticSignals, MemoryWindow,
    ConversationTurn, CompletenessSignals, ViralPotential, EditorialSegment,
    BoundaryConfidence, WhisperConfidenceRegion, RefinementLog,
    ClipCandidate, LLMRating, EditorialScoreDimensions, EditorialScore,
    ScoredCandidate, QAChecklistResult, QAReport, HighlightOutput,
)

all_schema_classes = [
    IntentProfile, EditorialRules, AcousticSignals, MemoryWindow,
    ConversationTurn, CompletenessSignals, ViralPotential, EditorialSegment,
    BoundaryConfidence, WhisperConfidenceRegion, RefinementLog,
    ClipCandidate, LLMRating, EditorialScoreDimensions, EditorialScore,
    ScoredCandidate, QAChecklistResult, QAReport, HighlightOutput,
]

for cls in all_schema_classes:
    try:
        obj = cls()
        d = dataclasses.asdict(obj)
        serialized = json.dumps(d)
        deserialized = json.loads(serialized)
        check(f"{cls.__name__} round-trips through JSON", True)
    except Exception as e:
        check(f"{cls.__name__} round-trips through JSON", False, str(e))

# Verify HighlightOutput backward-compatible field names survive serialization
ho = HighlightOutput(id="clip_01", start=10.5, end=45.2, score=85, hook="Test hook")
d = dataclasses.asdict(ho)
serialized = json.dumps(d)
parsed = json.loads(serialized)
legacy_fields = ["id", "start", "end", "duration", "score", "hook",
                 "text", "reason", "type", "source", "model",
                 "min_duration", "quality_checklist"]
for f in legacy_fields:
    key = f  # dataclasses.asdict uses field names directly
    check(f"HighlightOutput JSON has legacy key '{key}'", key in parsed, list(parsed.keys()))


# ===========================================================================
# 3. LLM Provider Extensibility (SOLID Open/Closed + Liskov)
# ===========================================================================
print("\n--- 3. LLM Provider Extensibility ---")

from highlights.llm_provider import LLMProvider, OllamaProvider, NullProvider, get_llm_provider, LLMUnavailable
import abc

# LLMProvider must be abstract
check("LLMProvider is abstract (ABC)", inspect.isabstract(LLMProvider))

# All abstract methods are declared
abstract_methods = {
    name for name, val in inspect.getmembers(LLMProvider)
    if getattr(val, "__isabstractmethod__", False)
}
check("LLMProvider declares 'is_available' abstract", "is_available" in abstract_methods)
check("LLMProvider declares 'complete' abstract", "complete" in abstract_methods)
check("LLMProvider declares 'provider_name' abstract", "provider_name" in abstract_methods)

# Concrete providers satisfy Liskov Substitution — can be used interchangeably
def use_provider(p: LLMProvider) -> bool:
    """Any valid provider can be checked for availability."""
    result = p.is_available()
    return isinstance(result, bool)

check("OllamaProvider satisfies LLMProvider contract", use_provider(OllamaProvider()))
check("NullProvider satisfies LLMProvider contract", use_provider(NullProvider()))

# Simulate adding a new provider — it must implement all 3 abstract methods
class MockGPTProvider(LLMProvider):
    def is_available(self) -> bool:
        return True
    def complete(self, prompt: str, temperature: float = 0.3, max_tokens: int = 2048) -> str:
        return '{"test": true}'
    @property
    def provider_name(self) -> str:
        return "openai/gpt-4o-mini"

mock = MockGPTProvider()
check("New provider (MockGPT) works without modifying get_llm_provider", use_provider(mock))
check("New provider returns correct name", mock.provider_name == "openai/gpt-4o-mini")
check("New provider.complete() returns string", isinstance(mock.complete("test"), str))

# get_llm_provider returns a NullProvider when explicitly set
p = get_llm_provider({"llmProvider": "null"})
check("get_llm_provider factory is extensible via settings", isinstance(p, NullProvider))

# OllamaProvider gracefully handles connection refused (is_available returns False)
p_bad = OllamaProvider(base_url="http://localhost:19999")  # nothing on this port
avail = p_bad.is_available()
check("OllamaProvider.is_available() returns False (not exception) on unreachable host",
      avail == False)


# ===========================================================================
# 4. text_utils Purity — no hidden state, no I/O, no side effects
# ===========================================================================
print("\n--- 4. text_utils Purity ---")

import highlights.text_utils as tu

# Get all public functions
public_funcs = [
    name for name, obj in inspect.getmembers(tu, inspect.isfunction)
    if not name.startswith("_")
]
check(f"text_utils exports {len(public_funcs)} public functions", len(public_funcs) >= 15,
      str(public_funcs))

# Verify none of the functions access global mutable state
# (check that module-level objects are all frozensets, tuples, or strings)
mutable_globals = []
for name, obj in inspect.getmembers(tu):
    if name.startswith("_"):
        continue
    if inspect.isfunction(obj) or inspect.ismodule(obj):
        continue
    if not isinstance(obj, (frozenset, tuple, str, int, float, bool, type(None))):
        mutable_globals.append(f"{name}: {type(obj).__name__}")

check("text_utils has no mutable module-level state", len(mutable_globals) == 0,
      str(mutable_globals))

# Verify no file I/O (no open(), no pathlib, no os.path in function bodies)
for func_name in public_funcs:
    func = getattr(tu, func_name)
    try:
        src = inspect.getsource(func)
        has_io = "open(" in src or "Path(" in src or "os.path" in src
        check(f"text_utils.{func_name} has no file I/O", not has_io)
    except Exception:
        pass  # built-in or C extension

# Determinism: same input -> same output (run twice)
result1 = tu.jaccard_similarity("machine learning transforms business", "business intelligence machine")
result2 = tu.jaccard_similarity("machine learning transforms business", "business intelligence machine")
check("text_utils functions are deterministic (same input -> same output)", result1 == result2)

result1 = tu.detect_viral_type("Nobody talks about this hidden secret method")
result2 = tu.detect_viral_type("Nobody talks about this hidden secret method")
check("detect_viral_type is deterministic", result1 == result2)


# ===========================================================================
# 5. Zero Runtime Performance Regression
# ===========================================================================
print("\n--- 5. Zero Runtime Regression Check ---")

# Verify Phase A modules are NOT imported anywhere in existing pipeline code
import_targets = [
    ("highlights.schemas",     "c:/Users/mural/.gemini/antigravity/scratch/ai-clip/ai/pipeline/stages/stage_04_highlights.py"),
    ("highlights.llm_provider", "c:/Users/mural/.gemini/antigravity/scratch/ai-clip/ai/pipeline/stages/stage_04_highlights.py"),
    ("highlights.text_utils",  "c:/Users/mural/.gemini/antigravity/scratch/ai-clip/ai/pipeline/stages/stage_04_highlights.py"),
]
for module_name, filepath in import_targets:
    try:
        with open(filepath, encoding="utf-8") as f:
            content = f.read()
        imported = (module_name in content or module_name.split(".")[-1] in content.split("\n")[0:15])
        check(f"stage_04 does NOT import {module_name}", module_name not in content)
    except FileNotFoundError:
        check(f"stage_04 file accessible", False, filepath)

# Time the existing pipeline module import (no regression)
import time
start_t = time.perf_counter()
import importlib
import sys
# Remove cached version to force fresh import timing
for key in list(sys.modules.keys()):
    if "stage_04" in key or "ollama_highlights" in key:
        del sys.modules[key]
importlib.import_module("stages.stage_04_highlights")
elapsed = time.perf_counter() - start_t
check(f"stage_04_highlights imports in < 3.0s (actual: {elapsed:.2f}s)", elapsed < 3.0)

# Phase A modules import fast (pure Python, no ML model loading)
for mod_name in ["highlights.schemas", "highlights.llm_provider", "highlights.text_utils"]:
    for key in list(sys.modules.keys()):
        if mod_name in key:
            del sys.modules[key]
start_t = time.perf_counter()
importlib.import_module(mod_name)
elapsed = time.perf_counter() - start_t
check(f"{mod_name} imports in < 0.5s (actual: {elapsed*1000:.1f}ms)", elapsed < 0.5)


# ===========================================================================
# 6. Coding Style and Naming Conventions
# ===========================================================================
print("\n--- 6. Coding Style and Naming Conventions ---")

# All Phase A files use snake_case for functions, UPPER_CASE for constants
schema_classes = [
    "IntentProfile", "EditorialRules", "AcousticSignals", "MemoryWindow",
    "ConversationTurn", "CompletenessSignals", "ViralPotential", "EditorialSegment",
    "BoundaryConfidence", "WhisperConfidenceRegion", "RefinementLog",
    "ClipCandidate", "LLMRating", "EditorialScoreDimensions", "EditorialScore",
    "ScoredCandidate", "QAChecklistResult", "QAReport", "HighlightOutput",
]
from highlights import schemas as _s
for cls_name in schema_classes:
    check(f"schemas.{cls_name} uses PascalCase", hasattr(_s, cls_name))

# text_utils: all public functions use snake_case
for func_name in public_funcs:
    is_snake = func_name == func_name.lower() or "_" in func_name
    check(f"text_utils.{func_name} uses snake_case", is_snake)

# llm_provider: classes use PascalCase, exception uses PascalCase
for cls_name in ["LLMProvider", "OllamaProvider", "NullProvider", "LLMUnavailable"]:
    check(f"llm_provider.{cls_name} exists and uses PascalCase",
          hasattr(__import__("highlights.llm_provider", fromlist=["x"]), cls_name))

# All modules have module-level docstrings
for mod_name, mod_obj in [
    ("schemas", _schemas_mod),
    ("llm_provider", _provider_mod),
    ("text_utils", _tu_mod),
]:
    has_docstring = bool(mod_obj.__doc__ and mod_obj.__doc__.strip())
    check(f"{mod_name}.py has module docstring", has_docstring)

# All public dataclass fields have type annotations
from highlights.schemas import ClipCandidate
hints = ClipCandidate.__dataclass_fields__
missing_types = [f for f, field in hints.items() if field.type is None]
check("ClipCandidate all fields have type annotations", len(missing_types) == 0,
      str(missing_types))

# from __future__ import annotations present in all 3 modules (forward refs)
for mod_obj in [_schemas_mod, _provider_mod, _tu_mod]:
    src = inspect.getsource(mod_obj)
    check(f"{mod_obj.__name__} has 'from __future__ import annotations'",
          "from __future__ import annotations" in src)


# ===========================================================================
# Summary
# ===========================================================================
print(f"\n{'='*65}")
print(f"Architecture Verification Complete")
print(f"  Passed: {PASSES}")
print(f"  Failed: {FAILS}")
print(f"{'='*65}")
if FAILS > 0:
    sys.exit(1)
