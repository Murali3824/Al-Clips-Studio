import { spawn, execSync } from "child_process";
import path from "path";
import fs from "fs";
import { io } from "../server.js";
import { ensureJobUploadDir } from "../utils/storagePaths.js";
import { writeProject } from "./project.service.js";
import {
  getAccessibleBrowser,
  markBrowserInaccessible,
  getBrowserDiagnostics,
} from "./cookieManager.js";

const storageRoot = path.resolve(process.env.STORAGE_PATH ?? "../storage");
const cacheFilePath = path.join(storageRoot, ".youtube_cache.json");

export interface YouTubeInfo {
  title: string;
  duration: number;
  thumbnailUrl?: string | null;
  videoId?: string;
}

export interface DependencyStatus {
  ok: boolean;
  ytDlpAvailable: boolean;
  ffmpegAvailable: boolean;
  detectedBrowser?: string | null;
  browserDiagnostics?: any;
  issues: string[];
}

// Active download processes mapped by jobId
export const activeDownloads = new Map<string, any>();

const isDebug = process.env.DEBUG === "true" || process.env.COOKIE_DEBUG === "1";

/**
 * Extracts YouTube video ID from various URL formats.
 */
export function extractVideoId(url: string): string | null {
  try {
    const parsed = new URL(url);
    const host = parsed.hostname.toLowerCase();
    
    if (host.includes("youtu.be")) {
      return parsed.pathname.slice(1).split("?")[0].split("/")[0] || null;
    }
    
    if (host.includes("youtube.com")) {
      if (parsed.pathname === "/watch") {
        return parsed.searchParams.get("v");
      }
      if (parsed.pathname.startsWith("/shorts/")) {
        return parsed.pathname.split("/")[2] || null;
      }
      if (parsed.pathname.startsWith("/embed/") || parsed.pathname.startsWith("/v/")) {
        return parsed.pathname.split("/")[2] || null;
      }
    }
  } catch {}
  return null;
}

/**
 * Validates whether a given string is a valid YouTube URL.
 */
export function isValidYouTubeUrl(url: string): boolean {
  return extractVideoId(url) !== null;
}

/**
 * Auto-detects the first accessible browser with unlocked cookies on the host system.
 */
export function detectBrowserCookies(): string | null {
  return getAccessibleBrowser();
}

/**
 * Validates system dependencies (yt-dlp, ffmpeg, browser cookies).
 */
export async function validateDependencies(): Promise<DependencyStatus> {
  const issues: string[] = [];
  let ytDlpAvailable = false;
  let ffmpegAvailable = false;

  // 1. Check yt-dlp
  try {
    execSync("python -m yt_dlp --version", { stdio: "ignore", timeout: 5000 });
    ytDlpAvailable = true;
  } catch {
    issues.push("yt-dlp is not installed or not accessible via 'python -m yt_dlp'.");
  }

  // 2. Check ffmpeg
  try {
    execSync("ffmpeg -version", { stdio: "ignore", timeout: 5000 });
    ffmpegAvailable = true;
  } catch {
    issues.push("FFmpeg is not installed or not in system PATH.");
  }

  const detectedBrowser = detectBrowserCookies();
  const browserDiagnostics = getBrowserDiagnostics();

  return {
    ok: ytDlpAvailable && ffmpegAvailable,
    ytDlpAvailable,
    ffmpegAvailable,
    detectedBrowser,
    browserDiagnostics,
    issues,
  };
}

/**
 * Reads local YouTube download cache.
 */
function readCache(): Record<string, { filePath: string; title: string; size: number; downloadedAt: string }> {
  try {
    if (fs.existsSync(cacheFilePath)) {
      const data = fs.readFileSync(cacheFilePath, "utf-8");
      return JSON.parse(data);
    }
  } catch {}
  return {};
}

/**
 * Writes to local YouTube download cache.
 */
function writeCache(videoId: string, entry: { filePath: string; title: string; size: number; downloadedAt: string }) {
  try {
    const cache = readCache();
    cache[videoId] = entry;
    fs.mkdirSync(path.dirname(cacheFilePath), { recursive: true });
    fs.writeFileSync(cacheFilePath, JSON.stringify(cache, null, 2), "utf-8");
  } catch (err) {
    console.error("[YouTube Cache] Failed to write cache:", err);
  }
}

