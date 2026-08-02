"""Stage 08B - Per-Frame Anchor Stream Builder.

Produces anchor_curve.json: a dense, time-ordered stream of subject anchor points
with one record per sampled frame. These anchors are the authoritative input for the
virtual camera operator in stage_08c.

Anchor priority (per frame):
  1. YuNet face detection for the approved identity  -> eye-line anchor
  2. YOLO body track for the selected track           -> estimated head-center anchor
  3. Carried forward from last known anchor            -> decayed anchor

EMA smoothing is applied to the raw anchor stream to prevent single-frame noise
from triggering camera movement.
"""

import json
import statistics

EMA_ALPHA_POSITION = 0.18
EMA_ALPHA_SIZE = 0.12
MAX_ANCHOR_GAP_SECONDS = 1.5
CARRY_FORWARD_DECAY = 0.92
BODY_EYE_LINE_FRACTION = 0.18
BODY_FACE_HEIGHT_FRACTION = 0.22
BODY_FACE_WIDTH_FRACTION = 0.55


def _face_samples_for_identity(identity_data, clip_start, clip_end):
    samples = []
    for scene in identity_data.get("scenes", []):
        scene_start = float(scene.get("start", 0))
        scene_end = float(scene.get("end", 999999))
        if scene_end < clip_start or scene_start > clip_end:
            continue

        switches = sorted(scene.get("subjectSwitches", []), key=lambda s: float(s.get("time", 0)))
        identities = scene.get("identities", [])
        if not identities:
            continue

        if not switches:
            # No switches: extract face samples from all identities in scene
            for identity in identities:
                for det in identity.get("detections", []):
                    t = float(det.get("time", -1))
                    if clip_start <= t <= clip_end:
                        samples.append({
                            "time": t,
                            "bbox": det["bbox"],
                            "confidence": float(det.get("confidence", 0.5)),
                            "source": "face",
                        })
        else:
            intervals = []
            first_switch_t = float(switches[0].get("time", scene_start))
            if first_switch_t > scene_start:
                primary_id = identities[0].get("subjectId")
                intervals.append((scene_start, first_switch_t, primary_id))

            for idx, switch in enumerate(switches):
                subject_id = switch.get("toSubjectId")
                seg_start = float(switch["time"])
                seg_end = float(switches[idx + 1]["time"]) if idx + 1 < len(switches) else scene_end
                intervals.append((seg_start, seg_end, subject_id))

            for seg_start, seg_end, subject_id in intervals:
                win_s = max(clip_start, seg_start)
                win_e = min(clip_end, seg_end)
                if win_e < win_s:
                    continue
                identity = next((i for i in identities if i.get("subjectId") == subject_id), None)
                if not identity:
                    continue
                for det in identity.get("detections", []):
                    t = float(det.get("time", -1))
                    if win_s <= t <= win_e:
                        samples.append({
                            "time": t,
                            "bbox": det["bbox"],
                            "confidence": float(det.get("confidence", 0.5)),
                            "source": "face",
                        })

    samples.sort(key=lambda s: s["time"])
    return samples


def _body_samples_for_track(track, clip_start, clip_end):
    samples = []
    for det in track.get("detections", []):
        t = float(det.get("time", -1))
        if clip_start <= t <= clip_end:
            bbox = det.get("bbox", [])
            if not bbox or len(bbox) < 4:
                continue
            x, y, w, h = float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
            eye_y = y + h * BODY_EYE_LINE_FRACTION
            face_cx = x + w / 2.0
            face_w = w * BODY_FACE_WIDTH_FRACTION
            face_h = h * BODY_FACE_HEIGHT_FRACTION
            samples.append({
                "time": t,
                "bbox": [face_cx - face_w / 2.0, eye_y - face_h * 0.42, face_w, face_h],
                "confidence": float(det.get("confidence", 0.4)) * 0.75,
                "source": "body",
                "body_bbox": [x, y, w, h],
            })
    samples.sort(key=lambda s: s["time"])
    return samples


