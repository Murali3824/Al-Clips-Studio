import React, { useEffect, useState, useCallback, useRef } from "react";
import { Project } from "../../types/project";
import { StorageManagementPanel } from "./StorageManagementPanel";

// ─── Helpers ──────────────────────────────────────────────────────────────────

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function timeAgo(iso: string): string {
  const ms = Date.now() - new Date(iso).getTime();
  const s = Math.floor(ms / 1000);
  if (s < 60) return "just now";
  const m = Math.floor(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.floor(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.floor(h / 24);
  if (d < 30) return `${d}d ago`;
  return new Date(iso).toLocaleDateString();
}

function StatusBadge({ status }: { status: Project["status"] }) {
  const map: Record<Project["status"], { label: string; cls: string; dot: string }> = {
    complete: {
      label: "Complete",
      cls: "bg-emerald-50 text-emerald-700 border-emerald-200",
      dot: "bg-emerald-500",
    },
    processing: {
      label: "Processing",
      cls: "bg-blue-50 text-blue-700 border-blue-200",
      dot: "bg-blue-500 animate-pulse",
    },
    uploading: {
      label: "Uploading",
      cls: "bg-amber-50 text-amber-700 border-amber-200",
      dot: "bg-amber-500 animate-pulse",
    },
    failed: {
      label: "Failed",
      cls: "bg-red-50 text-red-700 border-red-200",
      dot: "bg-red-500",
    },
  };
  const { label, cls, dot } = map[status] ?? map.failed;
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2 py-0.5 rounded-full border ${cls}`}>
      <span className={`w-1.5 h-1.5 rounded-full flex-shrink-0 ${dot}`} />
      {label}
    </span>
  );
}

// ─── Inline Rename Input ───────────────────────────────────────────────────────

function InlineRename({
  value,
  onSave,
  onCancel,
}: {
  value: string;
  onSave: (name: string) => void;
  onCancel: () => void;
}) {
  const [draft, setDraft] = useState(value);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.select();
  }, []);

  return (
    <input
      ref={inputRef}
      value={draft}
      onChange={(e) => setDraft(e.target.value)}
      onKeyDown={(e) => {
        if (e.key === "Enter") onSave(draft.trim() || value);
        if (e.key === "Escape") onCancel();
      }}
      onBlur={() => onSave(draft.trim() || value)}
      onClick={(e) => e.stopPropagation()}
      className="w-full text-sm font-semibold text-gray-950 bg-white border border-blue-400 rounded px-1.5 py-0.5 outline-none ring-2 ring-blue-100 focus:ring-blue-200"
      maxLength={80}
    />
  );
}

// ─── Project Card ─────────────────────────────────────────────────────────────

function ProjectCard({
  project,
  onOpen,
  onRename,
  onDelete,
}: {
  project: Project;
  onOpen: (p: Project) => void;
  onRename: (jobId: string, name: string) => void;
  onDelete: (jobId: string) => void;
}) {
  const [renaming, setRenaming] = useState(false);
  const [imgError, setImgError] = useState(false);

  const handleRename = (name: string) => {
    setRenaming(false);
    if (name !== project.name) onRename(project.jobId, name);
  };

  const isOpenable = true;

  return (
    <div
      className={`group relative flex flex-col rounded-2xl border border-gray-200 bg-white shadow-sm overflow-hidden transition-all duration-200 hover:shadow-lg hover:-translate-y-0.5 cursor-pointer`}
      onClick={() => !renaming && onOpen(project)}
    >
      {/* Thumbnail */}
      <div className="relative w-full bg-gray-100 overflow-hidden" style={{ aspectRatio: "9/5" }}>
        {project.thumbnailUrl && !imgError ? (
          <img
            src={`http://localhost:3001${project.thumbnailUrl}`}
            alt={project.name}
            className="w-full h-full object-cover"
            onError={() => setImgError(true)}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center gap-2">
            <div className="w-12 h-12 rounded-2xl bg-gray-200 flex items-center justify-center">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            {project.status === "processing" && (
              <p className="text-xs text-gray-400 font-medium">Generating clips…</p>
            )}
            {project.status === "uploading" && (
              <p className="text-xs text-amber-500 font-medium">Uploading video…</p>
            )}
            {project.status === "failed" && (
              <p className="text-xs text-red-400 font-medium">Generation failed</p>
            )}
          </div>
        )}

        {/* Status overlay */}
        <div className="absolute top-2 left-2">
          <StatusBadge status={project.status} />
        </div>

        {/* Clip count badge */}
        {project.clipCount > 0 && (
          <div className="absolute top-2 right-2 bg-black/60 text-white text-[11px] font-semibold px-2 py-0.5 rounded-full backdrop-blur-sm">
            {project.clipCount} clip{project.clipCount !== 1 ? "s" : ""}
          </div>
        )}

        {/* Hover overlay: open hint */}
        <div className="absolute inset-0 bg-black/0 group-hover:bg-black/20 transition-colors flex items-center justify-center opacity-0 group-hover:opacity-100">
          <div className="bg-white/90 backdrop-blur-sm text-gray-950 text-xs font-semibold px-4 py-2 rounded-xl shadow-lg">
            {project.status === "processing"
              ? "Processing..."
              : project.status === "uploading"
              ? "Resume Upload →"
              : project.status === "failed"
              ? "Resume Processing →"
              : "Open Project →"}
          </div>
        </div>
      </div>

      {/* Card body */}
      <div className="flex flex-col gap-3 p-4 flex-1">
        {/* Name */}
        <div className="flex-1 min-w-0">
          {renaming ? (
            <InlineRename value={project.name} onSave={handleRename} onCancel={() => setRenaming(false)} />
          ) : (
            <h3 className="text-sm font-semibold text-gray-950 truncate leading-snug" title={project.name}>
              {project.name}
            </h3>
          )}
          <p className="text-[11px] text-gray-400 mt-0.5 truncate" title={project.originalFileName}>
            {project.originalFileName}
          </p>
        </div>

        {/* Meta row */}
        <div className="flex items-center justify-between text-[11px] text-gray-400">
          <span title={new Date(project.updatedAt).toLocaleString()}>
            {timeAgo(project.updatedAt)}
          </span>
          <span>{formatBytes(project.storageBytes)}</span>
        </div>

        {/* Action row */}
        <div
          className="flex items-center gap-1.5 pt-2 border-t border-gray-100"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            onClick={() => onOpen(project)}
            className="flex-1 text-xs font-semibold text-white bg-gray-950 rounded-lg px-3 py-1.5 hover:bg-gray-800 transition-colors"
          >
            {project.status === "processing"
              ? "Processing"
              : project.status === "uploading"
              ? "Resume Upload"
              : project.status === "failed"
              ? "Resume"
              : "Open"}
          </button>
          <button
            onClick={() => setRenaming(true)}
            title="Rename"
            className="p-1.5 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 4H4a2 2 0 00-2 2v14a2 2 0 002 2h14a2 2 0 002-2v-7" />
              <path d="M18.5 2.5a2.121 2.121 0 013 3L12 15l-4 1 1-4 9.5-9.5z" />
            </svg>
          </button>
          <button
            onClick={() => onDelete(project.jobId)}
            title="Delete project"
            className="p-1.5 rounded-lg text-gray-400 hover:text-red-600 hover:bg-red-50 transition-colors"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
              <path d="M10 11v6M14 11v6" />
              <path d="M9 6V4a1 1 0 011-1h4a1 1 0 011 1v2" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Delete Confirmation Dialog ────────────────────────────────────────────────

function DeleteConfirmDialog({
  projectName,
  onConfirm,
  onCancel,
  isDeleting,
}: {
  projectName: string;
  onConfirm: () => void;
  onCancel: () => void;
  isDeleting: boolean;
}) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in">
      <div className="w-full max-w-sm bg-white rounded-2xl shadow-2xl border border-gray-200 p-6 space-y-5 animate-scale-in">
        <div className="flex items-start gap-3">
          <div className="w-9 h-9 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
            </svg>
          </div>
          <div>
            <h3 className="text-sm font-semibold text-gray-950">Delete Project</h3>
            <p className="text-xs text-gray-500 mt-1 leading-relaxed">
              Are you sure you want to delete <strong className="text-gray-800">"{projectName}"</strong>? This will permanently remove the original video, all generated clips, captions, thumbnails, and metadata. This action cannot be undone.
            </p>
          </div>
        </div>
        <div className="flex gap-2">
          <button
            onClick={onCancel}
            disabled={isDeleting}
            className="flex-1 text-sm font-medium text-gray-600 bg-gray-100 hover:bg-gray-200 rounded-xl py-2.5 transition-colors disabled:opacity-50"
          >
            Cancel
          </button>
          <button
            onClick={onConfirm}
            disabled={isDeleting}
            className="flex-1 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl py-2.5 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
          >
            {isDeleting ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                Deleting…
              </>
            ) : (
              "Delete Forever"
            )}
          </button>
        </div>
      </div>
    </div>
  );
}

