# Walkthrough — Project Architecture Redesign

## What Was Built

The app has been transformed from a one-session clip generator into a fully persistent, professional AI video editor with a Projects Dashboard and complete project lifecycle management.

---

## New Workflow

```
App opens → Projects Dashboard
  → Open existing project → Results workspace (all clips restored instantly)
  → New Project → Upload → Configure → Generate → Results → ← Projects
```

---

## Files Created

### Backend

| File | Purpose |
|------|---------|
| `backend/src/services/project.service.ts` | Core project CRUD: `listProjects`, `readProject`, `writeProject`, `renameProject`, `deleteProject`, `getProjectStorageBytes` |
| `backend/src/routes/projects.routes.ts` | REST API: `GET /api/projects`, `GET /api/projects/:id`, `PATCH /api/projects/:id`, `DELETE /api/projects/:id` |

### Frontend

| File | Purpose |
|------|---------|
| `frontend/src/types/project.ts` | TypeScript `Project` and `ProjectStatus` types |
| `frontend/src/hooks/useSessionRecovery.ts` | `saveSession`, `loadSession`, `clearSession`, `validateSession`, `useSessionPersistence` |
| `frontend/src/components/Dashboard/ProjectsDashboard.tsx` | Full dashboard UI with project cards, search, stats, delete dialog, empty state |

---

## Files Modified

| File | Change |
|------|--------|
| `backend/src/routes/upload.routes.ts` | Writes `project.json` immediately on upload — project appears in dashboard |
| `backend/src/services/python.service.ts` | Updates `project.json` status: `processing` on start → `complete`/`failed` on exit + clip count |
| `backend/src/server.ts` | Registers `projectsRouter` at `/api/projects` |
| `frontend/src/App.tsx` | Added `appView` state, `openProject`, fixed `resetToNewProject`, session recovery, "← Projects" back button, `key={projectKey}` for clean wizard re-mounts |
| `frontend/src/stores/processingStore.ts` | Added `clearProcessing()`, `initProcessing()`, and `restorePipelineProgress()` to support state restores without forcing status to `"running"` |
| `frontend/src/components/Processing/ProgressPanel.tsx` | Added `onResume` callback and UI Resume button for failed or interrupted jobs |

---

## Features Delivered

### 1. Projects Dashboard (new home screen)
- Shows all projects as cards sorted by last modified
- Each card: thumbnail, name, original file, status badge, clip count, storage size, time ago
- Actions: Open, Rename (inline), Delete (confirmation dialog)
- Search filter (appears when >3 projects)
- Summary stats: total projects, clips, storage
- Auto-polls every 4s when any project is processing
- Loading skeleton while fetching
- Rich empty state with CTA

### 2. Project Persistence
- Every upload creates a `project.json` in `storage/uploads/{jobId}/`
- Once processing starts, `project.json` migrates to `storage/outputs/{jobId}/`
- Status transitions: `uploading` → `processing` → `complete`/`failed`
- Project name defaults to filename without extension (underscores → spaces)

### 3. Open Existing Project / Resume Processing / Failed state (Fixed)
- Solved issue where clicking a processing card from the dashboard did nothing. All cards (complete, processing, failed) are now openable.
- Click a **Complete** project card → immediately loads all clips in Results workspace.
- Click a **Processing** project card → opens the live processing timeline and resumes watching logs and progress.
- Click a **Failed** project card → opens the failed status screen with details and a new **Resume / Retry** button to pick up where it left off.
- Integrated backend `GET /api/process/:jobId/status` to determine the exact pipeline state.

### 4. Delete Project — Full Cleanup
- Deletes `storage/uploads/{jobId}/`, `storage/outputs/{jobId}/`, `storage/temp/{jobId}/`
- No orphan files remain
- Confirmation dialog prevents accidental deletion

### 5. New Project Flow
- "New Project" button clears the session, sets wizard back to `"upload"`, resets uploads store progress and errors, and navigates cleanly to the upload step.
- Solved issue where clicking "New Project" redirected the user back to the existing "Processing your video" page.

### 6. Session Recovery (F5) (Fixed)
- Unified session recovery and dashboard clicking under the new `openProject` function.
- If page is refreshed during a running or failed job, it restores the processing status timeline and logs from the backend process status API.
- Closing the browser tab clears the session (sessionStorage behavior)
- Projects themselves live on the backend permanently

### 7. Navigation
- Logo / "AI Clips Studio" in wizard header → clicks back to Dashboard
- "← Projects" text button always visible in wizard header right area
- "← Projects" is also visible during processing and results

---

## Build Verification

| Check | Result |
|-------|--------|
| Backend `tsc --noEmit` | ✅ |
| Frontend `tsc --noEmit` | ✅ |
