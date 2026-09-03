"""
Camera Pipeline Unit & Integration Tests
==========================================
Validates the three camera pipeline fixes:
1. stage_08b: Anchor backfill (initial lost frames get first valid position)
2. stage_08c: Camera freeze on lost anchors + first-frame snap
3. stage_08d: Hermite transition window clamping at clip boundaries
"""
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

passed = 0
failed = 0

def check(label, condition):
    global passed, failed
    if condition:
        print(f"  [PASS] {label}")
        passed += 1
    else:
        print(f"  [FAIL] {label}")
        failed += 1


# ═══════════════════════════════════════════════════════════════════════
# TEST 1: Anchor Backfill (stage_08b)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 1. Anchor Backfill (stage_08b) ---")

from stages.stage_08b_anchor_stream import _merge_anchor_samples, _median_smooth

# Simulate: frames at 0.0, 0.5, 1.0, 1.5, 2.0
# Face detection only at t=1.0 and t=2.0 (first 2 frames have no detection)
frame_times = [0.0, 0.5, 1.0, 1.5, 2.0]
face_samples = [
    {"time": 1.0, "bbox": [800.0, 200.0, 100.0, 140.0], "confidence": 0.95, "source": "face"},
    {"time": 2.0, "bbox": [810.0, 205.0, 100.0, 140.0], "confidence": 0.92, "source": "face"},
]
body_samples = []

raw_anchors = _merge_anchor_samples(face_samples, body_samples, 0.0, 2.0, frame_times)

check("Frame 0 is backfilled (not lost)", raw_anchors[0].get("source") == "backfill")
check("Frame 1 is backfilled or matched (not lost)", raw_anchors[1].get("source") in ("backfill", "face", "body", "carried"))
check("Frame 2 is the first real detection", raw_anchors[2].get("source") == "face")
check("Backfilled frame 0 has valid anchorX", raw_anchors[0].get("anchorX") is not None)
check("Backfilled frame 0 anchorX matches first face",
      abs(raw_anchors[0]["anchorX"] - raw_anchors[2]["anchorX"]) < 0.01)
check("Backfilled frame 0 anchorY matches first face",
      abs(raw_anchors[0]["anchorY"] - raw_anchors[2]["anchorY"]) < 0.01)
check("Backfilled confidence is reduced (0.8x)",
      raw_anchors[0]["confidence"] < raw_anchors[2]["confidence"])

# Test median smoothing with backfilled anchors
smoothed = _median_smooth(raw_anchors)
check("Median smoother output has same length as input", len(smoothed) == len(raw_anchors))
check("EMA frame 0 has valid anchorX (not None)", smoothed[0].get("anchorX") is not None)


# ═══════════════════════════════════════════════════════════════════════
# TEST 2: No backfill needed (all frames have detections)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 2. No Backfill When All Frames Have Detections ---")

face_samples_full = [
    {"time": 0.0, "bbox": [800.0, 200.0, 100.0, 140.0], "confidence": 0.95, "source": "face"},
    {"time": 0.5, "bbox": [805.0, 202.0, 100.0, 140.0], "confidence": 0.93, "source": "face"},
    {"time": 1.0, "bbox": [810.0, 205.0, 100.0, 140.0], "confidence": 0.92, "source": "face"},
]
raw_full = _merge_anchor_samples(face_samples_full, [], 0.0, 1.0, [0.0, 0.5, 1.0])
check("No backfill when first frame has detection", raw_full[0].get("source") == "face")
check("All frames are face-sourced", all(a.get("source") == "face" for a in raw_full))


# ═══════════════════════════════════════════════════════════════════════
# TEST 3: Camera Freeze on Lost Anchor (stage_08c)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 3. Camera Freeze on Lost Anchor (stage_08c) ---")

from stages.stage_08c_camera_operator import _compute_target, _crop_dims

# Verify _compute_target returns center-crop when anchor is None
src_w, src_h = 1920, 1080
crop_w, crop_h = _crop_dims(src_w, src_h, 1.16)
tx_lost, ty_lost = _compute_target(
    {"anchorX": None, "anchorY": None}, src_w, src_h, crop_w, crop_h
)
center_x = (src_w - crop_w) / 2.0
center_y = (src_h - crop_h) / 2.0
check("_compute_target returns center for None anchor",
      abs(tx_lost - center_x) < 0.1 and abs(ty_lost - center_y) < 0.1)

# Verify _compute_target returns correct position for valid anchor
tx_valid, ty_valid = _compute_target(
    {"anchorX": 800.0, "anchorY": 300.0, "faceHeight": 140.0},
    src_w, src_h, crop_w, crop_h,
)
check("_compute_target positions near anchor for valid face",
      abs(tx_valid - (800.0 - crop_w / 2.0)) < 50)


