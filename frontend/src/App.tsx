import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { usePipelineSocket } from "./hooks/usePipelineSocket";
import { io } from "socket.io-client";
import { useProcessingStore } from "./stores/processingStore";
import { useResultsStore } from "./stores/resultsStore";
import { useSettingsStore } from "./stores/settingsStore";
import { useUploadStore } from "./stores/uploadStore";
import { CaptionStyle, TranslationLanguage } from "./types/settings";
import { ResultsResponse } from "./types/results";
import { UploadResponse } from "./types/upload";
import { ProjectsDashboard } from "./components/Dashboard/ProjectsDashboard";
import { useSessionPersistence, loadSession, saveSession, clearSession, validateSession } from "./hooks/useSessionRecovery";

import { UploadSection } from "./components/Upload/UploadSection";
import { UploadPreview } from "./components/Upload/UploadPreview";
import { YouTubeImportProgress, ImportProgressData } from "./components/Upload/YouTubeImportProgress";
import { ProcessingSettings } from "./components/Settings/ProcessingSettings";
import { CaptionSettings } from "./components/Settings/CaptionSettings";
import { LayoutSettings } from "./components/Settings/LayoutSettings";
import { TranslationSettings } from "./components/Settings/TranslationSettings";
import { ProgressPanel } from "./components/Processing/ProgressPanel";
import { LogsPanel } from "./components/Processing/LogsPanel";
import { ResultsPage } from "./components/Results/ResultsPage";

// ─── Caption Style Data ────────────────────────────────────────────────────────

const captionStyles: Array<{ id: CaptionStyle; label: string; sample: string }> = [
  { id: "classic-white", label: "Classic White", sample: "Clean white text" },
  { id: "boxed", label: "Boxed", sample: "Opaque background box" },
  { id: "outline", label: "Outline", sample: "Thick black outline" },
  { id: "bold-pop", label: "Bold Pop", sample: "Pops on playback" },
  { id: "karaoke-bounce", label: "Karaoke Bounce", sample: "Bouncing karaoke" },
  { id: "minimal", label: "Minimalist", sample: "Simple layout" },
  { id: "creator", label: "Creator Pro", sample: "Bold fonts, creators' choice" },
  { id: "viral-shorts", label: "Viral Shorts", sample: "Impactful viral format" },
  { id: "tiktok", label: "TikTok Style", sample: "Sleek social media" },
  { id: "podcast", label: "Podcast Style", sample: "Classic talk show layout" },
];

const languages: Array<{ id: TranslationLanguage; label: string }> = [
  { id: "es", label: "Spanish" },
  { id: "hi", label: "Hindi" },
  { id: "fr", label: "French" },
  { id: "de", label: "German" },
  { id: "pt", label: "Portuguese" },
];

const classicWhitePreview = (
  <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
    <span className="text-white">Create</span>
    <span className="text-white font-extrabold scale-110">Viral</span>
    <span className="text-white">Shorts</span>
  </div>
);

const captionStylePreviews: Record<CaptionStyle, React.ReactNode> = {
  "classic-white": classicWhitePreview,
  "green-highlight": classicWhitePreview,
  "yellow-highlight": classicWhitePreview,
  "blue-highlight": classicWhitePreview,
  "red-highlight": classicWhitePreview,
  "boxed": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
      <span className="text-white">Create</span>
      <span className="bg-white text-black px-2 py-0.5 rounded font-extrabold shadow-md">Viral</span>
      <span className="text-white">Shorts</span>
    </div>
  ),
  "outline": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
      <span className="text-white" style={{ textShadow: "1px 1px 2px black" }}>Create</span>
      <span className="text-white font-extrabold scale-105" style={{ textShadow: "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000" }}>Viral</span>
      <span className="text-white" style={{ textShadow: "1px 1px 2px black" }}>Shorts</span>
    </div>
  ),
  "bold-pop": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-black uppercase">
      <span className="text-gray-300 scale-90">Create</span>
      <span className="text-amber-300 font-black scale-125 tracking-wider">Viral</span>
      <span className="text-gray-300 scale-90">Shorts</span>
    </div>
  ),
  "karaoke-bounce": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
      <span className="text-gray-300">Create</span>
      <span className="text-blue-400 font-extrabold -translate-y-1 scale-110 animate-bounce">Viral</span>
      <span className="text-gray-300">Shorts</span>
    </div>
  ),
  "minimal": (
    <div className="flex gap-1.5 justify-center items-center text-md font-medium tracking-tight text-gray-300">
      <span>Create</span>
      <span className="text-white font-semibold">Viral</span>
      <span>Shorts</span>
    </div>
  ),
  "creator": (
    <div className="flex gap-1.5 justify-center items-center text-xl font-black italic uppercase">
      <span className="text-white">Create</span>
      <span className="text-yellow-300 font-black scale-110">Viral</span>
      <span className="text-white">Shorts</span>
    </div>
  ),
  "viral-shorts": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-black uppercase text-white" style={{ textShadow: "2px 2px 0 #000" }}>
      <span>Create</span>
      <span className="text-yellow-400 font-black scale-110">Viral</span>
      <span>Shorts</span>
    </div>
  ),
  "tiktok": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold bg-black/60 px-3 py-1 rounded-md">
      <span className="text-white">Create</span>
      <span className="text-blue-400 font-extrabold">Viral</span>
      <span className="text-white">Shorts</span>
    </div>
  ),
  "podcast": (
    <div className="flex gap-1.5 justify-center items-center text-md font-semibold bg-black/80 px-2 py-0.5 rounded border border-gray-600">
      <span className="text-gray-200">Create</span>
      <span className="text-yellow-400 font-bold">Viral</span>
      <span className="text-gray-200">Shorts</span>
    </div>
  ),
  "word-highlight": classicWhitePreview,
  "boxed-background": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
      <span className="text-white">Create</span>
      <span className="bg-blue-600 text-white px-2 py-0.5 rounded font-extrabold">Viral</span>
      <span className="text-white">Shorts</span>
    </div>
  ),
  "outline-shadow": (
    <div className="flex gap-1.5 justify-center items-center text-lg font-bold">
      <span className="text-white" style={{ textShadow: "1px 1px 2px black" }}>Create</span>
      <span className="text-yellow-300 font-extrabold scale-105" style={{ textShadow: "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000" }}>Viral</span>
      <span className="text-white" style={{ textShadow: "1px 1px 2px black" }}>Shorts</span>
    </div>
  ),
};