/**
 * Translates raw yt-dlp stderr into user-friendly error messages and retryability flag.
 */
function translateError(stderr: string, activeBrowser?: string | null): { userMessage: string; isRetryable: boolean; isCookieError: boolean } {
  const lower = stderr.toLowerCase();

  if (lower.includes("could not copy") || lower.includes("cookie database") || lower.includes("cookies-from-browser") || lower.includes("dpapi")) {
    if (activeBrowser) {
      markBrowserInaccessible(activeBrowser, "database locked or inaccessible");
    }
    return {
      userMessage: "Browser cookie database was inaccessible. Continuing download directly...",
      isRetryable: true,
      isCookieError: true,
    };
  }

  if (lower.includes("sign in to confirm") || lower.includes("bot")) {
    return {
      userMessage: "YouTube is requesting authentication. Please ensure the video is public or try a different link.",
      isRetryable: true,
      isCookieError: false,
    };
  }

  if (lower.includes("video unavailable") || lower.includes("this video has been removed")) {
    return {
      userMessage: "This YouTube video is unavailable or has been removed.",
      isRetryable: false,
      isCookieError: false,
    };
  }

  if (lower.includes("private video")) {
    return {
      userMessage: "This YouTube video is private and cannot be accessed.",
      isRetryable: false,
      isCookieError: false,
    };
  }

  if (lower.includes("http error 429") || lower.includes("too many requests")) {
    return {
      userMessage: "YouTube is temporarily rate-limiting requests. Please wait a moment and try again.",
      isRetryable: true,
      isCookieError: false,
    };
  }

  if (lower.includes("http error 403")) {
    return {
      userMessage: "Access forbidden by YouTube (HTTP 403). Retrying...",
      isRetryable: true,
      isCookieError: false,
    };
  }

  if (lower.includes("network") || lower.includes("timed out") || lower.includes("incompleteread")) {
    return {
      userMessage: "Network connectivity issue while fetching video from YouTube.",
      isRetryable: true,
      isCookieError: false,
    };
  }

  return {
    userMessage: "Failed to download video from YouTube. Please verify the URL and try again.",
    isRetryable: true,
    isCookieError: false,
  };
}

/**
 * Builds arguments array for yt-dlp execution.
 *
 * Cookie priority:
 *   1. cookies.txt file in storage/ → unlocks 1080p / 2K / 4K DASH streams (best quality)
 *   2. Browser cookies (--cookies-from-browser) → HD DASH streams if browser is accessible
 *   3. No cookies + android,web client → only 360p progressive stream (fallback)
 */
function buildYtDlpArgs(extraArgs: string[], url: string, activeBrowser?: string | null): string[] {
  const args = ["-m", "yt_dlp"];

  // Add JS runtimes ('node' is valid for yt-dlp)
  args.push("--js-runtimes", "node");

  // YouTube requires a JS challenge solver; fetch it from yt-dlp's GitHub
  args.push("--remote-components", "ejs:github");

  // Resilience: retry on transient CDN errors
  args.push("--retries", "10");
  args.push("--fragment-retries", "10");

  // ── Cookie Authentication (Priority Order) ──────────────────────────────
  const cookiesFilePath = path.join(storageRoot, "cookies.txt");
  const hasCookiesFile = fs.existsSync(cookiesFilePath);

  if (hasCookiesFile) {
    // Priority 1: cookies.txt — provides full HD/4K DASH stream access
    args.push("--cookies", cookiesFilePath);
    console.log("[YouTube] Using cookies.txt for authentication → HD quality enabled");
  } else {
    // Priority 2: browser cookies (may be locked/inaccessible on Windows)
    const browser = activeBrowser !== undefined ? activeBrowser : getAccessibleBrowser();
    if (browser) {
      args.push("--cookies-from-browser", browser);
      console.log(`[YouTube] Using browser cookies (${browser}) for authentication`);
    } else {
      // Priority 3: No cookies — force android,web client to get at least 360p
      // (default android_vr client returns HD URLs but CDN 403s them without auth)
      args.push("--extractor-args", "youtube:player_client=android,web");
      console.log("[YouTube] No cookies available → falling back to 360p (add storage/cookies.txt for HD)");
    }
  }
  // ────────────────────────────────────────────────────────────────────────

  args.push(...extraArgs);
  args.push(url);
  return args;
}

