import json

from media_utils import find_input_video
from scenedetect import SceneManager, open_video
from scenedetect.detectors import ContentDetector


def run(context):
    input_video = find_input_video(context["upload_dir"])
    metadata = json.loads(
        (context["temp_dir"] / "video_metadata.json").read_text(encoding="utf-8")
    )
    video_duration = float(metadata["duration"])
    threshold = float(context["settings"].get("sceneThreshold", 27.0))

    video = open_video(str(input_video))
    scene_manager = SceneManager()
    scene_manager.add_detector(ContentDetector(threshold=threshold))
    scene_manager.detect_scenes(video=video, show_progress=False)

    scene_list = scene_manager.get_scene_list()
    scenes = []
    for index, (start_time, end_time) in enumerate(scene_list):
        scenes.append({
            "index": index,
            "start": round(start_time.get_seconds(), 3),
            "end": round(end_time.get_seconds(), 3),
            "startFrame": start_time.get_frames(),
            "endFrame": end_time.get_frames(),
        })

    if not scenes:
        scenes = [{
            "index": 0,
            "start": 0.0,
            "end": round(video_duration, 3),
            "startFrame": 0,
            "endFrame": None,
        }]

    (context["temp_dir"] / "scene_cuts.json").write_text(
        json.dumps({
            "method": "PySceneDetect ContentDetector",
            "threshold": threshold,
            "scenes": scenes,
        }, indent=2),
        encoding="utf-8",
    )
