import os
import sys
import time
import shutil
import pathlib
import urllib.request
import urllib.error
from typing import Optional, Dict, Any, List

# Increase Hugging Face download timeout to 600s (10 minutes) for production resilience
os.environ["HF_HUB_DOWNLOAD_TIMEOUT"] = "600"
os.environ["HF_HUB_DISABLE_SYMLINKS_WARNING"] = "1"

MODELS_DIR = pathlib.Path(__file__).resolve().parent / "models"


def format_size(bytes_num: float) -> str:
    """Format bytes into human-readable MB / GB strings."""
    if bytes_num >= 1024 * 1024 * 1024:
        return f"{bytes_num / (1024**3):.2f} GB"
    elif bytes_num >= 1024 * 1024:
        return f"{bytes_num / (1024**2):.2f} MB"
    elif bytes_num >= 1024:
        return f"{bytes_num / 1024:.1f} KB"
    else:
        return f"{int(bytes_num)} B"


def format_time(seconds: float) -> str:
    """Format seconds into MM:SS format."""
    if seconds < 0 or seconds > 86400:
        return "--:--"
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def render_progress_bar(
    filename: str,
    current_bytes: int,
    total_bytes: int,
    start_time: float,
    bar_length: int = 20,
):
    """Render a clean terminal progress bar with percentage, speed, and ETA."""
    elapsed = max(0.001, time.time() - start_time)
    speed = current_bytes / elapsed if elapsed > 0 else 0

    if total_bytes > 0:
        pct = min(100.0, (current_bytes / total_bytes) * 100.0)
        filled = int(bar_length * current_bytes // total_bytes)
        bar = "█" * filled + "░" * (bar_length - filled)
        remaining_bytes = max(0, total_bytes - current_bytes)
        eta_sec = remaining_bytes / speed if speed > 0 else 0
        eta_str = format_time(eta_sec)
        msg = f"\r  [{bar}] {pct:5.1f}% | {format_size(current_bytes)} / {format_size(total_bytes)} @ {format_size(speed)}/s | ETA: {eta_str}  "
    else:
        bar = "█" * bar_length
        msg = f"\r  [{bar}] {format_size(current_bytes)} @ {format_size(speed)}/s  "

    sys.stdout.write(msg)
    sys.stdout.flush()


def download_single_file_with_resume(
    url: str,
    dest_path: pathlib.Path,
    min_valid_size_bytes: int = 100,
) -> bool:
    """Download a single file with HTTP Range resume support and progress reporting."""
    dest_path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = dest_path.with_suffix(dest_path.suffix + ".part")

    # Check if already complete
    if dest_path.exists() and dest_path.stat().st_size >= min_valid_size_bytes:
        return True

    initial_size = temp_path.stat().st_size if temp_path.exists() else 0

    req = urllib.request.Request(url)
    if initial_size > 0:
        req.add_header("Range", f"bytes={initial_size}-")

    try:
        start_time = time.time()
        with urllib.request.urlopen(req, timeout=30) as resp:
            # Check content length
            content_range = resp.headers.get("Content-Range")
            if content_range and "bytes" in content_range:
                total_bytes = int(content_range.split("/")[-1])
            else:
                total_bytes = int(resp.headers.get("Content-Length", 0))
                if initial_size > 0 and total_bytes > 0:
                    total_bytes += initial_size

            mode = "ab" if (initial_size > 0 and resp.status in (206, 200)) else "wb"
            current_bytes = initial_size if mode == "ab" else 0

            with open(temp_path, mode) as out_f:
                chunk_size = 64 * 1024
                while True:
                    chunk = resp.read(chunk_size)
                    if not chunk:
                        break
                    out_f.write(chunk)
                    current_bytes += len(chunk)
                    render_progress_bar(dest_path.name, current_bytes, total_bytes, start_time)

        sys.stdout.write("\n")
        sys.stdout.flush()

        # Rename part file to dest file
        if temp_path.exists():
            if dest_path.exists():
                dest_path.unlink()
            temp_path.rename(dest_path)

        return dest_path.exists() and dest_path.stat().st_size >= min_valid_size_bytes

    except Exception as err:
        sys.stdout.write("\n")
        print(f"  [ERROR] Failed to download {dest_path.name}: {err}")
        return False


def validate_whisper_model(model_dir: pathlib.Path, expected_min_bin_mb: float) -> bool:
    """Validate a Whisper CTranslate2 model directory.

    Requires:
      1. model.bin exists and is >= expected_min_bin_mb
      2. config.json exists
      3. tokenizer.json OR vocabulary.json OR vocabulary.txt exists
    """
    if not model_dir.exists() or not model_dir.is_dir():
        return False

    model_bin = model_dir / "model.bin"
    config_json = model_dir / "config.json"

    if not model_bin.exists() or not config_json.exists():
        return False

    # Size check on model.bin
    bin_size_mb = model_bin.stat().st_size / (1024 * 1024)
    if bin_size_mb < expected_min_bin_mb:
        return False

    # Check for vocabulary/tokenizer
    has_vocab = (
        (model_dir / "tokenizer.json").exists()
        or (model_dir / "vocabulary.json").exists()
        or (model_dir / "vocabulary.txt").exists()
    )

    return has_vocab


def setup_whisper_model(
    model_name: str,
    min_bin_mb: float,
) -> tuple[bool, str, float]:
    """Download and verify a Whisper model into models/whisper-<name>/."""
    dest_dir = MODELS_DIR / f"whisper-{model_name}"

    # Check if already complete and valid
    if validate_whisper_model(dest_dir, min_bin_mb):
        size_mb = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        return True, "VALID (EXISTS)", size_mb

    # If invalid or incomplete, clean directory before download
    if dest_dir.exists():
        print(f"  [CLEANUP] Removing incomplete/corrupted model at {dest_dir.name}...")
        try:
            shutil.rmtree(dest_dir)
        except Exception as e:
            print(f"  [WARNING] Could not delete directory {dest_dir}: {e}")

    dest_dir.mkdir(parents=True, exist_ok=True)
    print(f"  [DOWNLOAD] Fetching Whisper {model_name} from Hugging Face -> {dest_dir.name}/...")

    try:
        from faster_whisper import download_model
        download_model(model_name, output_dir=str(dest_dir))
    except Exception as err:
        print(f"  [ERROR] Faster-Whisper download failed for {model_name}: {err}")
        return False, f"FAILED ({err})", 0.0

    # Verify after download
    if validate_whisper_model(dest_dir, min_bin_mb):
        size_mb = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file()) / (1024 * 1024)
        return True, "VALID (NEW)", size_mb
    else:
        print(f"  [ERROR] Model verification failed after download for {model_name}.")
        return False, "INVALID AFTER DOWNLOAD", 0.0