def _best_track(tracks, clip_start, clip_end):
    best = None
    best_score = -1.0
    for track in tracks:
        dets = [d for d in track.get("detections", []) if clip_start <= float(d.get("time", -1)) <= clip_end]
        if not dets:
            continue
        avg_conf = statistics.fmean(float(d.get("confidence", 0.5)) for d in dets)
        areas = [float(d["bbox"][2]) * float(d["bbox"][3]) for d in dets if len(d.get("bbox", [])) >= 4]
        avg_area = statistics.fmean(areas) if areas else 1.0
        score = len(dets) * avg_conf * (1.0 + min(1.0, avg_area / 50000.0))
        if score > best_score:
            best = track
            best_score = score
    return best


def _merge_anchor_samples(face_samples, body_samples, clip_start, clip_end, frame_times):
    TOLERANCE = 0.50  # Must be at least 1 frame interval (0.5s) to match sampling grids

    def nearest(samples, t):
        if not samples:
            return None
        best = min(samples, key=lambda s: abs(s["time"] - t))
        if abs(best["time"] - t) <= TOLERANCE:
            return best
        return None

    raw_anchors = []
    last_anchor = None
    last_anchor_time = None
    carry_confidence = 0.0

    for t in frame_times:
        face = nearest(face_samples, t)
        body = nearest(body_samples, t)

        if face is not None:
            fx, fy, fw, fh = float(face["bbox"][0]), float(face["bbox"][1]), float(face["bbox"][2]), float(face["bbox"][3])
            anchor = {
                "time": t,
                "anchorX": fx + fw / 2.0,
                "anchorY": fy + fh * 0.25,   # 0.25 = eye line in face bbox (not 0.42 = nose)
                "faceWidth": fw,
                "faceHeight": fh,
                "confidence": float(face["confidence"]),
                "source": "face",
            }
            if body is not None and body.get("body_bbox"):
                anchor["bodyBbox"] = body["body_bbox"]
            last_anchor = anchor.copy()
            last_anchor_time = t
            carry_confidence = float(face["confidence"])
        elif body is not None:
            bx, by, bw, bh = float(body["bbox"][0]), float(body["bbox"][1]), float(body["bbox"][2]), float(body["bbox"][3])
            bbbox = body.get("body_bbox", [])
            anchor = {
                "time": t,
                "anchorX": bx + bw / 2.0,
                "anchorY": by + bh * 0.42,
                "faceWidth": bw,
                "faceHeight": bh,
                "confidence": float(body["confidence"]),
                "source": "body",
            }
            if bbbox and len(bbbox) >= 4:
                anchor["bodyBbox"] = bbbox
            last_anchor = anchor.copy()
            last_anchor_time = t
            carry_confidence = float(body["confidence"])
        elif last_anchor is not None:
            gap = t - last_anchor_time
            if gap <= MAX_ANCHOR_GAP_SECONDS:
                carry_confidence *= CARRY_FORWARD_DECAY
                anchor = {
                    **last_anchor,
                    "time": t,
                    "confidence": round(carry_confidence, 4),
                    "source": "carried",
                }
            else:
                anchor = {
                    "time": t, "anchorX": None, "anchorY": None,
                    "faceWidth": None, "faceHeight": None,
                    "confidence": 0.0, "source": "lost",
                }
        else:
            anchor = {
                "time": t, "anchorX": None, "anchorY": None,
                "faceWidth": None, "faceHeight": None,
                "confidence": 0.0, "source": "lost",
            }

        raw_anchors.append(anchor)

    # ── Backfill initial lost frames with first valid anchor ──────────────
    # If the first N frames have no detection (source="lost"), the camera
    # would have no target and downstream stages would default to frame-center.
    # Instead, propagate the first known subject position backward so the camera
    # starts framed on the subject from frame 0.
    first_valid_idx = next(
        (i for i, a in enumerate(raw_anchors) if a.get("anchorX") is not None), None
    )
    if first_valid_idx is not None and first_valid_idx > 0:
        fill = raw_anchors[first_valid_idx]
        for i in range(first_valid_idx):
            raw_anchors[i] = {
                **fill,
                "time": raw_anchors[i]["time"],
                "confidence": round(float(fill.get("confidence", 0.5)) * 0.8, 4),
                "source": "backfill",
            }

    return raw_anchors


