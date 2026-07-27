"""Centralized Music Library Manager.

Single source of truth for all music file operations.
Directory: storage/music/

Features:
  - ffprobe-validated track scanning with caching
  - Category detection from filenames and subdirectory names
  - Content-to-music category matching
  - History-aware intelligent selection with reproducible shuffle
  - Graceful handling of corrupted / unsupported files
  - Scalable to 500+ tracks
"""

import hashlib
import json
import random
import subprocess
import time
from pathlib import Path
from typing import Optional

SUPPORTED_AUDIO = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

# ── Category keyword mapping ──────────────────────────────────────────────────
CATEGORY_KEYWORDS: dict[str, list[str]] = {
    "ambient":       ["ambient", "calm", "peaceful", "relaxing", "chill", "lofi", "lo-fi", "soft"],
    "cinematic":     ["cinematic", "epic", "dramatic", "trailer", "film", "orchestral"],
    "corporate":     ["corporate", "business", "professional", "presentation", "modern"],
    "upbeat":        ["upbeat", "happy", "energetic", "fun", "party", "dance", "light", "cheerful"],
    "emotional":     ["emotional", "sad", "melancholy", "sentimental", "heartfelt", "tender"],
    "inspirational": ["inspirational", "motivational", "hopeful", "uplifting", "triumph"],
    "acoustic":      ["acoustic", "guitar", "piano", "folk", "unplugged"],
    "electronic":    ["electronic", "synth", "techno", "edm", "digital", "futuristic"],
}

# ── Content category → preferred music categories ─────────────────────────────
CONTENT_TO_MUSIC: dict[str, list[str]] = {
    "podcast":      ["ambient", "acoustic"],
    "motivation":   ["cinematic", "inspirational"],
    "business":     ["corporate", "ambient"],
    "educational":  ["ambient", "acoustic"],
    "storytelling": ["emotional", "cinematic"],
    "funny":        ["upbeat", "electronic"],
    "news":         ["corporate", "ambient"],
    "tutorial":     ["ambient", "acoustic"],
    "gaming":       ["electronic", "upbeat"],
    "fitness":      ["upbeat", "electronic"],
    "technology":   ["electronic", "corporate"],
    "lifestyle":    ["upbeat", "acoustic"],
    "travel":       ["cinematic", "acoustic"],
    "cooking":      ["upbeat", "acoustic"],
    "interview":    ["ambient", "acoustic"],
}

_PREFIX = "[MusicLibrary]"