# ═══════════════════════════════════════════════════════════════════════
# TEST 4: Hermite Window Clamping (stage_08d)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 4. Hermite Window Clamping (stage_08d) ---")

from stages.stage_08d_transition_planner import _apply_hermite_transition

# Build mock frames: 5 frames at 0.0, 0.5, 1.0, 1.5, 2.0
mock_frames = []
for i, t in enumerate([0.0, 0.5, 1.0, 1.5, 2.0]):
    mock_frames.append({
        "time": t,
        "x": 500, "y": 200,
        "width": 520, "height": 926,
        "zoom": 1.16, "layout": "full-crop",
    })

# Save frame 0 original position
frame0_x_before = mock_frames[0]["x"]
frame0_y_before = mock_frames[0]["y"]

# Apply transition at t=0.0 (event at clip start — this used to cause the offset)
_apply_hermite_transition(mock_frames, 0.0, 0.25, 1920, 1080)

check("Frame 0 X unchanged after clamped transition at clip start",
      mock_frames[0]["x"] == frame0_x_before)
check("Frame 0 Y unchanged after clamped transition at clip start",
      mock_frames[0]["y"] == frame0_y_before)

# Build mock frames for transition in the middle (should still work normally)
mid_frames = []
for i, t in enumerate([0.0, 0.5, 1.0, 1.5, 2.0, 2.5, 3.0]):
    mid_frames.append({
        "time": t,
        "x": 500 + i * 10, "y": 200,
        "width": 520, "height": 926,
        "zoom": 1.16, "layout": "full-crop",
    })
mid_frame0_x = mid_frames[0]["x"]
_apply_hermite_transition(mid_frames, 1.5, 0.50, 1920, 1080)
check("Mid-clip transition does NOT affect frame 0", mid_frames[0]["x"] == mid_frame0_x)


# ═══════════════════════════════════════════════════════════════════════
# TEST 5: End-to-End Integration (08b -> 08c -> 08d)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 5. End-to-End Integration (08b -> 08c -> 08d) ---")

import stages.stage_08b_anchor_stream as stage08b
import stages.stage_08c_camera_operator as stage08c
import stages.stage_08d_transition_planner as stage08d

tmp_dir = Path(tempfile.mkdtemp())