/**
 * Retrieve metadata (title and duration) for a YouTube URL using yt-dlp --dump-json with retries and cookie fallback.
 */
export async function getVideoInfo(url: string, retriesLeft = 2, activeBrowser?: string | null): Promise<YouTubeInfo> {
  const videoId = extractVideoId(url);
  if (!videoId) {
    throw new Error("Invalid YouTube URL. Please provide a valid YouTube video link.");
  }

  // Check cache first for metadata
  const cache = readCache();
  if (cache[videoId] && fs.existsSync(cache[videoId].filePath)) {
    return {
      title: cache[videoId].title,
      duration: 0,
      videoId,
    };
  }

  const currentBrowser = activeBrowser !== undefined ? activeBrowser : getAccessibleBrowser();

  return new Promise((resolve, reject) => {
    const args = buildYtDlpArgs(["--dump-json", "--no-playlist"], url, currentBrowser);
    const child = spawn("python", args);

    let stdout = "";
    let stderr = "";

    child.stdout.on("data", (data) => {
      stdout += data.toString();
    });

    child.stderr.on("data", (data) => {
      stderr += data.toString();
    });

    child.on("close", async (code) => {
      if (code !== 0) {
        if (isDebug) console.log(`[YouTube Metadata Stderr]:`, stderr);
        const { userMessage, isRetryable, isCookieError } = translateError(stderr, currentBrowser);
        if (isRetryable && retriesLeft > 0) {
          const nextBrowser = isCookieError ? getAccessibleBrowser() : currentBrowser;
          console.warn(`[YouTube Metadata Retry] Retrying metadata fetch for ${url} (browser: ${nextBrowser || "none"}). (${retriesLeft} retries left)`);
          await new Promise((r) => setTimeout(r, 1000));
          try {
            const result = await getVideoInfo(url, retriesLeft - 1, nextBrowser);
            resolve(result);
          } catch (err) {
            reject(err);
          }
          return;
        }
        reject(new Error(userMessage));
        return;
      }

      try {
        const info = JSON.parse(stdout);
        resolve({
          title: info.title || "YouTube Video",
          duration: info.duration || 0,
          thumbnailUrl: info.thumbnail || (videoId ? `https://i.ytimg.com/vi/${videoId}/hqdefault.jpg` : null),
          videoId,
        });
      } catch {
        reject(new Error("Failed to parse YouTube video metadata."));
      }
    });
  });
}

/**
 * Start downloading a YouTube video asynchronously in the background with auto-retry and cache support.
 */