def _ema_smooth(anchors, alpha_pos, alpha_size):
    smoothed = []
    s_x = s_y = s_fw = s_fh = None

    for anchor in anchors:
        ax = anchor.get("anchorX")
        ay = anchor.get("anchorY")
        fw = anchor.get("faceWidth")
        fh = anchor.get("faceHeight")

        if ax is None or ay is None:
            s_x = s_y = s_fw = s_fh = None
            smoothed.append({**anchor})
            continue

        if s_x is None:
            s_x, s_y = ax, ay
            s_fw = fw if fw is not None else 100.0
            s_fh = fh if fh is not None else 180.0
        else:
            s_x = alpha_pos * ax + (1.0 - alpha_pos) * s_x
            s_y = alpha_pos * ay + (1.0 - alpha_pos) * s_y
            if fw is not None:
                s_fw = alpha_size * fw + (1.0 - alpha_size) * s_fw
            if fh is not None:
                s_fh = alpha_size * fh + (1.0 - alpha_size) * s_fh

        smoothed.append({
            **anchor,
            "anchorX": round(s_x, 3),
            "anchorY": round(s_y, 3),
            "faceWidth": round(s_fw, 3) if s_fw is not None else None,
            "faceHeight": round(s_fh, 3) if s_fh is not None else None,
            "rawAnchorX": round(ax, 3),
            "rawAnchorY": round(ay, 3),
        })

    return smoothed


def _build_frame_times(clip_start, clip_end, fps, frame_interval):
    times = []
    dt = frame_interval / fps
    t = clip_start
    while t <= clip_end + 1e-6:
        times.append(round(t, 6))
        t += dt
    return times


def run(context):
    temp_dir = context["temp_dir"]
    metadata = json.loads((temp_dir / "video_metadata.json").read_text(encoding="utf-8"))
    highlights = json.loads((temp_dir / "highlights.json").read_text(encoding="utf-8"))["highlights"]
    track_data = json.loads((temp_dir / "face_tracks.json").read_text(encoding="utf-8"))
    identity_path = temp_dir / "subject_identities.json"
    identity_data = json.loads(identity_path.read_text(encoding="utf-8")) if identity_path.exists() else None

    fps = float(metadata.get("fps") or 30.0)
    frame_interval = max(1, int(round(fps / 2)))
    tracks = track_data.get("tracks", [])

    clip_curves = []

    for highlight in sorted(highlights, key=lambda h: float(h["start"])):
        clip_id = highlight["id"]
        clip_start = float(highlight["start"])
        clip_end = float(highlight["end"])

        frame_times = _build_frame_times(clip_start, clip_end, fps, frame_interval)
        best_track = _best_track(tracks, clip_start, clip_end)
        face_samples = _face_samples_for_identity(identity_data, clip_start, clip_end) if identity_data else []
        body_samples = _body_samples_for_track(best_track, clip_start, clip_end) if best_track else []

        raw_anchors = _merge_anchor_samples(face_samples, body_samples, clip_start, clip_end, frame_times)
        smoothed_anchors = _ema_smooth(raw_anchors, EMA_ALPHA_POSITION, EMA_ALPHA_SIZE)

        source_counts = {}
        for a in smoothed_anchors:
            src = a.get("source", "unknown")
            source_counts[src] = source_counts.get(src, 0) + 1

        clip_curves.append({
            "clipId": clip_id,
            "start": clip_start,
            "end": clip_end,
            "fps": fps,
            "frameInterval": frame_interval,
            "totalFrames": len(smoothed_anchors),
            "sourceCounts": source_counts,
            "anchors": smoothed_anchors,
        })

    (temp_dir / "anchor_curve.json").write_text(
        json.dumps({
            "method": "face-body-fusion-ema-anchor-stream",
            "schemaVersion": "1.0",
            "emaAlphaPosition": EMA_ALPHA_POSITION,
            "emaAlphaSize": EMA_ALPHA_SIZE,
            "clips": clip_curves,
        }, indent=2),
        encoding="utf-8",
    )