// ─── Empty State ───────────────────────────────────────────────────────────────

function EmptyState({ onNewProject }: { onNewProject: () => void }) {
  return (
    <div className="flex flex-col items-center justify-center py-28 px-6 text-center">
      <div className="w-20 h-20 rounded-3xl bg-gray-100 flex items-center justify-center mb-6 shadow-inner">
        <svg width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="#d1d5db" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
          <polygon points="23 7 16 12 23 17 23 7" />
          <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
          <line x1="12" y1="9" x2="12" y2="15" />
          <line x1="9" y1="12" x2="15" y2="12" />
        </svg>
      </div>
      <h2 className="text-xl font-semibold text-gray-950 font-[Geist] mb-2">No projects yet</h2>
      <p className="text-sm text-gray-400 max-w-xs leading-relaxed mb-8">
        Upload your first video and AI will find the best moments, add captions, and export vertical shorts automatically.
      </p>
      <button
        onClick={onNewProject}
        className="bg-gray-950 text-white text-sm font-semibold rounded-xl px-8 py-3 hover:bg-gray-800 transition-colors shadow-sm"
      >
        Upload a Video
      </button>
    </div>
  );
}

// ─── Main Dashboard ────────────────────────────────────────────────────────────

interface ProjectsDashboardProps {
  onNewProject: () => void;
  onOpenProject: (jobId: string) => void;
}

