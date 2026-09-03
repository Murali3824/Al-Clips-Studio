import os
from pathlib import Path
import urllib.request
import sys

def download_file(url: str, dest_path: Path):
    if dest_path.exists():
        print(f"[INFO] {dest_path.name} already exists. Skipping download.")
        return

    print(f"[INFO] Downloading {url} to {dest_path}...")
    dest_path.parent.mkdir(parents=True, exist_ok=True)

    def progress_hook(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, int(downloaded * 100 / total_size)) if total_size > 0 else 0
        sys.stdout.write(f"\rProgress: {percent}% ({downloaded / (1024*1024):.1f}MB / {total_size / (1024*1024):.1f}MB)")
        sys.stdout.flush()

    try:
        urllib.request.urlretrieve(url, str(dest_path), reporthook=progress_hook)
        print("\n[SUCCESS] Download completed.")
    except Exception as e:
        print(f"\n[ERROR] Failed to download {url}: {e}")

def main():
    root = Path(__file__).resolve().parent
    music_dir = root / "storage" / "music"
    music_dir.mkdir(parents=True, exist_ok=True)

    print("==========================================")
    print("  AI Shorts Generator - Music Downloader")
    print("==========================================")
    print()

    tracks = [
        ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", "lofi_ambient.mp3"),
        ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-2.mp3", "upbeat_acoustic.mp3"),
        ("https://www.soundhelix.com/examples/mp3/SoundHelix-Song-3.mp3", "corporate_synth.mp3")
    ]

    for index, (url, filename) in enumerate(tracks, start=1):
        print(f"[{index}/{len(tracks)}] Setting up {filename}...")
        download_file(url, music_dir / filename)
        print()

    print("==========================================")
    print(" Background music download completed!")
    print("==========================================")

if __name__ == "__main__":
    main()
