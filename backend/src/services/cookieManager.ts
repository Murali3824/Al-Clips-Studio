import { execSync } from "child_process";
import fs from "fs";
import path from "path";
import os from "os";

export const SUPPORTED_BROWSERS = [
  "chrome",
  "firefox",
  "edge",
  "brave",
  "chromium",
  "opera",
] as const;

export type BrowserName = typeof SUPPORTED_BROWSERS[number];

type BrowserStatus =
  | "available"
  | "locked"
  | "decryption_failed"
  | "not_installed"
  | "no_cookies";

interface BrowserHealthEntry {
  status: BrowserStatus;
  reason: string;
  testedAt: number;
}

// Session cache for browser health status and last working browser
const browserHealthCache = new Map<BrowserName, BrowserHealthEntry>();
let lastSuccessfulBrowser: BrowserName | null = null;

// Cache TTL: re-verify locked browsers after 30 seconds if needed
const CACHE_TTL_MS = 30000;

// Log level helper
const isDebugEnabled =
  process.env.DEBUG === "true" ||
  process.env.COOKIE_DEBUG === "1" ||
  process.env.NODE_ENV === "development_debug";

function logInfo(msg: string) {
  console.log(`[CookieManager] ${msg}`);
}

function logWarn(msg: string) {
  console.warn(`[CookieManager] ${msg}`);
}

function logDebug(msg: string, details?: any) {
  if (isDebugEnabled) {
    console.log(`[CookieManager:DEBUG] ${msg}`, details || "");
  }
}

/**
 * Fast filesystem check to see if browser data directory exists on disk.
 */
function isBrowserInstalled(browser: BrowserName): boolean {
  const isWindows = process.platform === "win32";
  const localAppData = process.env.LOCALAPPDATA || "";
  const appData = process.env.APPDATA || "";
  const home = os.homedir();

  try {
    if (isWindows) {
      switch (browser) {
        case "chrome":
          return fs.existsSync(path.join(localAppData, "Google", "Chrome", "User Data"));
        case "edge":
          return fs.existsSync(path.join(localAppData, "Microsoft", "Edge", "User Data"));
        case "brave":
          return fs.existsSync(path.join(localAppData, "BraveSoftware", "Brave-Browser", "User Data"));
        case "firefox":
          return fs.existsSync(path.join(appData, "Mozilla", "Firefox", "Profiles"));
        case "chromium":
          return fs.existsSync(path.join(localAppData, "Chromium", "User Data"));
        case "opera":
          return fs.existsSync(path.join(appData, "Opera Software", "Opera Stable"));
      }
    } else {
      // macOS / Linux path heuristics
      switch (browser) {
        case "chrome":
          return fs.existsSync(path.join(home, ".config", "google-chrome")) || fs.existsSync(path.join(home, "Library", "Application Support", "Google", "Chrome"));
        case "firefox":
          return fs.existsSync(path.join(home, ".mozilla", "firefox")) || fs.existsSync(path.join(home, "Library", "Application Support", "Firefox"));
        case "edge":
          return fs.existsSync(path.join(home, ".config", "microsoft-edge")) || fs.existsSync(path.join(home, "Library", "Application Support", "Microsoft Edge"));
        case "brave":
          return fs.existsSync(path.join(home, ".config", "BraveSoftware")) || fs.existsSync(path.join(home, "Library", "Application Support", "BraveSoftware"));
        default:
          return true; // Fallback to command probe
      }
    }
  } catch {
    return true; // If detection fails, attempt probe
  }
  return true;
}

/**
 * Probes a specific browser's cookie database for accessibility.
 */