export function ProjectsDashboard({ onNewProject, onOpenProject }: ProjectsDashboardProps) {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [search, setSearch] = useState("");
  const [deleteTarget, setDeleteTarget] = useState<Project | null>(null);
  const [isDeleting, setIsDeleting] = useState(false);
  const [showStoragePanel, setShowStoragePanel] = useState(false);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const fetchProjects = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:3001/api/projects");
      if (!res.ok) throw new Error("Failed to load projects");
      const data = await res.json();
      setProjects(data.projects ?? []);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Could not connect to the backend server.");
    } finally {
      setLoading(false);
    }
  }, []);

  // Initial fetch
  useEffect(() => {
    fetchProjects();
  }, [fetchProjects]);

  // Poll while any project is processing or uploading (to pick up status changes)
  useEffect(() => {
    const hasActive = projects.some((p) => p.status === "processing" || p.status === "uploading");
    if (hasActive && !pollRef.current) {
      pollRef.current = setInterval(fetchProjects, 4000);
    } else if (!hasActive && pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [projects, fetchProjects]);

  const handleRename = async (jobId: string, name: string) => {
    try {
      const res = await fetch(`http://localhost:3001/api/projects/${jobId}`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name }),
      });
      if (!res.ok) throw new Error("Rename failed");
      setProjects((prev) =>
        prev.map((p) => (p.jobId === jobId ? { ...p, name } : p))
      );
    } catch {
      // silent — name reverts visually on next poll
    }
  };

  const handleDeleteConfirm = async () => {
    if (!deleteTarget) return;
    setIsDeleting(true);
    try {
      await fetch(`http://localhost:3001/api/projects/${deleteTarget.jobId}`, {
        method: "DELETE",
      });
      setProjects((prev) => prev.filter((p) => p.jobId !== deleteTarget.jobId));
      setDeleteTarget(null);
    } catch {
      setError("Failed to delete the project. Please try again.");
    } finally {
      setIsDeleting(false);
    }
  };

  // Compute summary stats
  const totalStorage = projects.reduce((sum, p) => sum + p.storageBytes, 0);
  const totalClips = projects.reduce((sum, p) => sum + p.clipCount, 0);

  const filtered = search.trim()
    ? projects.filter(
        (p) =>
          p.name.toLowerCase().includes(search.toLowerCase()) ||
          p.originalFileName.toLowerCase().includes(search.toLowerCase())
      )
    : projects;

  return (
    <div className="min-h-screen bg-gray-50 font-sans">

      {/* Header */}
      <header className="bg-white border-b border-gray-200 sticky top-0 z-30">
        <div className="max-w-screen-xl mx-auto px-6 h-14 flex items-center justify-between">
          {/* Logo */}
          <div className="flex items-center gap-2.5">
            <div className="w-7 h-7 rounded-lg bg-gray-950 flex items-center justify-center flex-shrink-0">
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" />
                <rect x="1" y="5" width="15" height="14" rx="2" ry="2" />
              </svg>
            </div>
            <span className="font-[Geist] font-semibold text-gray-950 text-sm tracking-tight select-none">
              AI Clips Studio
            </span>
          </div>

          {/* Actions */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setShowStoragePanel(!showStoragePanel)}
              className={`inline-flex items-center gap-1.5 text-xs font-semibold rounded-lg px-3.5 py-2 transition-colors ${
                showStoragePanel
                  ? "bg-gray-200 text-gray-950"
                  : "bg-white border border-gray-200 text-gray-700 hover:bg-gray-50"
              }`}
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
              </svg>
              Storage
            </button>
            <button
              onClick={onNewProject}
              className="inline-flex items-center gap-2 bg-gray-950 text-white text-xs font-semibold rounded-lg px-4 py-2 hover:bg-gray-800 transition-colors shadow-sm"
            >
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <line x1="12" y1="5" x2="12" y2="19" />
                <line x1="5" y1="12" x2="19" y2="12" />
              </svg>
              New Project
            </button>
          </div>
        </div>
      </header>

      {/* Page content */}
      <main className="max-w-screen-xl mx-auto px-6 py-8">

        {/* Storage Management Panel */}
        {showStoragePanel && (
          <StorageManagementPanel
            onClose={() => setShowStoragePanel(false)}
            onStorageUpdated={fetchProjects}
          />
        )}

        {/* Page title + stats */}
        <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4 mb-8">
          <div>
            <h1 className="font-[Geist] text-2xl font-semibold text-gray-950 tracking-tight">Projects</h1>
            <p className="text-sm text-gray-400 mt-1">
              {projects.length === 0
                ? "No projects yet"
                : `${projects.length} project${projects.length !== 1 ? "s" : ""} · ${totalClips} clip${totalClips !== 1 ? "s" : ""} · ${formatBytes(totalStorage)} stored`}
            </p>
          </div>

          {/* Search */}
          {projects.length > 3 && (
            <div className="relative">
              <svg className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <input
                type="text"
                placeholder="Search projects…"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-8 pr-4 py-2 text-sm bg-white border border-gray-200 rounded-lg w-52 outline-none focus:ring-2 focus:ring-gray-950/10 focus:border-gray-400 transition"
              />
            </div>
          )}
        </div>

        {/* Error banner */}
        {error && (
          <div className="mb-6 p-4 rounded-xl border border-red-200 bg-red-50 text-sm text-red-700 flex items-center gap-2">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
              <circle cx="12" cy="12" r="10" />
              <line x1="12" y1="8" x2="12" y2="12" />
              <line x1="12" y1="16" x2="12.01" y2="16" />
            </svg>
            {error}
          </div>
        )}

        {/* Loading skeleton */}
        {loading && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {[1, 2, 3].map((i) => (
              <div key={i} className="rounded-2xl border border-gray-200 bg-white overflow-hidden animate-pulse">
                <div className="bg-gray-100" style={{ aspectRatio: "9/5" }} />
                <div className="p-4 space-y-3">
                  <div className="h-4 bg-gray-100 rounded w-3/4" />
                  <div className="h-3 bg-gray-100 rounded w-1/2" />
                  <div className="h-8 bg-gray-100 rounded-lg mt-4" />
                </div>
              </div>
            ))}
          </div>
        )}

        {/* Empty state */}
        {!loading && projects.length === 0 && (
          <EmptyState onNewProject={onNewProject} />
        )}

        {/* No search results */}
        {!loading && projects.length > 0 && filtered.length === 0 && (
          <div className="text-center py-20 text-gray-400 text-sm">
            No projects match "<span className="font-medium text-gray-600">{search}</span>"
          </div>
        )}

        {/* Project cards grid */}
        {!loading && filtered.length > 0 && (
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-5">
            {filtered.map((project) => (
              <ProjectCard
                key={project.jobId}
                project={project}
                onOpen={(p) => onOpenProject(p.jobId)}
                onRename={handleRename}
                onDelete={(jobId) => setDeleteTarget(projects.find((p) => p.jobId === jobId) ?? null)}
              />
            ))}
          </div>
        )}
      </main>

      {/* Delete confirmation dialog */}
      {deleteTarget && (
        <DeleteConfirmDialog
          projectName={deleteTarget.name}
          onConfirm={handleDeleteConfirm}
          onCancel={() => setDeleteTarget(null)}
          isDeleting={isDeleting}
        />
      )}
    </div>
  );
}