// ─── Translation Popover Component ──────────────────────────────────────────────
const TranslationPopover: React.FC<{
  settings: any;
  languages: any[];
  toggleLanguage: (id: TranslationLanguage) => void;
}> = ({ settings, languages, toggleLanguage }) => {
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!isOpen) return;

    const handleClickOutside = (e: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(e.target as Node)) {
        setIsOpen(false);
      }
    };

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    document.addEventListener("keydown", handleKeyDown);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  return (
    <div className="relative" ref={containerRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="text-xs font-medium text-gray-500 hover:text-gray-950 flex items-center gap-1.5 select-none transition-colors px-2.5 py-1.5 rounded-lg hover:bg-gray-100"
      >
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <path d="M12.87 15.07l-2.54-2.51.03-.03A17.52 17.52 0 0014.07 6H17V4h-7V2H8v2H1v2h11.17C11.5 7.92 10.44 9.75 9 11.35 8.07 10.32 7.3 9.19 6.69 8h-2c.73 1.63 1.73 3.17 2.98 4.56l-5.09 5.02L4 19l5-5 3.11 3.11.76-2.04zM18.5 10h-2L12 22h2l1.12-3h4.75L21 22h2l-4.5-12zm-2.62 7l1.62-4.33L19.12 17h-3.24z"/>
        </svg>
        <span>Translation</span>
      </button>

      {isOpen && (
        <div className="absolute right-0 top-full mt-2 z-50 bg-white border border-gray-200 rounded-xl shadow-xl p-4 min-w-[280px] animate-fade-in">
          <TranslationSettings
            settings={settings}
            languages={languages}
            toggleLanguage={toggleLanguage}
          />
        </div>
      )}
    </div>
  );
};

// ─── Wizard Step Types ─────────────────────────────────────────────────────────
type WizardStep = "upload" | "config" | "captions" | "generate" | "processing" | "results";
type AppView = "dashboard" | "wizard";

const WIZARD_STEPS: Array<{ id: WizardStep; label: string }> = [
  { id: "upload", label: "Upload" },
  { id: "config", label: "Configure AI" },
  { id: "captions", label: "Captions" },
  { id: "generate", label: "Generate" },
];

// ─── Stepper Component ─────────────────────────────────────────────────────────
function WizardStepper({
  currentStep,
  onStepClick,
  hasFile,
}: {
  currentStep: WizardStep;
  onStepClick: (step: WizardStep) => void;
  hasFile: boolean;
}) {
  const stepIds = WIZARD_STEPS.map((s) => s.id);
  const currentIndex = stepIds.indexOf(currentStep);

  return (
    <div className="stepper">
      {WIZARD_STEPS.map((step, idx) => {
        const isDone = idx < currentIndex;
        const isActive = step.id === currentStep;
        // Clickable if: already done, OR it's the upload step (always), OR active (noop)
        // Not clickable if: it's a future step we haven't reached yet
        const canClick = isDone || step.id === "upload";
        return (
          <React.Fragment key={step.id}>
            <div className="stepper-step">
              <button
                type="button"
                disabled={!canClick && !isActive}
                onClick={() => canClick && onStepClick(step.id)}
                className={`stepper-dot ${
                  isDone ? "done" : isActive ? "active" : ""
                } ${
                  canClick && !isActive ? "cursor-pointer hover:opacity-80 transition-opacity" : ""
                } ${!canClick && !isActive ? "cursor-default" : ""}`}
                aria-label={`Go to ${step.label}`}
              >
                {isDone ? (
                  <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                ) : (
                  idx + 1
                )}
              </button>
              <button
                type="button"
                disabled={!canClick && !isActive}
                onClick={() => canClick && onStepClick(step.id)}
                className={`stepper-label ${
                  isDone ? "done" : isActive ? "active" : ""
                } ${
                  canClick && !isActive ? "cursor-pointer hover:text-gray-950 transition-colors" : ""
                } ${!canClick && !isActive ? "cursor-default" : ""}`}
              >
                {step.label}
              </button>
            </div>
            {idx < WIZARD_STEPS.length - 1 && (
              <div className={`stepper-connector ${isDone ? "done" : ""}`} />
            )}
          </React.Fragment>
        );
      })}
    </div>
  );
}