def main():
    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    print("==========================================================")
    print("      AI Clip Generator — Production Model Setup Utility")
    print("==========================================================")
    print(f" Target Directory: {MODELS_DIR}\n")

    report_rows: List[Dict[str, Any]] = []

    # 1. Silero VAD
    print("[1/6] Silero VAD Model...")
    vad_path = MODELS_DIR / "silero_vad.onnx"
    vad_url = "https://github.com/snakers4/silero-vad/raw/master/files/silero_vad.onnx"
    ok = download_single_file_with_resume(vad_url, vad_path, min_valid_size_bytes=1_000_000)
    size_mb = vad_path.stat().st_size / (1024 * 1024) if vad_path.exists() else 0.0
    report_rows.append({
        "name": "Silero VAD",
        "variant": "silero_vad.onnx",
        "path": str(vad_path.relative_to(MODELS_DIR.parent)),
        "size": format_size(vad_path.stat().st_size) if ok else "0 B",
        "status": "VALID" if ok else "FAILED",
    })

    # 2. YOLOv8n
    print("[2/6] YOLOv8 Object/Person Detection Model...")
    yolo_path = MODELS_DIR / "yolov8n.pt"
    yolo_url = "https://github.com/ultralytics/assets/releases/download/v8.2.0/yolov8n.pt"
    ok = download_single_file_with_resume(yolo_url, yolo_path, min_valid_size_bytes=5_000_000)
    report_rows.append({
        "name": "YOLOv8",
        "variant": "yolov8n.pt",
        "path": str(yolo_path.relative_to(MODELS_DIR.parent)),
        "size": format_size(yolo_path.stat().st_size) if ok else "0 B",
        "status": "VALID" if ok else "FAILED",
    })

    # 3. YuNet Face Detector
    print("[3/6] YuNet Face Detection ONNX Model...")
    yunet_path = MODELS_DIR / "face_detection_yunet_2023mar.onnx"
    yunet_url = "https://github.com/opencv/opencv_zoo/raw/main/models/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ok = download_single_file_with_resume(yunet_url, yunet_path, min_valid_size_bytes=200_000)
    report_rows.append({
        "name": "YuNet Face Detector",
        "variant": "yunet_2023mar",
        "path": str(yunet_path.relative_to(MODELS_DIR.parent)),
        "size": format_size(yunet_path.stat().st_size) if ok else "0 B",
        "status": "VALID" if ok else "FAILED",
    })

    # 4. Whisper Tiny
    print("\n[4/6] Whisper Tiny Model...")
    ok, status, sz_mb = setup_whisper_model("tiny", min_bin_mb=65.0)
    report_rows.append({
        "name": "Whisper Tiny",
        "variant": "whisper-tiny",
        "path": str((MODELS_DIR / "whisper-tiny").relative_to(MODELS_DIR.parent)),
        "size": f"{sz_mb:.1f} MB",
        "status": status,
    })

    # 5. Whisper Medium
    print("\n[5/6] Whisper Medium Model...")
    ok, status, sz_mb = setup_whisper_model("medium", min_bin_mb=1400.0)
    report_rows.append({
        "name": "Whisper Medium",
        "variant": "whisper-medium",
        "path": str((MODELS_DIR / "whisper-medium").relative_to(MODELS_DIR.parent)),
        "size": f"{sz_mb:.1f} MB",
        "status": status,
    })

    # 6. Whisper Large-v3
    print("\n[6/6] Whisper Large-v3 Model...")
    ok, status, sz_mb = setup_whisper_model("large-v3", min_bin_mb=3000.0)
    report_rows.append({
        "name": "Whisper Large-v3",
        "variant": "whisper-large-v3",
        "path": str((MODELS_DIR / "whisper-large-v3").relative_to(MODELS_DIR.parent)),
        "size": f"{sz_mb:.1f} MB",
        "status": status,
    })

    # Produce Final Execution Report
    print("\n" + "=" * 80)
    print("                      PRODUCTION MODEL SETUP REPORT")
    print("=" * 80)
    hdr = f"{'MODEL':<20s} | {'VARIANT':<18s} | {'LOCAL PATH':<24s} | {'SIZE':<10s} | {'STATUS'}"
    print(hdr)
    print("-" * 80)
    for row in report_rows:
        line = f"{row['name']:<20s} | {row['variant']:<18s} | {row['path']:<24s} | {row['size']:<10s} | {row['status']}"
        print(line)
    print("=" * 80)

    all_valid = all(r["status"].startswith("VALID") for r in report_rows)
    if all_valid:
        print(" SUCCESS: All required AI models are installed, validated, and ready for offline use!")
    else:
        print(" WARNING: Some models failed to setup. Check output logs above.")


if __name__ == "__main__":
    main()