function probeBrowserCookies(browser: BrowserName): { success: boolean; status: BrowserStatus; reason: string } {
  // Check fast filesystem install check first
  if (!isBrowserInstalled(browser)) {
    return {
      success: false,
      status: "not_installed",
      reason: "not installed",
    };
  }

  try {
    const output = execSync(
      `python -m yt_dlp --cookies-from-browser ${browser} --simulate --no-playlist "https://www.youtube.com/watch?v=BaW_jenozKc"`,
      { timeout: 4000, encoding: "utf-8", stdio: ["ignore", "pipe", "pipe"] }
    );
    logDebug(`yt-dlp probe output for ${browser}:`, output.slice(0, 200));
    return {
      success: true,
      status: "available",
      reason: "cookies loaded successfully",
    };
  } catch (error: any) {
    const stderr = (error.stderr || "").toString().toLowerCase();
    const stdout = (error.stdout || "").toString().toLowerCase();
    const combined = stderr + "\n" + stdout;

    logDebug(`yt-dlp probe error for ${browser}:`, combined);

    if (
      combined.includes("could not copy") ||
      combined.includes("cookie database") ||
      combined.includes("permission denied") ||
      combined.includes("locked")
    ) {
      return {
        success: false,
        status: "locked",
        reason: "database locked",
      };
    }

    if (combined.includes("dpapi") || combined.includes("decryption") || combined.includes("keyring")) {
      return {
        success: false,
        status: "decryption_failed",
        reason: "decryption failed",
      };
    }

    if (combined.includes("could not find") || combined.includes("no cookies") || combined.includes("browser not found")) {
      return {
        success: false,
        status: "no_cookies",
        reason: "no cookies found",
      };
    }

    return {
      success: false,
      status: "no_cookies",
      reason: "cookies inaccessible",
    };
  }
}

/**
 * Selects the best accessible browser, leveraging priority order and browser health cache.
 * Stops immediately after the first working browser is found.
 */
export function getAccessibleBrowser(): BrowserName | null {
  const now = Date.now();

  // 1. Try last known successful browser first
  if (lastSuccessfulBrowser) {
    const cached = browserHealthCache.get(lastSuccessfulBrowser);
    if (!cached || cached.status === "available" || now - cached.testedAt > CACHE_TTL_MS) {
      const probe = probeBrowserCookies(lastSuccessfulBrowser);
      browserHealthCache.set(lastSuccessfulBrowser, {
        status: probe.status,
        reason: probe.reason,
        testedAt: now,
      });

      if (probe.success) {
        logInfo(`Authentication source: ${lastSuccessfulBrowser}`);
        return lastSuccessfulBrowser;
      } else {
        logInfo(`${lastSuccessfulBrowser} unavailable (${probe.reason})`);
        lastSuccessfulBrowser = null;
      }
    }
  }

  // 2. Iterate through browsers in priority order
  for (const browser of SUPPORTED_BROWSERS) {
    if (browser === lastSuccessfulBrowser) continue;

    const cached = browserHealthCache.get(browser);
    if (cached && cached.status !== "available" && now - cached.testedAt < CACHE_TTL_MS) {
      // Skip recently failed browsers without re-probing
      logDebug(`Skipping cached failed browser ${browser} (${cached.reason})`);
      continue;
    }

    const probe = probeBrowserCookies(browser);
    browserHealthCache.set(browser, {
      status: probe.status,
      reason: probe.reason,
      testedAt: now,
    });

    if (probe.success) {
      lastSuccessfulBrowser = browser;
      logInfo(`${browser} cookies loaded successfully`);
      logInfo(`Authentication source: ${browser}`);
      return browser; // STOP IMMEDIATELY after first success
    } else {
      logInfo(`${browser} unavailable (${probe.reason})`);
    }
  }

  logInfo("Authentication source: none (proceeding without browser cookies)");
  return null;
}

/**
 * Explicitly marks a browser as inaccessible if a download process encounters a runtime error.
 */
export function markBrowserInaccessible(browser: string, reason?: string): void {
  const browserName = browser as BrowserName;
  browserHealthCache.set(browserName, {
    status: "locked",
    reason: reason || "runtime error",
    testedAt: Date.now(),
  });

  if (lastSuccessfulBrowser === browserName) {
    lastSuccessfulBrowser = null;
  }

  logInfo(`${browser} marked unavailable (${reason || "runtime error"})`);
}

/**
 * Resets the health cache and last successful browser state.
 */
export function resetBrowserCache(): void {
  browserHealthCache.clear();
  lastSuccessfulBrowser = null;
  logDebug("Browser health cache reset.");
}

/**
 * Returns current browser health diagnostics (for health check endpoints).
 */
export function getBrowserDiagnostics(): {
  activeBrowser: BrowserName | null;
  statuses: Record<string, { status: string; reason: string }>;
} {
  const statuses: Record<string, { status: string; reason: string }> = {};
  for (const [b, entry] of browserHealthCache.entries()) {
    statuses[b] = { status: entry.status, reason: entry.reason };
  }
  return {
    activeBrowser: lastSuccessfulBrowser,
    statuses,
  };
}