export function startYouTubeDownload(
  jobId: string,
  url: string,
  title: string,
  retryCount = 0,
  activeBrowser?: string | null
): void {
  const uploadDir = ensureJobUploadDir(jobId);
  const destFile = path.join(uploadDir, "input.mp4");
  const videoId = extractVideoId(url);

  // ── Cache Lookup ──
  if (videoId) {
    const cache = readCache();
    const cachedEntry = cache[videoId];
    if (cachedEntry && fs.existsSync(cachedEntry.filePath)) {
      const cachedSize = fs.statSync(cachedEntry.filePath).size;
      if (cachedSize > 0) {
        console.log(`[YouTube Cache Hit] Reusing cached file for video ID ${videoId}`);
        try {
          fs.copyFileSync(cachedEntry.filePath, destFile);
          const originalFileName = `${title}.mp4`;
          writeProject(jobId, {
            name: title,
            originalFileName,
            status: "uploading",
            storageBytes: cachedSize,
          });

          io.emit("youtube:progress", {
            jobId,
            progress: 100,
            status: "complete",
            stage: "READY",
            stageText: "Video Ready",
            result: {
              jobId,
              originalName: originalFileName,
              storedName: "input.mp4",
              size: cachedSize,
              mimetype: "video/mp4",
              uploadedAt: new Date().toISOString(),
            },
          });
          return;
        } catch (err) {
          console.warn(`[YouTube Cache Warning] Copying cached file failed, proceeding with download:`, err);
        }
      }
    }
  }

  // ── Fresh Download via yt-dlp ──
  const currentBrowser = activeBrowser !== undefined ? activeBrowser : getAccessibleBrowser();

  const extraArgs = [
    "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
    "--merge-output-format", "mp4",
    "--no-playlist",
    "--continue",
    "-o", destFile,
  ];

  const args = buildYtDlpArgs(extraArgs, url, currentBrowser);
  const child = spawn("python", args);

  activeDownloads.set(jobId, child);

  let lastStderr = "";

  child.stdout.on("data", (chunk) => {
    const output = chunk.toString();
    const match = output.match(/\[download\]\s+([\d.]+)%(?:\s+of\s+~?([\d.]+\w+))?(?:\s+at\s+([\d.]+\w+\/s))?(?:\s+ETA\s+([\d:]+))?/);
    if (match) {
      const progress = parseFloat(match[1]);
      const totalSizeStr = match[2] || "";
      const speedStr = match[3] || "";
      const etaStr = match[4] || "";

      let stage = "DOWNLOADING";
      let stageText = `Downloading video (${progress.toFixed(0)}%)`;
      if (progress >= 99) {
        stage = "PROCESSING";
        stageText = "Processing video stream & thumbnail...";
      }

      io.emit("youtube:progress", {
        jobId,
        progress: Math.min(99, progress),
        status: "downloading",
        stage,
        stageText,
        totalSizeStr,
        speedStr,
        etaStr,
      });
    }
  });

  child.stderr.on("data", (data) => {
    const str = data.toString();
    lastStderr += str;
    if (isDebug) {
      console.log(`[YouTube Download Stderr] [${jobId}]:`, str);
    }
  });

  child.on("close", async (code) => {
    activeDownloads.delete(jobId);

    if (code !== 0) {
      const { userMessage, isRetryable, isCookieError } = translateError(lastStderr, currentBrowser);
      const maxRetries = 2;

      if (isRetryable && retryCount < maxRetries) {
        const nextBrowser = isCookieError ? getAccessibleBrowser() : currentBrowser;
        const backoffMs = (retryCount + 1) * 1500;
        console.warn(`[YouTube Download Retry] Job ${jobId} failed (exit code ${code}). Retrying in ${backoffMs}ms with browser=${nextBrowser || "none"}... (Attempt ${retryCount + 1}/${maxRetries})`);

        io.emit("youtube:progress", {
          jobId,
          progress: 0,
          status: "downloading",
          message: isCookieError
            ? "Retrying download with alternative authentication source..."
            : `Network glitch detected. Retrying download (${retryCount + 1}/${maxRetries})...`,
        });

        await new Promise((r) => setTimeout(r, backoffMs));
        startYouTubeDownload(jobId, url, title, retryCount + 1, nextBrowser);
        return;
      }

      console.error(`[YouTube Download Failed] [${jobId}] exit code: ${code}, error: ${userMessage}`);
      writeProject(jobId, { status: "failed" });
      io.emit("youtube:progress", {
        jobId,
        progress: 0,
        status: "failed",
        error: userMessage,
      });
      return;
    }

    // Verify downloaded file size
    let size = 0;
    try {
      if (fs.existsSync(destFile)) {
        size = fs.statSync(destFile).size;
      }
    } catch (err) {
      console.error(`Failed to read size for ${destFile}:`, err);
    }

    if (size === 0) {
      writeProject(jobId, { status: "failed" });
      io.emit("youtube:progress", {
        jobId,
        progress: 0,
        status: "failed",
        error: "Downloaded video file is empty. Please try another URL.",
      });
      return;
    }

    // Save to cache
    if (videoId) {
      writeCache(videoId, {
        filePath: destFile,
        title,
        size,
        downloadedAt: new Date().toISOString(),
      });
    }

    const originalFileName = `${title}.mp4`;
    writeProject(jobId, {
      name: title,
      originalFileName,
      status: "uploading",
      storageBytes: size,
    });

    io.emit("youtube:progress", {
      jobId,
      progress: 100,
      status: "complete",
      result: {
        jobId,
        originalName: originalFileName,
        storedName: "input.mp4",
        size,
        mimetype: "video/mp4",
        uploadedAt: new Date().toISOString(),
      },
    });
  });
}

/**
 * Cancel any ongoing YouTube download for a job.
 */
export function cancelYouTubeDownload(jobId: string): void {
  const child = activeDownloads.get(jobId);
  if (child) {
    child.kill("SIGTERM");
    activeDownloads.delete(jobId);
  }
}