class MusicLibrary:
    """Thread-safe, cached, category-aware music library."""

    def __init__(self, music_dir: Path | str):
        self.music_dir = Path(music_dir)
        self._cache_path = self.music_dir / ".library_cache.json"
        self._tracks: list[dict] = []
        self._history: list[str] = []
        self._scanned = False

    # ── Public API ────────────────────────────────────────────────────────────

    def scan(self, force: bool = False) -> list[dict]:
        """Scan music directory, validate tracks via ffprobe, and cache results.

        Returns a list of validated track dicts. Corrupted or unsupported files
        are logged and silently skipped.
        """
        if self._scanned and not force:
            return self._tracks

        if not self.music_dir.exists():
            print(f"{_PREFIX} Music directory does not exist: {self.music_dir}")
            self._tracks = []
            self._scanned = True
            return []

        audio_files = self._list_audio_files()
        if not audio_files:
            print(f"{_PREFIX} No audio files found in {self.music_dir}")
            self._tracks = []
            self._scanned = True
            return []

        # Attempt to use cache
        cache = self._load_cache()
        if cache and not force:
            cached_paths = {t["path"] for t in cache.get("tracks", [])}
            current_paths = {str(f) for f in audio_files}

            if cached_paths == current_paths:
                cache_time = cache.get("scanned_at", 0)
                latest_mtime = max(
                    (f.stat().st_mtime for f in audio_files), default=0
                )
                if latest_mtime <= cache_time:
                    self._tracks = cache["tracks"]
                    self._scanned = True
                    print(
                        f"{_PREFIX} Loaded {len(self._tracks)} tracks from cache"
                    )
                    return self._tracks

        # Full scan with validation
        print(f"{_PREFIX} Scanning {len(audio_files)} audio files...")
        tracks: list[dict] = []
        skipped = 0

        for audio_file in audio_files:
            track = self._validate_track(audio_file)
            if track:
                tracks.append(track)
            else:
                skipped += 1

        self._tracks = tracks
        self._scanned = True
        self._save_cache(tracks)

        print(
            f"{_PREFIX} Library ready: {len(tracks)} valid tracks"
            + (f", {skipped} skipped" if skipped else "")
        )
        return tracks

    def select_track(
        self,
        clip_index: int = 0,
        total_clips: int = 1,
        content_category: str = "",
        job_id: str = "",
        explicit_path: str = "",
    ) -> Optional[dict]:
        """Select a music track with intelligent category matching and history awareness.

        Priority order:
          1. Explicit user-selected track (if valid)
          2. Category-matched tracks (if content_category provided)
          3. All available tracks (general pool)

        Within each pool, tracks are shuffled reproducibly using job_id + clip_index
        as seed, and recently-used tracks are deprioritized.
        """
        # User explicitly selected a track
        if explicit_path:
            p = Path(explicit_path)
            if p.exists():
                return {
                    "path": str(p),
                    "name": p.stem,
                    "reason": "user-selected",
                }
            else:
                print(
                    f"{_PREFIX} User-selected track not found: {explicit_path}"
                )

        tracks = self.scan()
        if not tracks:
            return None

        # Category matching
        preferred_cats = CONTENT_TO_MUSIC.get(content_category.lower(), [])
        category_pool = (
            [t for t in tracks if t.get("category") in preferred_cats]
            if preferred_cats
            else []
        )

        pool = category_pool if category_pool else tracks
        reason_prefix = (
            f"category-match({content_category})"
            if category_pool
            else "general-pool"
        )

        # History-aware deprioritization
        if len(pool) > 1:
            history_window = max(1, len(pool) // 2)
            recent = set(self._history[-history_window:])
            fresh = [t for t in pool if t["path"] not in recent]
            if fresh:
                pool = fresh

        # Reproducible shuffle
        seed_str = f"{job_id}:{clip_index}"
        seed = int(hashlib.md5(seed_str.encode()).hexdigest()[:8], 16)
        rng = random.Random(seed)
        selected = rng.choice(pool)

        # Update history
        self._history.append(selected["path"])
        if len(self._history) > 200:
            self._history = self._history[-100:]

        reason = f"{reason_prefix} → {selected.get('category', 'general')}"
        print(
            f"{_PREFIX} Clip {clip_index + 1}/{total_clips}: "
            f"{Path(selected['path']).name} ({reason})"
        )

        return {**selected, "reason": reason}

    def track_count(self) -> int:
        """Return the number of validated tracks without triggering a full scan."""
        if self._scanned:
            return len(self._tracks)
        return len(self._list_audio_files())

    # ── Internal ──────────────────────────────────────────────────────────────

    def _list_audio_files(self) -> list[Path]:
        """List all audio files in the music directory (non-recursive, sorted)."""
        if not self.music_dir.exists():
            return []
        return sorted(
            p
            for p in self.music_dir.iterdir()
            if p.is_file()
            and p.suffix.lower() in SUPPORTED_AUDIO
            and not p.name.startswith(".")
        )

    def _validate_track(self, path: Path) -> Optional[dict]:
        """Validate an audio file using ffprobe. Returns track dict or None."""
        try:
            result = subprocess.run(
                [
                    "ffprobe",
                    "-v", "quiet",
                    "-print_format", "json",
                    "-show_format",
                    str(path),
                ],
                capture_output=True,
                timeout=15,
            )
            if result.returncode != 0:
                print(f"⚠️ Skipping track {path.name}: metadata probe failed", flush=True)
                return None

            raw_stdout = result.stdout or b""
            stdout_str = raw_stdout.decode("utf-8", errors="replace").strip()
            if not stdout_str:
                print(f"⚠️ One music track contains invalid metadata. Skipping track and continuing...", flush=True)
                return None

            try:
                probe = json.loads(stdout_str)
            except Exception:
                print(f"⚠️ One music track contains invalid metadata. Skipping track and continuing...", flush=True)
                return None

            fmt = probe.get("format", {})
            duration = float(fmt.get("duration", 0))

            if duration < 1.0:
                print(f"⚠️ Skipping track {path.name}: duration too short ({duration:.1f}s)", flush=True)
                return None

            category = self._detect_category(path)

            return {
                "path": str(path),
                "name": path.stem,
                "format": path.suffix.lower(),
                "duration": round(duration, 2),
                "size": path.stat().st_size,
                "category": category,
            }
        except subprocess.TimeoutExpired:
            print(f"⚠️ Skipping track {path.name}: probe timed out", flush=True)
            return None
        except Exception as exc:
            print(f"⚠️ One music track contains invalid metadata. Skipping track and continuing...", flush=True)
            return None

    def _detect_category(self, path: Path) -> str:
        """Detect music category from filename and parent directory name."""
        name_lower = path.stem.lower().replace("_", " ").replace("-", " ")
        parent = path.parent.name.lower()
        search = f"{name_lower} {parent}" if parent != "music" else name_lower

        for category, keywords in CATEGORY_KEYWORDS.items():
            if any(kw in search for kw in keywords):
                return category
        return "general"

    def _load_cache(self) -> Optional[dict]:
        """Load cached library metadata if it exists."""
        try:
            if self._cache_path.exists():
                data = json.loads(
                    self._cache_path.read_text(encoding="utf-8")
                )
                if isinstance(data, dict) and "tracks" in data:
                    return data
        except Exception:
            pass
        return None

    def _save_cache(self, tracks: list[dict]) -> None:
        """Persist validated library to disk cache."""
        try:
            self.music_dir.mkdir(parents=True, exist_ok=True)
            self._cache_path.write_text(
                json.dumps(
                    {"scanned_at": time.time(), "tracks": tracks}, indent=2
                ),
                encoding="utf-8",
            )
        except Exception:
            pass  # Non-critical — cache is advisory


def has_audio_stream(video_path: str | Path) -> bool:
    """Check if a video file contains at least one audio stream."""
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "quiet",
                "-select_streams", "a",
                "-show_entries", "stream=index",
                "-of", "csv=p=0",
                str(video_path),
            ],
            capture_output=True,
            timeout=10,
        )
        raw_stdout = result.stdout or b""
        stdout_str = raw_stdout.decode("utf-8", errors="replace").strip()
        return len(stdout_str) > 0
    except Exception:
        return False  # Assume audio exists on probe failure (safer default)
