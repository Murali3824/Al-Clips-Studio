"""
Empirical verification test for downstream stages (stage_08_shot_selection.py & stage_08_smooth_crop.py).
Verifies that the output produced by the redesigned Highlight Selection Pipeline (highlights.json)
is consumed by stage_08_shot_selection and stage_08_smooth_crop without KeyError: 'id' or schema errors.
"""
import sys
import os
import json
import tempfile
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from highlights.production_exporter import run_production_export
from highlights.schemas import FinalHighlight, HighlightCandidate, QAReportEntry, RankingCandidate
import stages.stage_08_shot_selection as stage08_select
import stages.stage_08_smooth_crop as stage08_crop


def test_downstream_pipeline_execution():
    tmp_dir = Path(tempfile.mkdtemp())

    # 1. Setup mock video metadata
    metadata = {
        "width": 1920,
        "height": 1080,
        "duration": 60.0,
        "fps": 30.0,
    }
    (tmp_dir / "video_metadata.json").write_text(json.dumps(metadata), encoding="utf-8")

    # 2. Export sample production highlights.json (using Phase L exporter)
    fh1 = FinalHighlight(
        clip_id="cand_001",
        start=0.0,
        end=30.0,
        duration=30.0,
        score=0.92,
        ranking=1,
        production_score=0.90,
        editorial_quality=0.88,
        qa_status="PASSED",
        text="What is the single secret to building high performance teams?",
    )
    fh2 = FinalHighlight(
        clip_id="cand_002",
        start=35.0,
        end=55.0,
        duration=20.0,
        score=0.88,
        ranking=2,
        production_score=0.85,
        editorial_quality=0.85,
        qa_status="PASSED",
        text="When allocating your ad spend test small and learn fast.",
    )
    
    # Save backward-compatible highlights.json
    output_obj = {
        "method": "editorial-intelligence-pass9",
        "clipCount": 2,
        "highlights": [fh1.to_dict(), fh2.to_dict()],
    }
    (tmp_dir / "highlights.json").write_text(json.dumps(output_obj, indent=2), encoding="utf-8")

    # 3. Setup mock face tracks & detections
    face_tracks = {
        "tracker": "bytetrack",
        "tracks": [
            {
                "trackId": 1,
                "detections": [
                    {"time": 5.0, "bbox": [800, 200, 300, 400], "confidence": 0.95},
                    {"time": 15.0, "bbox": [805, 205, 300, 400], "confidence": 0.95},
                    {"time": 40.0, "bbox": [810, 210, 300, 400], "confidence": 0.95},
                ]
            }
        ]
    }
    (tmp_dir / "face_tracks.json").write_text(json.dumps(face_tracks), encoding="utf-8")

    face_detections = {
        "method": "yunet",
        "detections": [
            {"time": 5.0, "bbox": [800, 200, 300, 400], "confidence": 0.95},
            {"time": 15.0, "bbox": [805, 205, 300, 400], "confidence": 0.95},
            {"time": 40.0, "bbox": [810, 210, 300, 400], "confidence": 0.95},
        ]
    }
    (tmp_dir / "face_detections.json").write_text(json.dumps(face_detections), encoding="utf-8")

    # 4. Setup mock scene cuts & subject identities
    scene_cuts = {
        "scenes": [
            {"start": 0.0, "end": 30.0, "index": 0},
            {"start": 30.0, "end": 60.0, "index": 1},
        ]
    }
    (tmp_dir / "scene_cuts.json").write_text(json.dumps(scene_cuts), encoding="utf-8")

    context = {"temp_dir": tmp_dir, "settings": {"layoutMode": "auto"}}

    print("\n--- Running Stage 8: Editorial Shot Selection ---")
    stage08_select.run(context)
    
    shot_plan_file = tmp_dir / "shot_plan.json"
    assert shot_plan_file.exists(), "shot_plan.json not generated!"
    shot_plan_data = json.loads(shot_plan_file.read_text(encoding="utf-8"))
    print(f"  [PASS] shot_plan.json generated cleanly with {len(shot_plan_data.get('clips', []))} clip plans")
    for clip in shot_plan_data.get("clips", []):
        assert "clipId" in clip, "Missing clipId in shot_plan clip!"
        print(f"  [INFO] Shot plan for clipId={clip['clipId']}: {len(clip.get('segments', []))} scene segments classified")

    print("\n--- Running Stage 8 (Smooth Crop): Crop Coords Generation ---")
    stage08_crop.run(context)

    crop_coords_file = tmp_dir / "crop_coords.json"
    assert crop_coords_file.exists(), "crop_coords.json not generated!"
    crop_data = json.loads(crop_coords_file.read_text(encoding="utf-8"))
    print(f"  [PASS] crop_coords.json generated cleanly with {len(crop_data.get('plans', []))} crop plans")
    for plan in crop_data.get("plans", []):
        assert "clipId" in plan, "Missing clipId in crop plan!"
        print(f"  [INFO] Crop plan for clipId={plan['clipId']}: resolvedLayout={plan.get('resolvedLayout')}, method={plan.get('method')}")

    print("\n" + "="*70)
    print("Downstream Stages Schema Verification: 100% PASSED")
    print("Stage 8 (Editorial Shot Selection) and Stage 8 (Smooth Crop) executed cleanly without KeyError!")
    print("="*70)


if __name__ == "__main__":
    test_downstream_pipeline_execution()
