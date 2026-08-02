"""
Frame-by-Frame Camera Forensic Trace
=====================================
Traces the REAL production camera state through every stage of the pipeline
for one or more actual clips from a real pipeline run. Compares:

  - Stage 08b anchor positions (where the camera SHOULD point)
  - Stage 08c camera curve positions (what the camera operator computed)
  - Stage 08d post-transition positions (final rendered camera state)
  - Stage 09 render consumption (what the renderer actually uses)

For each frame, reports:
  - Anchor source (face/body/backfill/carried/lost)
  - Anchor X/Y (desired subject center)
  - Camera X/Y (computed crop top-left)
  - Delta from previous frame (drift)
  - Whether it snapped, smoothed, or froze
"""

import json
import sys
import os
from pathlib import Path

# ── Pick the most recent real job ─────────────────────────────────────
TEMP_BASE = Path(r"C:\Users\mural\.gemini\antigravity\scratch\ai-clip\storage\temp")

# Use the most recently modified temp dir
job_dirs = sorted(TEMP_BASE.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
if not job_dirs:
    print("ERROR: No temp directories found.")
    sys.exit(1)

# Find a job with all required files
job_dir = None
for d in job_dirs:
    required = ["anchor_curve.json", "camera_curve.json", "highlights.json", "video_metadata.json"]
    if all((d / f).exists() for f in required):
        job_dir = d
        break

if not job_dir:
    print("ERROR: No job directory with all required files found.")
    sys.exit(1)

print(f"Job: {job_dir.name}")
print(f"Path: {job_dir}")

# ── Load all artifacts ────────────────────────────────────────────────
metadata = json.loads((job_dir / "video_metadata.json").read_text(encoding="utf-8"))
highlights = json.loads((job_dir / "highlights.json").read_text(encoding="utf-8"))
anchor_data = json.loads((job_dir / "anchor_curve.json").read_text(encoding="utf-8"))
camera_data = json.loads((job_dir / "camera_curve.json").read_text(encoding="utf-8"))
crop_data = json.loads((job_dir / "crop_coords.json").read_text(encoding="utf-8"))

src_w = int(metadata["width"])
src_h = int(metadata["height"])
fps = float(metadata.get("fps", 30.0))
print(f"Source: {src_w}x{src_h} @ {fps}fps")

# Also load face detections + identity data for cross-reference
face_dets_path = job_dir / "face_detections.json"
face_dets = json.loads(face_dets_path.read_text(encoding="utf-8")) if face_dets_path.exists() else {}
identity_path = job_dir / "subject_identities.json"
identity_data = json.loads(identity_path.read_text(encoding="utf-8")) if identity_path.exists() else {}

# Index artifacts by clipId
anchor_clips = {c["clipId"]: c for c in anchor_data.get("clips", [])}
camera_clips = {c["clipId"]: c for c in camera_data.get("clips", [])}
crop_plans = {p["clipId"]: p for p in crop_data.get("plans", [])}

# Get the actual highlights list
hl_list = highlights.get("highlights", [])
print(f"Clips: {len(hl_list)}")
print()

# ── Forensic trace for each clip ──────────────────────────────────────
for hl in hl_list:
    clip_id = hl.get("id") or hl.get("clipId") or hl.get("clip_id")
    clip_start = float(hl["start"])
    clip_end = float(hl["end"])
    print(f"{'='*80}")
    print(f"CLIP: {clip_id}  [{clip_start:.3f}s - {clip_end:.3f}s]  duration={clip_end-clip_start:.1f}s")
    print(f"{'='*80}")

    # ── 1. Find face detections near clip start ───────────────────────
    # Check if there are face detections at/near t=clip_start
    all_face_dets = face_dets.get("detections", [])
    early_dets = [d for d in all_face_dets
                  if clip_start <= float(d.get("time", -1)) <= clip_start + 1.0]
    print(f"\n  Face detections in first 1.0s: {len(early_dets)}")
    for d in early_dets[:5]:
        t = float(d["time"])
        bbox = d.get("bbox", [])
        conf = float(d.get("confidence", 0))
        cx = float(bbox[0]) + float(bbox[2]) / 2.0 if len(bbox) >= 4 else "?"
        print(f"    t={t:.3f}s  center_x={cx}  conf={conf:.2f}")

    # ── 2. Find identity faces near clip start ────────────────────────
    identity_faces_early = []
    for scene in identity_data.get("scenes", []):
        for ident in scene.get("identities", []):
            for det in ident.get("detections", []):
                t = float(det.get("time", -1))
                if clip_start <= t <= clip_start + 1.0:
                    identity_faces_early.append(det)
    print(f"  Identity faces in first 1.0s: {len(identity_faces_early)}")
    for d in identity_faces_early[:5]:
        t = float(d["time"])
        bbox = d.get("bbox", [])
        conf = float(d.get("confidence", 0))
        cx = float(bbox[0]) + float(bbox[2]) / 2.0 if len(bbox) >= 4 else "?"
        print(f"    t={t:.3f}s  center_x={cx}  conf={conf:.2f}")

    # ── 3. Trace anchor stream (08b) ──────────────────────────────────
    ac = anchor_clips.get(clip_id, {})
    anchors = ac.get("anchors", [])
    print(f"\n  STAGE 08B: Anchor Stream ({len(anchors)} frames)")
    print(f"  {'Frame':>5} {'Time':>8} {'Source':>10} {'AnchorX':>9} {'AnchorY':>9} {'Conf':>6} {'DeltaX':>8}")

    prev_ax = None
    first_valid_anchor_t = None
    first_valid_anchor_x = None
    for i, a in enumerate(anchors[:30]):  # first 30 frames
        t = float(a["time"])
        ax = a.get("anchorX")
        ay = a.get("anchorY")
        src = a.get("source", "?")
        conf = float(a.get("confidence", 0))
        dx = ""
        if ax is not None and prev_ax is not None:
            dx = f"{ax - prev_ax:+.1f}"
        if ax is not None:
            prev_ax = ax
            if first_valid_anchor_t is None:
                first_valid_anchor_t = t
                first_valid_anchor_x = ax
            print(f"  {i:5d} {t:8.3f} {src:>10} {ax:9.1f} {ay:9.1f} {conf:6.3f} {dx:>8}")
        else:
            print(f"  {i:5d} {t:8.3f} {src:>10}      None      None {conf:6.3f} {dx:>8}")

    if first_valid_anchor_t is not None:
        print(f"\n  ** First valid anchor at t={first_valid_anchor_t:.3f}s, anchorX={first_valid_anchor_x:.1f}")
    else:
        print(f"\n  ** WARNING: No valid anchors found in first 30 frames!")

    # ── 4. Trace camera curve (08c) ───────────────────────────────────
    cc = camera_clips.get(clip_id, {})
    cam_frames = cc.get("frames", [])
    print(f"\n  STAGE 08C: Camera Curve ({len(cam_frames)} frames)")
    print(f"  {'Frame':>5} {'Time':>8} {'CamX':>7} {'CamY':>7} {'W':>5} {'H':>5} {'Zoom':>6} {'Layout':>10} {'Source':>10} {'DriftX':>8} {'DriftY':>8}")

    prev_cx = None
    prev_cy = None
    frame0_cam_x = None
    frame0_cam_y = None
    for i, f in enumerate(cam_frames[:30]):
        t = float(f["time"])
        cx = int(f["x"])
        cy = int(f["y"])
        w = int(f["width"])
        h = int(f["height"])
        z = float(f.get("zoom", 1.0))
        layout = f.get("layout", "?")
        source = f.get("source", "?")

        dx_str = ""
        dy_str = ""
        if prev_cx is not None:
            dx = cx - prev_cx
            dy = cy - prev_cy
            dx_str = f"{dx:+d}"
            dy_str = f"{dy:+d}"

        if i == 0:
            frame0_cam_x = cx
            frame0_cam_y = cy

        prev_cx = cx
        prev_cy = cy
        print(f"  {i:5d} {t:8.3f} {cx:7d} {cy:7d} {w:5d} {h:5d} {z:6.2f} {layout:>10} {source:>10} {dx_str:>8} {dy_str:>8}")

    # ── 5. Camera drift analysis ──────────────────────────────────────
    if cam_frames:
        full_crop = [f for f in cam_frames if f.get("layout") == "full-crop"]
        if len(full_crop) >= 2:
            first = full_crop[0]
            # Find the first frame that DIFFERS significantly from frame 0
            deviation_frame = None
            for i, f in enumerate(full_crop[1:], 1):
                drift = abs(int(f["x"]) - int(first["x"]))
                if drift > 5:
                    deviation_frame = i
                    break

            if deviation_frame is not None:
                df = full_crop[deviation_frame]
                total_drift = int(df["x"]) - int(first["x"])
                print(f"\n  ** CAMERA DRIFT DETECTED: Frame {deviation_frame} deviates by {total_drift:+d}px from Frame 0")
                print(f"     Frame 0: x={first['x']}, t={first['time']:.3f}s, source={first.get('source','?')}")
                print(f"     Frame {deviation_frame}: x={df['x']}, t={df['time']:.3f}s, source={df.get('source','?')}")

                # Identify the total range of camera X motion
                x_vals = [int(f["x"]) for f in full_crop]
                x_min = min(x_vals)
                x_max = max(x_vals)
                print(f"     Total X range: [{x_min}, {x_max}] ({x_max - x_min}px total travel)")
            else:
                print(f"\n  ** Camera is STABLE: No frame deviates >5px from Frame 0")

            # Compare camera frame 0 position to frame center
            crop_w = int(first["width"])
            center_x = (src_w - crop_w) // 2
            cam_vs_center = abs(int(first["x"]) - center_x)
            print(f"\n  ** Frame 0 camera X={first['x']} vs frame-center X={center_x}")
            print(f"     Distance from center: {cam_vs_center}px")
            if cam_vs_center < 20:
                print(f"     !! WARNING: Camera starts very close to frame center - possible default position!")

    # ── 6. Cross-reference anchor vs camera ───────────────────────────
    print(f"\n  CROSS-REFERENCE: Anchor target vs Camera position (first 15 frames)")
    print(f"  {'Frame':>5} {'Time':>8} {'AnchorX':>9} {'CamCenterX':>12} {'Offset':>8} {'AncSrc':>10} {'CamSrc':>10}")

    # Build a time-indexed lookup
    anchor_by_time = {round(float(a["time"]), 3): a for a in anchors}

    for i, f in enumerate(cam_frames[:15]):
        t = round(float(f["time"]), 3)
        cx = int(f["x"])
        cw = int(f["width"])
        cam_center_x = cx + cw / 2.0

        a = anchor_by_time.get(t, {})
        ax = a.get("anchorX")
        a_src = a.get("source", "?")
        c_src = f.get("source", "?")

        if ax is not None:
            offset = cam_center_x - ax
            print(f"  {i:5d} {t:8.3f} {ax:9.1f} {cam_center_x:12.1f} {offset:+8.1f} {a_src:>10} {c_src:>10}")
        else:
            print(f"  {i:5d} {t:8.3f}      None {cam_center_x:12.1f}      N/A {a_src:>10} {c_src:>10}")

    print()

print(f"\n{'='*80}")
print(f"FORENSIC TRACE COMPLETE")
print(f"{'='*80}")