# Setup mock data: subject clearly visible from frame 0 at x=800, y=300
metadata = {"width": 1920, "height": 1080, "duration": 10.0, "fps": 30.0}
(tmp_dir / "video_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

highlights = {
    "highlights": [
        {"id": "clip_01", "clipId": "clip_01", "clip_id": "clip_01",
         "start": 0.0, "end": 5.0, "duration": 5.0, "score": 0.9,
         "hook": "Test clip", "text": "Test clip text"}
    ]
}
(tmp_dir / "highlights.json").write_text(json.dumps(highlights), encoding="utf-8")

# Face tracks with detections starting at t=0.5 (NOT t=0)
# This simulates the cold-start gap where frame 0 has no detection
face_tracks = {
    "tracker": "bytetrack",
    "tracks": [{
        "trackId": 1,
        "detections": [
            {"time": 0.5, "bbox": [750, 180, 100, 140], "confidence": 0.95},
            {"time": 1.0, "bbox": [755, 182, 100, 140], "confidence": 0.94},
            {"time": 1.5, "bbox": [760, 184, 100, 140], "confidence": 0.93},
            {"time": 2.0, "bbox": [758, 183, 100, 140], "confidence": 0.95},
            {"time": 2.5, "bbox": [762, 185, 100, 140], "confidence": 0.94},
            {"time": 3.0, "bbox": [755, 182, 100, 140], "confidence": 0.93},
            {"time": 3.5, "bbox": [760, 184, 100, 140], "confidence": 0.95},
            {"time": 4.0, "bbox": [758, 183, 100, 140], "confidence": 0.94},
            {"time": 4.5, "bbox": [755, 182, 100, 140], "confidence": 0.93},
        ]
    }]
}
(tmp_dir / "face_tracks.json").write_text(json.dumps(face_tracks), encoding="utf-8")
(tmp_dir / "face_detections.json").write_text(json.dumps({"detections": []}), encoding="utf-8")

# Scene cuts at 2.5s (creates a transition event)
scene_cuts = {
    "scenes": [
        {"start": 0.0, "end": 2.5, "index": 0},
        {"start": 2.5, "end": 5.0, "index": 1},
    ]
}
(tmp_dir / "scene_cuts.json").write_text(json.dumps(scene_cuts), encoding="utf-8")

# No identity data (fallback to body tracking)
(tmp_dir / "subject_identities.json").write_text(json.dumps({"scenes": []}), encoding="utf-8")

# Shot plan with close shot
shot_plan = {
    "clips": [{
        "clipId": "clip_01",
        "start": 0.0, "end": 5.0,
        "segments": [
            {"start": 0.0, "end": 2.5, "shotType": "close", "layout": "full-crop"},
            {"start": 2.5, "end": 5.0, "shotType": "close", "layout": "full-crop"},
        ]
    }]
}
(tmp_dir / "shot_plan.json").write_text(json.dumps(shot_plan), encoding="utf-8")

context = {"temp_dir": tmp_dir, "settings": {}}

# Run Stage 08b
stage08b.run(context)
anchor_data = json.loads((tmp_dir / "anchor_curve.json").read_text(encoding="utf-8"))
clip_anchors = anchor_data["clips"][0]["anchors"]

check("Anchor curve generated", len(clip_anchors) > 0)
# Frame 0 should be backfilled, not lost
first_anchor = clip_anchors[0]
check("First anchor is NOT lost (backfilled or face)",
      first_anchor.get("source") in ("backfill", "face", "body"))
check("First anchor has valid anchorX", first_anchor.get("anchorX") is not None)

# Run Stage 08c
stage08c.run(context)
camera_data = json.loads((tmp_dir / "camera_curve.json").read_text(encoding="utf-8"))
clip_frames = camera_data["clips"][0]["frames"]

check("Camera curve generated", len(clip_frames) > 0)

# The critical test: frame 0 should be at the subject position, NOT frame center
frame0 = clip_frames[0]
frame_center_x = (1920 - frame0["width"]) / 2.0

# Subject is at x≈800, frame center is at x≈(1920-crop_w)/2≈437.
# The camera should be near the subject, NOT near frame center.
subject_x_approx = 800.0
center_offset = abs(frame0["x"] - frame_center_x)
subject_offset = abs(frame0["x"] - (subject_x_approx - frame0["width"] / 2.0))
check("Frame 0 camera is closer to subject than to frame center",
      subject_offset < center_offset)

# Check camera stability: frame 0 and frame 1 should be very close
# (no large jump from center to subject)
if len(clip_frames) > 1:
    frame1 = clip_frames[1]
    drift = abs(frame0["x"] - frame1["x"])
    check(f"Frame 0 -> 1 drift is small (<30px, got {drift}px)", drift < 30)
else:
    check("Frame 0 -> 1 drift check (skipped - single frame)", True)

# Run Stage 08d
stage08d.run(context)
camera_data_post = json.loads((tmp_dir / "camera_curve.json").read_text(encoding="utf-8"))
clip_frames_post = camera_data_post["clips"][0]["frames"]

frame0_post = clip_frames_post[0]
check("Frame 0 position preserved after transition planner",
      frame0_post["x"] == frame0["x"])


# ═══════════════════════════════════════════════════════════════════════
# TEST 6: Subject Stationary — Camera Should Be Stable
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 6. Camera Stability for Stationary Subject ---")

# Check that when the subject barely moves (±5px), the camera stays very stable
full_crop_frames = [f for f in clip_frames if f.get("layout") == "full-crop"]
if len(full_crop_frames) > 3:
    x_positions = [f["x"] for f in full_crop_frames]
    max_drift = max(x_positions) - min(x_positions)
    check(f"Total camera X drift for stationary subject is small (<40px, got {max_drift}px)",
          max_drift < 40)
    y_positions = [f["y"] for f in full_crop_frames]
    max_y_drift = max(y_positions) - min(y_positions)
    check(f"Total camera Y drift for stationary subject is small (<40px, got {max_y_drift}px)",
          max_y_drift < 40)
else:
    check("Camera stability check (skipped - too few frames)", True)
    check("Camera stability Y check (skipped - too few frames)", True)


# ═══════════════════════════════════════════════════════════════════════
# TEST 7: All Lost Anchors (no subject ever detected)
# ═══════════════════════════════════════════════════════════════════════
print("\n--- 7. All Lost Anchors (No Subject) ---")

raw_all_lost = _merge_anchor_samples([], [], 0.0, 2.0, [0.0, 0.5, 1.0, 1.5, 2.0])
check("All frames are 'lost' when no detections",
      all(a.get("source") == "lost" for a in raw_all_lost))
check("No backfill when no valid anchor exists",
      all(a.get("anchorX") is None for a in raw_all_lost))


# ═══════════════════════════════════════════════════════════════════════
# SUMMARY
# ═══════════════════════════════════════════════════════════════════════
print(f"\n{'='*70}")
print(f"Camera Pipeline Test Suite Complete")
print(f"  Passed: {passed}")
print(f"  Failed: {failed}")
print(f"{'='*70}")

if failed > 0:
    sys.exit(1)