// ─── Main App ─────────────────────────────────────────────────────────────────
export function App() {
  usePipelineSocket();

  // Read initial saved workspace session synchronously on mount
  const initialSession = useMemo(() => loadSession(), []);

  // Wizard + view state
  const [appView, setAppView] = useState<AppView>(() => {
    if (initialSession?.activeJobId && (initialSession.appView === "wizard" || initialSession.wizardStep)) {
      return "wizard";
    }
    return "dashboard";
  });
  const [wizardStep, setWizardStep] = useState<WizardStep>(() => {
    if (initialSession?.wizardStep) {
      return initialSession.wizardStep as WizardStep;
    }
    return "upload";
  });
  // projectKey forces a clean re-mount of the wizard when starting a new project
  const [projectKey, setProjectKey] = useState(0);
  const [logsOpen, setLogsOpen] = useState(false);
  const [processMessage, setProcessMessage] = useState<string | null>(null);
  const [hasMusicLibrary, setHasMusicLibrary] = useState(false);
  const [musicDownloading, setMusicDownloading] = useState(false);
  const [missingSourceVideo, setMissingSourceVideo] = useState(false);
  const [isDownloadingYoutube, setIsDownloadingYoutube] = useState(false);
  const [importProgress, setImportProgress] = useState<ImportProgressData | null>(null);
  const [lastSubmittedUrl, setLastSubmittedUrl] = useState<string>("");
  const [isBackendOffline, setIsBackendOffline] = useState(false);
  const [memes, setMemes] = useState<any[]>([]);
  const [musicTracks, setMusicTracks] = useState<any[]>([]);
  const [sessionRestored, setSessionRestored] = useState(false);

  // Stores
  const { error, file, job, previewUrl, progress, setError, setFile, setJob, setProgress } = useUploadStore();
  const { activeJobId, logs, percent: pipelinePercent, resetProcessing, stages, status, clearProcessing, initProcessing, restorePipelineProgress, setStatus } = useProcessingStore();
  const {
    clips, selectedClipId, selectedClipIds, editorOpen, editorTab, saving, clipEdits,
    setClips, setSelectedClipId, toggleClip, updateClipTrim, openEditor, closeEditor,
    setEditorTab, setSaving, updateClipEdit, applyEditsToClip, renderingClips, setRenderingClip,
  } = useResultsStore();
  const { settings, setSettings, updateSetting } = useSettingsStore();

  // ── Session persistence — save workspace state to local & session storage ────
  useSessionPersistence({ activeJobId, appView, wizardStep, selectedClipId });

  // ── Auto-sync lastActiveStep & settings to backend for project restoration ──
  useEffect(() => {
    if (!activeJobId) return;
    fetch(`http://localhost:3001/api/projects/${activeJobId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lastActiveStep: wizardStep, settings }),
    }).catch(() => {});
  }, [activeJobId, wizardStep, settings]);

  // ── Open existing project from dashboard or session ──────────────────────
  const openProject = useCallback(async (jobId: string, targetStepOverride?: WizardStep) => {
    setProcessMessage(null);
    try {
      // 1. Fetch stored project metadata & settings
      let projectData: any = null;
      try {
        const projRes = await fetch(`http://localhost:3001/api/projects/${jobId}`);
        if (projRes.ok) {
          projectData = await projRes.json();
          if (projectData.settings) {
            const { setSettings } = useSettingsStore.getState();
            setSettings(projectData.settings);
          }
          // Restore job & file in uploadStore so Generate button & Stepper navigation are enabled
          const { setJob, setFile } = useUploadStore.getState();
          setJob({
            jobId,
            originalName: projectData.originalFileName || jobId,
            storedName: projectData.originalFileName || jobId,
            size: projectData.storageBytes || 0,
            mimetype: "video/mp4",
            uploadedAt: projectData.createdAt || new Date().toISOString(),
          });
          if (projectData.originalFileName) {
            setFile(
              { name: projectData.originalFileName, size: projectData.storageBytes || 0 },
              `http://localhost:3001/api/upload/${jobId}/video`
            );
          }
        }
      } catch {}

      // Always fetch clips if available
      try {
        const clipsRes = await fetch(`http://localhost:3001/api/results/${jobId}`);
        if (clipsRes.ok) {
          const clipsData = await clipsRes.json();
          setClips(clipsData.clips || []);
        }
      } catch {}

      // Check if original source video exists
      try {
        const sourceRes = await fetch(`http://localhost:3001/api/storage/check-source/${jobId}`);
        if (sourceRes.ok) {
          const sourceData = await sourceRes.json();
          setMissingSourceVideo(!sourceData.exists);
        }
      } catch {
        setMissingSourceVideo(false);
      }

      // 2. Fetch current pipeline process status
      const res = await fetch(`http://localhost:3001/api/process/${jobId}/status`);
      const statusData = res.ok ? await res.json() : null;

      const isActivelyRunning = statusData?.status === "running";
      const isComplete = statusData?.status === "complete" || projectData?.status === "complete";
      const lastStep = projectData?.lastActiveStep as WizardStep | undefined;

      // 3. Step Restoration Logic
      if (isActivelyRunning) {
        initProcessing(jobId, "running");
        restorePipelineProgress(statusData?.percent ?? 0, statusData?.stages ?? [], statusData?.logs ?? []);
        setWizardStep("processing");
      } else if (projectData?.status === "processing" && lastStep === "processing") {
        // Backend process crashed/interrupted mid-run — resume from checkpoint
        initProcessing(jobId, "running");
        restorePipelineProgress(statusData?.percent ?? 0, statusData?.stages ?? [], statusData?.logs ?? []);
        try {
          await fetch(`http://localhost:3001/api/process/${jobId}/resume`, { method: "POST" });
        } catch {}
        setWizardStep("processing");
      } else if (projectData?.status === "failed" && lastStep === "processing") {
        initProcessing(jobId, "failed");
        restorePipelineProgress(statusData?.percent ?? 0, statusData?.stages ?? [], statusData?.logs ?? []);
        setWizardStep("processing");
      } else {
        initProcessing(jobId, isComplete ? "complete" : "idle");
        const validSteps: WizardStep[] = ["upload", "config", "captions", "generate", "processing", "results"];
        
        // Priority for step restoration on F5 refresh:
        // 1. Explicit targetStepOverride passed from session recovery
        // 2. lastStep saved in project metadata on backend
        // 3. Default: if project complete -> results, else -> config/upload
        const stepToRestore = targetStepOverride && validSteps.includes(targetStepOverride)
          ? targetStepOverride
          : (lastStep && validSteps.includes(lastStep))
            ? lastStep
            : (isComplete ? "results" : (projectData?.originalFileName ? "config" : "upload"));

        setWizardStep(stepToRestore);
      }

      setAppView("wizard");
    } catch (err: any) {
      setProcessMessage(`Error: Failed to open project. ${err.message || ""}`);
    }
  }, [initProcessing, restorePipelineProgress, setClips]);

  // ── Session recovery — restore workspace after F5 refresh ─────────────────
  useEffect(() => {
    if (sessionRestored) return;
    setSessionRestored(true);
    const session = loadSession();
    if (!session?.activeJobId) {
      setAppView("dashboard");
      return;
    }

    validateSession(session.activeJobId).then((valid) => {
      if (!valid) {
        clearSession();
        setAppView("dashboard");
        return;
      }
      openProject(session.activeJobId!, session.wizardStep as WizardStep);
    });
  }, [openProject, sessionRestored]); // run once on mount

  // ── Handler: navigate via stepper click ──────────────────────────────────
  const handleStepperNav = (step: WizardStep) => {
    if (step === "upload" || Boolean(job) || Boolean(activeJobId)) {
      setWizardStep(step);
      setProcessMessage(null);
    }
  };

  // ── Advance wizard when processing starts / completes ─────────────────────
  useEffect(() => {
    if (status === "running" && wizardStep !== "processing") {
      setWizardStep("processing");
    }
    if (status === "complete" && wizardStep !== "results") {
      setWizardStep("results");
    }
  }, [status, wizardStep]);

  // ── Load settings from backend ─────────────────────────────────────────────
  useEffect(() => {
    fetch("http://localhost:3001/api/settings")
      .then((r) => r.json())
      .then(setSettings)
      .catch(() => setProcessMessage("Settings loaded from local defaults."));
  }, [setSettings]);

  useEffect(() => {
    fetch("http://localhost:3001/api/settings/music-status")
      .then((r) => r.json())
      .then((d) => setHasMusicLibrary(d.hasMusic))
      .catch(() => setHasMusicLibrary(false));
  }, []);

  useEffect(() => {
    fetch("http://localhost:3001/api/health")
      .then((r) => { if (!r.ok) throw new Error(); setIsBackendOffline(false); })
      .catch(() => setIsBackendOffline(true));
  }, []);

  // ── Socket listener for retrim and youtube progress ───────────────────────
  useEffect(() => {
    const socket = io("http://localhost:3001");
    socket.on("retrim:progress", (data: { jobId: string; clipId: string; stage: string; progress: number }) => {
      if (data.stage === "Complete") {
        setRenderingClip(data.clipId, null, null);
      } else {
        setRenderingClip(data.clipId, data.stage, data.progress);
      }
    });

    socket.on("youtube:progress", (data: any) => {
      const { jobId, progress, status, stage, stageText, totalSizeStr, speedStr, etaStr, error, result } = data;
      const currentJob = useUploadStore.getState().job;
      if (!currentJob || currentJob.jobId !== jobId) return;

      if (status === "downloading") {
        setProgress(progress);
        setImportProgress((prev) => ({
          stage: (stage as any) || "DOWNLOADING",
          stageText: stageText || `Downloading video (${progress}%)...`,
          progress,
          title: prev?.title ?? currentJob.originalName,
          thumbnailUrl: prev?.thumbnailUrl,
          totalSizeStr,
          speedStr,
          etaStr,
        }));
      } else if (status === "complete" && result) {
        setJob(result);
        const resolvedSize = result.size || result.storageBytes || 0;
        setFile(
          { name: result.originalName, size: resolvedSize },
          `http://localhost:3001/api/upload/${jobId}/video`
        );
        setProgress(100);
        setIsDownloadingYoutube(false);
        setProcessMessage(null);
        setImportProgress((prev) => ({
          stage: "READY",
          stageText: "Video Ready",
          progress: 100,
          title: result.originalName,
          thumbnailUrl: prev?.thumbnailUrl,
        }));
      } else if (status === "failed") {
        setError(error || "Failed to download from YouTube.");
        setIsDownloadingYoutube(false);
        setImportProgress({
          stage: "FAILED",
          stageText: "Import Failed",
          progress: 0,
          error: error || "Failed to download from YouTube.",
        });
      }
    });

    return () => { socket.disconnect(); };
  }, [setRenderingClip, setProgress, setJob, setFile, setError]);

  // ── Load assets when editor opens ─────────────────────────────────────────
  const fetchAssets = useCallback((type: "memes" | "music") => {
    fetch(`http://localhost:3001/api/results/assets/${type}`)
      .then((r) => r.json())
      .then((d) => { if (type === "memes") setMemes(d); if (type === "music") setMusicTracks(d); })
      .catch((e) => console.error(`Error loading ${type}:`, e));
  }, []);

  useEffect(() => {
    if (editorOpen) { fetchAssets("memes"); fetchAssets("music"); }
  }, [editorOpen, editorTab, fetchAssets]);

  // ── Load results when processing completes ────────────────────────────────
  useEffect(() => {
    if (status !== "complete" || !activeJobId) return;
    fetch(`http://localhost:3001/api/results/${activeJobId}`)
      .then((r) => r.json())
      .then((result: ResultsResponse) => setClips(result.clips))
      .catch(() => setProcessMessage("Results are not ready yet."));
  }, [activeJobId, setClips, status]);

  // ── Handlers ──────────────────────────────────────────────────────────────
  const uploadFile = (selectedFile: File) => {
    setFile(selectedFile, URL.createObjectURL(selectedFile));
    setProgress(0);
    setError(null);
    setJob(null);
    const request = new XMLHttpRequest();
    const formData = new FormData();
    formData.append("video", selectedFile);
    request.upload.onprogress = (event) => {
      if (event.lengthComputable) setProgress(Math.round((event.loaded / event.total) * 100));
    };
    request.onload = () => {
      if (request.status >= 200 && request.status < 300) {
        const res = JSON.parse(request.responseText) as UploadResponse;
        setJob(res);
        setFile({ name: selectedFile.name, size: res.size || selectedFile.size }, URL.createObjectURL(selectedFile));
        setProgress(100);
        // Remain on Upload page to allow user to review video preview before clicking Continue →
        return;
      }
      setError(JSON.parse(request.responseText).message ?? "Upload failed.");
    };
    request.onerror = () => setError("Upload failed. Check the backend server.");
    request.open("POST", "http://localhost:3001/api/upload");
    request.send(formData);
  };

  // ── Replace video: delete old project from storage then re-upload ─────────
  const replaceVideo = async (selectedFile: File) => {
    const previousJobId = activeJobId || job?.jobId;
    if (previousJobId) {
      try {
        await fetch(`http://localhost:3001/api/projects/${previousJobId}`, { method: "DELETE" });
      } catch {}
    }
    // Reset all derived state from the previous upload
    setJob(null);
    setClips([]);
    setProcessMessage(null);
    clearProcessing();
    // Then run a fresh upload
    uploadFile(selectedFile);
  };

  // ── Import from YouTube: initiate async background download ─────────────
  const importFromYouTube = async (url: string) => {
    setProgress(0);
    setError(null);
    setLastSubmittedUrl(url);
    setIsDownloadingYoutube(true);
    setImportProgress({
      stage: "CONNECTING",
      stageText: "Connecting to YouTube...",
      progress: 5,
    });

    try {
      const response = await fetch("http://localhost:3001/api/upload/youtube", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ url }),
      });

      if (!response.ok) {
        const errData = await response.json();
        throw new Error(errData.message || "Failed to initialize YouTube import.");
      }

      const initData = await response.json();
      setJob({
        jobId: initData.jobId,
        originalName: initData.originalName,
        storedName: "input.mp4",
        size: 0,
        mimetype: "video/mp4",
        uploadedAt: new Date().toISOString(),
      });
      setImportProgress({
        stage: "FETCHING_METADATA",
        stageText: "Fetching video metadata...",
        progress: 25,
        title: initData.projectName,
        thumbnailUrl: initData.thumbnailUrl,
        duration: initData.duration,
      });
    } catch (err: any) {
      setError(err.message || "Failed to start YouTube import.");
      setIsDownloadingYoutube(false);
      setImportProgress({
        stage: "FAILED",
        stageText: "Import Failed",
        progress: 0,
        error: err.message || "Failed to start YouTube import.",
      });
    }
  };

  // ── Replace video with YouTube URL: delete old project from storage then import ─────
  const replaceVideoWithYouTube = async (url: string) => {
    const previousJobId = activeJobId || job?.jobId;
    if (previousJobId) {
      try {
        await fetch(`http://localhost:3001/api/projects/${previousJobId}`, { method: "DELETE" });
      } catch {}
    }
    setJob(null);
    setClips([]);
    setProcessMessage(null);
    clearProcessing();
    importFromYouTube(url);
  };

  const saveSettings = async () => {
    try {
      const response = await fetch("http://localhost:3001/api/settings", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(settings),
      });
      if (!response.ok) throw new Error();
      const updated = await response.json();
      setSettings(updated);
      setProcessMessage("✓ Saved current configuration as default for future projects!");
    } catch {
      setProcessMessage("Error: Failed to save settings to backend.");
    }
  };

  const startProcessing = async () => {
    if (!job) return;
    resetProcessing(job.jobId);
    setProcessMessage(null);
    setWizardStep("processing");
    try {
      await saveSettings();
      const response = await fetch("http://localhost:3001/api/process", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ jobId: job.jobId, settings }),
      });
      const result = await response.json();
      if (!response.ok) {
        setProcessMessage(`Error: ${result.message || "Failed to start processing."}`);
        useProcessingStore.getState().setStatus("failed" as any);
      } else {
        setProcessMessage(result.message);
      }
    } catch {
      setProcessMessage("Error: Failed to start processing. Check connection to the backend.");
      useProcessingStore.getState().setStatus("failed" as any);
    }
  };

  const cancelProcessing = async () => {
    if (!activeJobId) return;
    try {
      const response = await fetch(`http://localhost:3001/api/process/${activeJobId}/cancel`, { method: "POST" });
      const result = await response.json();
      if (!response.ok) setProcessMessage(`Error: ${result.message || "Failed to cancel."}`);
      else setProcessMessage(result.message);
    } catch {
      setProcessMessage("Error: Failed to send cancel request.");
    }
  };

  const resumeProcessing = async () => {
    if (!activeJobId) return;
    setStatus("running");
    setProcessMessage(null);
    try {
      const response = await fetch(`http://localhost:3001/api/process/${activeJobId}/resume`, {
        method: "POST",
      });
      const result = await response.json();
      if (!response.ok) {
        setProcessMessage(`Error: ${result.message || "Failed to resume processing."}`);
        setStatus("failed");
      } else {
        setProcessMessage(result.message);
      }
    } catch {
      setProcessMessage("Error: Failed to connect to server.");
      setStatus("failed");
    }
  };

  const exportSelected = () => {
    if (!activeJobId) return;
    const params = new URLSearchParams();
    selectedClipIds.forEach((id) => params.append("clipId", id));
    window.location.href = `http://localhost:3001/api/export/${activeJobId}/download?${params.toString()}`;
  };

  const toggleLanguage = (language: TranslationLanguage) => {
    const selected = settings.translationLanguages.includes(language);
    updateSetting(
      "translationLanguages",
      selected
        ? settings.translationLanguages.filter((l) => l !== language)
        : [...settings.translationLanguages, language]
    );
  };

  const handleAssetUpload = async (type: "memes", file: File) => {
    const formData = new FormData();
    formData.append("file", file);
    try {
      setSaving(true);
      const res = await fetch(`http://localhost:3001/api/results/assets/${type}`, { method: "POST", body: formData });
      const data = await res.json();
      if (res.ok && data.success) {
        fetchAssets(type);
        setProcessMessage("Asset uploaded successfully.");
      } else {
        setProcessMessage(`Error: ${data.message || "Failed to upload asset."}`);
      }
    } catch {
      setProcessMessage("Error: Failed to upload asset.");
    } finally {
      setSaving(false);
    }
  };

  const onDownloadMusic = async () => {
    setMusicDownloading(true);
    setProcessMessage(null);
    try {
      const res = await fetch("http://localhost:3001/api/settings/download-music", { method: "POST" });
      const data = await res.json();
      if (res.ok && data.success) { setHasMusicLibrary(true); setProcessMessage("Music library installed."); }
      else setProcessMessage(`Error: ${data.message || "Failed to install music library."}`);
    } catch {
      setProcessMessage("Error: Failed to connect to server.");
    } finally {
      setMusicDownloading(false);
    }
  };



  const goToDashboard = () => {
    clearProcessing();
    saveSession({
      activeJobId: null,
      appView: "dashboard",
      wizardStep: "upload",
      selectedClipId: null,
    });
    setAppView("dashboard");
  };

  const resetToNewProject = () => {
    setProjectKey((k) => k + 1);   // forces wizard section to re-mount cleanly
    setJob(null);
    setFile(null as any, "");
    setProgress(0);
    setError(null);
    setClips([]);
    setWizardStep("upload");
    setProcessMessage(null);
    clearProcessing();
    clearSession();
    setAppView("wizard");           // ensures wizard renders, not dashboard
  };

  // ─── Render ────────────────────────────────────────────────────────────────
  const showStepper = wizardStep !== "processing" && wizardStep !== "results";

  // ── Dashboard view ────────────────────────────────────────────────────────
  if (appView === "dashboard") {
    return (
      <ProjectsDashboard
        onNewProject={resetToNewProject}
        onOpenProject={openProject}
      />
    );
  }

  return (
    <div className="min-h-screen bg-white text-gray-950 font-sans">

      {/* ── Backend Offline Banner ── */}
      {isBackendOffline && (
        <div className="bg-red-50 border-b border-red-200 px-6 py-3 text-center text-xs font-medium text-red-600">
          ⚠️ Studio API server is offline. Run{" "}
          <code className="bg-red-100 px-1.5 py-0.5 rounded font-mono mx-1">npm run dev</code>
          in the backend directory.
        </div>
      )}

      {/* ── Header ── */}
      <header className="sticky top-0 z-40 bg-white/95 backdrop-blur-sm border-b border-gray-200">
        <div className="mx-auto max-w-screen-xl px-6 h-14 flex items-center justify-between">
          {/* Logo / Back to dashboard */}
          <button
            onClick={goToDashboard}
            className="flex items-center gap-2.5 group"
            title="Back to Projects"
          >
            <div className="w-7 h-7 rounded-lg bg-gray-950 flex items-center justify-center flex-shrink-0">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <span className="font-[Geist] font-semibold text-gray-950 text-sm tracking-tight select-none group-hover:text-gray-600 transition-colors">
              AI Clips Studio
            </span>
          </button>

          {/* Stepper (center, only during wizard) */}
          {showStepper && (
            <div className="hidden md:flex absolute left-1/2 -translate-x-1/2">
              <WizardStepper
                currentStep={wizardStep}
                onStepClick={handleStepperNav}
                hasFile={!!file}
              />
            </div>
          )}

          {/* Header actions */}
          <div className="flex items-center gap-3">
            {/* Back to Projects link — always visible in wizard */}
            <button
              onClick={goToDashboard}
              className="text-xs text-gray-400 hover:text-gray-700 font-medium transition-colors px-2 py-1.5 rounded-lg hover:bg-gray-100 flex items-center gap-1"
            >
              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polyline points="15 18 9 12 15 6" />
              </svg>
              Projects
            </button>
            {(wizardStep === "results" || wizardStep === "processing") && (
              <button
                onClick={resetToNewProject}
                className="text-xs text-gray-500 hover:text-gray-950 font-medium transition-colors px-3 py-1.5 rounded-lg hover:bg-gray-100"
              >
                + New Project
              </button>
            )}
          </div>
        </div>
      </header>

      {/* Source Video Missing Callout Banner */}
      {missingSourceVideo && wizardStep !== "results" && (
        <div className="max-w-2xl mx-auto px-6 pt-6">
          <div className="p-4 rounded-2xl border border-amber-200 bg-amber-50 text-xs text-amber-900 flex items-center justify-between shadow-sm animate-fade-in">
            <div className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-amber-100 flex items-center justify-center flex-shrink-0">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#d97706" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <div>
                <strong className="font-semibold block text-sm text-amber-950">Original video has been removed</strong>
                <span className="text-amber-800 mt-0.5 block">
                  Upload the source video again to regenerate clips. Existing generated clips remain accessible on the Results page.
                </span>
              </div>
            </div>
            <button
              onClick={() => setWizardStep("upload")}
              className="bg-amber-600 text-white text-xs font-semibold px-4 py-2 rounded-xl hover:bg-amber-700 transition-colors flex-shrink-0 ml-4"
            >
              Re-upload Video
            </button>
          </div>
        </div>
      )}

      {/* ── Steps 1–6 wrapped with projectKey to force clean re-mount on New Project ── */}
      <div key={projectKey}>

      {/* ── Step 1: Upload ── */}
      {wizardStep === "upload" && (
        <div className="mx-auto max-w-2xl px-6 animate-fade-in">

          {/* ── A) No file yet — show hero + drop zone or Import Progress ── */}
          {!file && (
            <div className="py-16">
              {(isDownloadingYoutube || (importProgress && importProgress.stage === "FAILED")) ? (
                <div className="max-w-xl mx-auto py-6">
                  <YouTubeImportProgress
                    progressData={importProgress!}
                    onRetry={() => lastSubmittedUrl && importFromYouTube(lastSubmittedUrl)}
                    onEditUrl={() => {
                      setImportProgress(null);
                      setIsDownloadingYoutube(false);
                    }}
                  />
                </div>
              ) : (
                <>
                  <div className="text-center mb-12">
                    <h1 className="font-[Geist] text-4xl font-semibold text-gray-950 tracking-tight">
                      Turn any video into viral clips
                    </h1>
                    <p className="mt-3 text-base text-gray-400 max-w-md mx-auto leading-relaxed">
                      Upload a long-form video and AI will find the best moments, add captions, and export vertical shorts.
                    </p>
                  </div>
                  <UploadSection
                    onFileSelected={uploadFile}
                    onYouTubeImport={importFromYouTube}
                    isSubmitting={isDownloadingYoutube}
                  />
                  {error && (
                    <p className="mt-4 text-sm text-red-600 text-center animate-fade-in">{error}</p>
                  )}
                </>
              )}
            </div>
          )}

          {/* ── B) File loaded — show current video + Replace option ── */}
          {file && (
            <div className="py-12 relative">
              <div className="mb-8 flex items-center justify-between">
                <div>
                  <h1 className="font-[Geist] text-2xl font-semibold text-gray-950 tracking-tight">Upload</h1>
                  <p className="text-sm text-gray-400 mt-1">Your video is ready. You can review or replace it below.</p>
                </div>
                {job && !isDownloadingYoutube && (
                  <span className="bg-green-50 text-green-700 text-xs px-3 py-1 rounded-full border border-green-200 font-semibold flex items-center gap-1.5 shadow-sm">
                    ✓ Ready
                  </span>
                )}
              </div>

              {/* Video Preview Card with Dark Overlay when Replacing */}
              <div className="relative rounded-2xl overflow-hidden mb-6">
                <UploadPreview
                  previewUrl={previewUrl}
                  file={file}
                  progress={progress}
                  jobId={job?.jobId}
                  error={error}
                  isDownloadingYoutube={isDownloadingYoutube}
                />

                {/* Dark Replacement Overlay */}
                {isDownloadingYoutube && importProgress && (
                  <div className="absolute inset-0 bg-black/80 backdrop-blur-md z-30 rounded-2xl flex flex-col justify-center p-6 text-white animate-fade-in">
                    <YouTubeImportProgress
                      progressData={importProgress}
                      isReplacing
                      onRetry={() => lastSubmittedUrl && importFromYouTube(lastSubmittedUrl)}
                      onEditUrl={() => {
                        setImportProgress(null);
                        setIsDownloadingYoutube(false);
                      }}
                    />
                  </div>
                )}
              </div>

              {/* Replace Video Card */}
              <div className="rounded-xl border-2 border-dashed border-gray-200 bg-gray-50 hover:border-gray-300 hover:bg-white transition-all">
                <div className="px-6 py-5">
                  <p className="text-xs font-medium text-gray-500 uppercase tracking-wide mb-3">Replace Video</p>
                  <UploadSection
                    onFileSelected={replaceVideo}
                    onYouTubeImport={replaceVideoWithYouTube}
                    compact
                    isSubmitting={isDownloadingYoutube}
                  />
                </div>
              </div>

              {/* Navigation */}
              <div className="mt-8 flex items-center justify-between">
                <div />
                <button
                  onClick={() => setWizardStep("config")}
                  disabled={!job || isDownloadingYoutube}
                  className="bg-gray-950 text-white text-sm font-semibold rounded-xl px-8 py-3.5 hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
                >
                  {isDownloadingYoutube ? "Importing Video..." : "Continue →"}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* ── Step 2: AI Config ── */}
      {wizardStep === "config" && (
        <div className="mx-auto max-w-2xl px-6 py-12 animate-slide-up">
          <div className="mb-8">
            <h1 className="font-[Geist] text-2xl font-semibold text-gray-950 tracking-tight">Configure AI</h1>
            <p className="text-sm text-gray-400 mt-1">Set how the AI will find and cut your clips.</p>
          </div>

          {/* Uploaded file preview chip */}
          {file && (
            <div className="mb-6 flex items-center gap-3 rounded-xl border border-gray-200 bg-gray-50 px-4 py-3">
              <div className="w-8 h-8 rounded-lg bg-gray-200 flex items-center justify-center flex-shrink-0">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#6b7280" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" />
                </svg>
              </div>
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-gray-950 truncate">{file.name}</p>
                <p className="text-xs text-gray-400 mt-0.5">{(file.size / (1024 * 1024)).toFixed(1)} MB</p>
              </div>
              <span className="text-xs text-green-700 bg-green-50 border border-green-200 rounded-full px-2.5 py-0.5 font-medium flex-shrink-0">
                ✓ Ready
              </span>
            </div>
          )}

          <div className="step-card">
            <ProcessingSettings
              settings={settings}
              updateSetting={updateSetting}
              saveSettings={saveSettings}
              hasMusicLibrary={hasMusicLibrary}
              musicDownloading={musicDownloading}
              onDownloadMusic={onDownloadMusic}
              processMessage={processMessage}
              onStartProcessing={startProcessing}
              job={job}
            />
          </div>

          {/* Video Layout Settings */}
          <div className="mt-6 step-card">
            <LayoutSettings
              settings={settings}
              updateSetting={updateSetting}
            />
          </div>

          <div className="mt-6 flex items-center justify-between">
            <button onClick={() => setWizardStep("upload")} className="text-sm text-gray-400 hover:text-gray-700 transition-colors">
              ← Back
            </button>
            <button
              onClick={() => setWizardStep("captions")}
              className="bg-gray-950 text-white text-sm font-medium rounded-lg px-6 py-2.5 hover:bg-gray-800 transition-colors"
            >
              Next: Captions →
            </button>
          </div>
        </div>
      )}

      {/* ── Step 3: Captions ── */}
      {wizardStep === "captions" && (
        <div className="flex flex-col animate-slide-up" style={{ height: "calc(100vh - 72px)" }}>
          {/* Slim header bar */}
          <div className="flex items-center justify-between px-5 py-3 border-b border-gray-100 bg-white flex-shrink-0">
            <div className="flex items-center gap-4">
              <button onClick={() => setWizardStep("config")} className="text-sm text-gray-400 hover:text-gray-700 transition-colors flex items-center gap-1">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M19 12H5"/><polyline points="12 19 5 12 12 5"/></svg>
                Back
              </button>
              <div>
                <h1 className="font-[Geist] text-base font-semibold text-gray-950 tracking-tight leading-tight">Caption Editor</h1>
                <p className="text-[11px] text-gray-400">Design how captions will appear on your clips</p>
              </div>
            </div>
            <div className="flex items-center gap-3">
              <TranslationPopover
                settings={settings}
                languages={languages}
                toggleLanguage={toggleLanguage}
              />
              <button
                onClick={() => setWizardStep("generate")}
                className="bg-gray-950 text-white text-sm font-medium rounded-lg px-5 py-2 hover:bg-gray-800 transition-colors flex items-center gap-1.5"
              >
                Next: Review
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14"/><polyline points="12 5 19 12 12 19"/></svg>
              </button>
            </div>
          </div>

          {/* Three-panel caption editor fills remaining space */}
          <div className="flex-1 min-h-0 overflow-hidden">
            <CaptionSettings
              settings={settings}
              updateSetting={updateSetting}
              captionStyles={captionStyles}
              captionStylePreviews={captionStylePreviews}
            />
          </div>
        </div>
      )}

      {/* ── Step 4: Generate ── */}
      {wizardStep === "generate" && (
        <div className="mx-auto max-w-xl px-6 py-16 animate-slide-up">
          <div className="text-center mb-10">
            <h1 className="font-[Geist] text-3xl font-semibold text-gray-950 tracking-tight">Ready to generate</h1>
            <p className="text-sm text-gray-400 mt-2">Review your configuration and start the AI pipeline.</p>
          </div>

          {/* Settings summary cards */}
          <div className="space-y-3 mb-10">
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Video</span>
              <span className="text-sm font-medium text-gray-950 truncate max-w-[60%] text-right">{file?.name ?? "—"}</span>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Generation Mode</span>
              <span className="text-sm font-medium text-gray-950 capitalize">{settings.clipGenerationMode ?? "auto"}</span>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Coverage</span>
              <span className="text-sm font-medium text-gray-950 capitalize">{settings.coverageMode === "best" ? "Best Moments" : "Entire Coverage"}</span>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Whisper Model</span>
              <span className="text-sm font-medium text-gray-950">{settings.whisperModel ?? "medium"}</span>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Video Layout</span>
              <span className="text-sm font-medium text-gray-950 capitalize">
                {settings.layoutMode === "full-crop"
                  ? "Full Vertical Crop"
                  : settings.layoutMode === "blur-pad"
                  ? "Smart Vertical Blur"
                  : "Auto Detection"}
              </span>
            </div>
            <div className="rounded-xl border border-gray-200 bg-gray-50 px-5 py-4 flex items-center justify-between">
              <span className="text-sm text-gray-600">Caption Style</span>
              <span className="text-sm font-medium text-gray-950">
                {captionStyles.find((s) => s.id === settings.captionStyle)?.label ?? settings.captionStyle}
              </span>
            </div>
          </div>

          {/* Error / info message */}
          {processMessage && (
            <div className={`mb-6 rounded-xl border px-4 py-3 text-sm animate-fade-in ${
              processMessage.startsWith("Error:") ? "bg-red-50 border-red-200 text-red-600" : "bg-gray-50 border-gray-200 text-gray-600"
            }`}>
              {processMessage}
            </div>
          )}

          {/* Save Settings & Generate Actions */}
          <div className="space-y-3">
            <button
              type="button"
              onClick={saveSettings}
              className="w-full bg-white border border-gray-200 text-gray-700 text-sm font-semibold rounded-xl py-3 hover:bg-gray-50 hover:border-gray-300 transition-all flex items-center justify-center gap-2 shadow-sm"
            >
              💾 Save Settings as Default
            </button>
            <button
              onClick={startProcessing}
              disabled={!job}
              className="w-full bg-gray-950 text-white text-base font-semibold rounded-xl py-4 hover:bg-gray-800 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-sm"
            >
              Generate Clips
            </button>
          </div>

          <div className="mt-4 text-center">
            <button onClick={() => setWizardStep("captions")} className="text-sm text-gray-400 hover:text-gray-700 transition-colors">
              ← Edit settings
            </button>
          </div>
        </div>
      )}

      {/* ── Step 5: Processing ── */}
      {wizardStep === "processing" && (
        <div className="min-h-[calc(100vh-56px)] bg-white animate-fade-in">
          <div className="max-w-2xl mx-auto px-6 py-12">
            <ProgressPanel
              status={status}
              activeJobId={activeJobId}
              pipelinePercent={pipelinePercent}
              stages={stages}
              onCancel={cancelProcessing}
              onResume={resumeProcessing}
              logsOpen={logsOpen}
              setLogsOpen={setLogsOpen}
            />
            {logsOpen && <LogsPanel logs={logs} />}
            {processMessage && (
              <div className={`mt-4 rounded-xl border px-4 py-3 text-sm ${
                processMessage.startsWith("Error:") ? "bg-red-50 border-red-200 text-red-600" : "bg-gray-50 border-gray-200 text-gray-600"
              }`}>
                {processMessage}
              </div>
            )}
          </div>
        </div>
      )}

      {/* ── Step 6: Results ── */}
      {wizardStep === "results" && (
        <ResultsPage
          clips={clips}
          selectedClipId={selectedClipId}
          selectedClipIds={selectedClipIds}
          editorOpen={editorOpen}
          editorTab={editorTab}
          saving={saving}
          clipEdits={clipEdits}
          setClips={setClips}
          setSelectedClipId={setSelectedClipId}
          toggleClip={toggleClip}
          updateClipTrim={updateClipTrim}
          openEditor={openEditor}
          closeEditor={closeEditor}
          setEditorTab={setEditorTab}
          setSaving={setSaving}
          updateClipEdit={updateClipEdit}
          applyEditsToClip={applyEditsToClip}
          activeJobId={activeJobId}
          renderingClips={renderingClips}
          setRenderingClip={setRenderingClip}
          setProcessMessage={setProcessMessage}
          exportSelected={exportSelected}
          memes={memes}
          musicTracks={musicTracks}
          hasMusicLibrary={hasMusicLibrary}
          settings={settings}
          handleAssetUpload={handleAssetUpload}
        />
      )}

      </div>{/* end projectKey wrapper */}
    </div>
  );
}
