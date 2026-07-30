import { useEffect } from "react";

const SESSION_KEY = "aics_workspace_session";

export interface SessionState {
  activeJobId: string | null;
  appView: "dashboard" | "wizard";
  wizardStep: string;
  selectedClipId: string | null;
}

/** Save current workspace session to both localStorage and sessionStorage. */
export function saveSession(state: SessionState): void {
  try {
    const raw = JSON.stringify(state);
    localStorage.setItem(SESSION_KEY, raw);
    sessionStorage.setItem(SESSION_KEY, raw);
  } catch {
    // Storage may be unavailable in restricted sandbox environments
  }
}

/** Load last workspace session. Returns null if none. */
export function loadSession(): SessionState | null {
  try {
    const raw = sessionStorage.getItem(SESSION_KEY) || localStorage.getItem(SESSION_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as SessionState;
  } catch {
    return null;
  }
}

/** Clear active session state. */
export function clearSession(): void {
  try {
    localStorage.removeItem(SESSION_KEY);
    sessionStorage.removeItem(SESSION_KEY);
  } catch {}
}

/**
 * Hook that automatically persists workspace session state whenever tracked values change.
 * Prevents overwriting a valid saved session on initial component mount when activeJobId is null.
 */
export function useSessionPersistence(state: SessionState): void {
  useEffect(() => {
    if (state.activeJobId) {
      saveSession(state);
    } else if (state.appView === "dashboard") {
      const existing = loadSession();
      if (!existing?.activeJobId) {
        saveSession(state);
      }
    }
  }, [state.activeJobId, state.appView, state.wizardStep, state.selectedClipId]);
}

/**
 * Validates a project session against the backend.
 * Returns true if the project still exists and is recoverable.
 */
export async function validateSession(jobId: string): Promise<boolean> {
  try {
    const res = await fetch(`http://localhost:3001/api/projects/${jobId}`);
    return res.ok;
  } catch {
    return false;
  }
}
