import React, { useState, useEffect, useCallback } from "react";
import { StorageBreakdown, CleanupCategory, CleanupResult } from "../../types/storage";

function formatBytes(bytes: number): string {
  if (bytes === 0) return "0 B";
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

interface StorageManagementPanelProps {
  onClose?: () => void;
  onStorageUpdated?: () => void;
}

export function StorageManagementPanel({ onClose, onStorageUpdated }: StorageManagementPanelProps) {
  const [breakdown, setBreakdown] = useState<StorageBreakdown | null>(null);
  const [loading, setLoading] = useState(true);
  const [cleaningCategory, setCleaningCategory] = useState<CleanupCategory | null>(null);
  const [confirmClearAll, setConfirmClearAll] = useState(false);
  const [cleanupResult, setCleanupResult] = useState<CleanupResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const fetchBreakdown = useCallback(async () => {
    try {
      const res = await fetch("http://localhost:3001/api/storage/breakdown");
      if (!res.ok) throw new Error("Failed to fetch storage breakdown");
      const data = await res.json();
      setBreakdown(data);
      setError(null);
    } catch (e: any) {
      setError(e.message || "Could not load storage data");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchBreakdown();
  }, [fetchBreakdown]);

  const handleClean = async (category: CleanupCategory) => {
    setCleaningCategory(category);
    setError(null);
    try {
      const res = await fetch("http://localhost:3001/api/storage/clean", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ category }),
      });
      if (!res.ok) throw new Error("Cleanup failed");
      const result: CleanupResult = await res.json();
      setBreakdown(result.breakdown);
      setCleanupResult(result);
      if (onStorageUpdated) onStorageUpdated();
    } catch (e: any) {
      setError(e.message || "Failed to execute storage cleanup");
    } finally {
      setCleaningCategory(null);
      setConfirmClearAll(false);
    }
  };

  if (loading) {
    return (
      <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm animate-pulse space-y-4">
        <div className="h-5 bg-gray-100 rounded w-1/4" />
        <div className="h-4 bg-gray-100 rounded w-full" />
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <div className="h-32 bg-gray-100 rounded-xl" />
          <div className="h-32 bg-gray-100 rounded-xl" />
          <div className="h-32 bg-gray-100 rounded-xl" />
        </div>
      </div>
    );
  }

  const total = breakdown?.totalBytes || 1;
  const videoPercent = Math.min(100, Math.round(((breakdown?.uploadedVideosBytes || 0) / total) * 100));
  const clipsPercent = Math.min(100, Math.round(((breakdown?.generatedClipsBytes || 0) / total) * 100));
  const tempPercent = Math.min(100, Math.round(((breakdown?.tempFilesBytes || 0) / total) * 100));

  return (
    <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm mb-8 space-y-6 animate-fade-in">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 border-b border-gray-100 pb-5">
        <div>
          <div className="flex items-center gap-2">
            <div className="w-8 h-8 rounded-lg bg-gray-100 flex items-center justify-center">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#374151" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <ellipse cx="12" cy="5" rx="9" ry="3" />
                <path d="M21 12c0 1.66-4 3-9 3s-9-1.34-9-3" />
                <path d="M3 5v14c0 1.66 4 3 9 3s9-1.34 9-3V5" />
              </svg>
            </div>
            <h2 className="font-[Geist] text-lg font-semibold text-gray-950">Storage Management</h2>
          </div>
          <p className="text-xs text-gray-400 mt-1">
            Monitor and clean up storage safely. Active projects are automatically protected.
          </p>
        </div>

        {/* Total stats pill & Clear Everything CTA */}
        <div className="flex items-center gap-3">
          <div className="text-right">
            <span className="text-[11px] font-medium text-gray-400 uppercase tracking-wider block">Total Used</span>
            <span className="text-base font-semibold text-gray-950 font-mono">
              {formatBytes(breakdown?.totalBytes || 0)}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setConfirmClearAll(true)}
            disabled={cleaningCategory !== null || (breakdown?.totalBytes || 0) === 0}
            className="bg-red-50 border border-red-200 text-red-600 hover:bg-red-100 text-xs font-semibold px-3.5 py-2 rounded-xl transition-colors disabled:opacity-40 flex items-center gap-1.5"
          >
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <polyline points="3 6 5 6 21 6" />
              <path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6" />
            </svg>
            Clear Everything
          </button>

          {onClose && (
            <button
              type="button"
              onClick={onClose}
              className="p-2 rounded-xl text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors ml-1"
              title="Close Storage Management"
              aria-label="Close Storage Management"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <line x1="18" y1="6" x2="6" y2="18" />
                <line x1="6" y1="6" x2="18" y2="18" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Error banner */}
      {error && (
        <div className="p-3.5 rounded-xl border border-red-200 bg-red-50 text-xs text-red-700 flex items-center gap-2">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
            <circle cx="12" cy="12" r="10" />
            <line x1="12" y1="8" x2="12" y2="12" />
            <line x1="12" y1="16" x2="12.01" y2="16" />
          </svg>
          {error}
        </div>
      )}

      {/* Storage Visual Segmented Bar */}
      <div className="space-y-2">
        <div className="h-3 w-full bg-gray-100 rounded-full overflow-hidden flex shadow-inner">
          <div style={{ width: `${videoPercent}%` }} className="bg-blue-500 transition-all duration-500" title={`Uploaded Videos: ${videoPercent}%`} />
          <div style={{ width: `${clipsPercent}%` }} className="bg-emerald-500 transition-all duration-500" title={`Generated Clips: ${clipsPercent}%`} />
          <div style={{ width: `${tempPercent}%` }} className="bg-amber-500 transition-all duration-500" title={`Temp Files: ${tempPercent}%`} />
        </div>

        <div className="flex items-center justify-between text-xs text-gray-500">
          <div className="flex items-center gap-4">
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-blue-500 inline-block" />
              Uploaded Videos ({videoPercent}%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 inline-block" />
              Generated Clips ({clipsPercent}%)
            </span>
            <span className="flex items-center gap-1.5">
              <span className="w-2.5 h-2.5 rounded-full bg-amber-500 inline-block" />
              Temporary Files ({tempPercent}%)
            </span>
          </div>
        </div>
      </div>

      {/* 3 Storage Category Cards */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        {/* Category 1: Temporary Files */}
        <div className="border border-gray-200 rounded-xl p-4 bg-gray-50/50 flex flex-col justify-between space-y-4 hover:border-gray-300 transition-colors">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-amber-700 bg-amber-50 border border-amber-200 px-2 py-0.5 rounded-md">
                Cache & Temp
              </span>
              <span className="text-xs font-mono font-semibold text-gray-950">
                {formatBytes(breakdown?.tempFilesBytes || 0)}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-gray-950 mt-2">Temporary Files</h3>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              Intermediate frames, extracted audio, logs, and pipeline cache. Safe to delete anytime.
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleClean("temp")}
            disabled={cleaningCategory !== null || (breakdown?.tempFilesBytes || 0) === 0}
            className="w-full text-xs font-semibold text-gray-700 bg-white border border-gray-200 hover:bg-gray-100 rounded-lg py-2 transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {cleaningCategory === "temp" ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-gray-400 border-t-gray-800 rounded-full animate-spin" />
                Cleaning Temp…
              </>
            ) : (
              "Clean Temp Files"
            )}
          </button>
        </div>

        {/* Category 2: Generated Clips */}
        <div className="border border-gray-200 rounded-xl p-4 bg-gray-50/50 flex flex-col justify-between space-y-4 hover:border-gray-300 transition-colors">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-emerald-700 bg-emerald-50 border border-emerald-200 px-2 py-0.5 rounded-md">
                Outputs
              </span>
              <span className="text-xs font-mono font-semibold text-gray-950">
                {formatBytes(breakdown?.generatedClipsBytes || 0)}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-gray-950 mt-2">Generated Clips</h3>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              Rendered 9:16 shorts, thumbnails, and ZIP exports. Original source videos and metadata remain intact.
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleClean("clips")}
            disabled={cleaningCategory !== null || (breakdown?.generatedClipsBytes || 0) === 0}
            className="w-full text-xs font-semibold text-gray-700 bg-white border border-gray-200 hover:bg-gray-100 rounded-lg py-2 transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {cleaningCategory === "clips" ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-gray-400 border-t-gray-800 rounded-full animate-spin" />
                Cleaning Clips…
              </>
            ) : (
              "Clean Clips"
            )}
          </button>
        </div>

        {/* Category 3: Uploaded Source Videos */}
        <div className="border border-gray-200 rounded-xl p-4 bg-gray-50/50 flex flex-col justify-between space-y-4 hover:border-gray-300 transition-colors">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-xs font-semibold text-blue-700 bg-blue-50 border border-blue-200 px-2 py-0.5 rounded-md">
                Sources
              </span>
              <span className="text-xs font-mono font-semibold text-gray-950">
                {formatBytes(breakdown?.uploadedVideosBytes || 0)}
              </span>
            </div>
            <h3 className="text-sm font-semibold text-gray-950 mt-2">Uploaded Videos</h3>
            <p className="text-xs text-gray-400 mt-1 leading-relaxed">
              Original video source files. Generated clips remain accessible. Re-upload video later if regenerating.
            </p>
          </div>
          <button
            type="button"
            onClick={() => handleClean("uploads")}
            disabled={cleaningCategory !== null || (breakdown?.uploadedVideosBytes || 0) === 0}
            className="w-full text-xs font-semibold text-gray-700 bg-white border border-gray-200 hover:bg-gray-100 rounded-lg py-2 transition-colors disabled:opacity-40 flex items-center justify-center gap-2"
          >
            {cleaningCategory === "uploads" ? (
              <>
                <span className="w-3.5 h-3.5 border-2 border-gray-400 border-t-gray-800 rounded-full animate-spin" />
                Cleaning Videos…
              </>
            ) : (
              "Clean Source Videos"
            )}
          </button>
        </div>
      </div>

      {/* Safety Notice */}
      <div className="p-3 bg-blue-50/60 border border-blue-200/80 rounded-xl flex items-center gap-2.5 text-xs text-blue-800">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" className="flex-shrink-0">
          <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/>
        </svg>
        <span>
          <strong>Active Safety Guarantee:</strong> Projects actively uploading, processing, or rendering are automatically protected and skipped from cleanup operations.
        </span>
      </div>

      {/* Clear Everything Confirmation Modal */}
      {confirmClearAll && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-200 p-6 space-y-5 animate-scale-in">
            <div className="flex items-start gap-3">
              <div className="w-10 h-10 rounded-full bg-red-100 flex items-center justify-center flex-shrink-0 mt-0.5">
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="#dc2626" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  <line x1="12" y1="9" x2="12" y2="13" />
                  <line x1="12" y1="17" x2="12.01" y2="17" />
                </svg>
              </div>
              <div>
                <h3 className="text-base font-semibold text-gray-950">Clear Everything?</h3>
                <p className="text-xs text-gray-500 mt-1 leading-relaxed">
                  This will delete uploaded source videos, generated clips, and temporary cache for all <strong>completed and failed projects</strong>.
                </p>
                <p className="text-xs font-semibold text-gray-800 mt-2">
                  Active projects will be automatically skipped and will continue running safely.
                </p>
              </div>
            </div>
            <div className="flex gap-2.5">
              <button
                type="button"
                onClick={() => setConfirmClearAll(false)}
                disabled={cleaningCategory !== null}
                className="flex-1 text-sm font-medium text-gray-700 bg-gray-100 hover:bg-gray-200 rounded-xl py-2.5 transition-colors disabled:opacity-50"
              >
                Cancel
              </button>
              <button
                type="button"
                onClick={() => handleClean("everything")}
                disabled={cleaningCategory !== null}
                className="flex-1 text-sm font-semibold text-white bg-red-600 hover:bg-red-700 rounded-xl py-2.5 transition-colors disabled:opacity-50 flex items-center justify-center gap-2"
              >
                {cleaningCategory === "everything" ? (
                  <>
                    <span className="w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                    Cleaning All…
                  </>
                ) : (
                  "Clear Everything"
                )}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Cleanup Summary Modal */}
      {cleanupResult && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm animate-fade-in">
          <div className="w-full max-w-md bg-white rounded-2xl shadow-2xl border border-gray-200 p-6 space-y-5 animate-scale-in">
            <div className="flex items-start justify-between">
              <div className="flex items-center gap-3">
                <div className="w-10 h-10 rounded-full bg-emerald-100 flex items-center justify-center flex-shrink-0">
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#059669" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                    <path d="M20 6L9 17l-5-5" />
                  </svg>
                </div>
                <div>
                  <h3 className="text-base font-semibold text-gray-950">Storage Cleanup Summary</h3>
                  <p className="text-xs text-gray-500 mt-0.5">
                    Freed <strong className="text-emerald-600 font-mono">{formatBytes(cleanupResult.freedBytes)}</strong> of disk space.
                  </p>
                </div>
              </div>
            </div>

            {/* List breakdown */}
            <div className="space-y-4 max-h-64 overflow-y-auto pr-1">
              {/* Deleted items */}
              {cleanupResult.deleted.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <span className="text-emerald-600">✔</span> Deleted Projects ({cleanupResult.deleted.length})
                  </h4>
                  <ul className="space-y-1 bg-emerald-50/50 rounded-xl p-2.5 border border-emerald-100 text-xs">
                    {cleanupResult.deleted.map((p) => (
                      <li key={p.jobId} className="flex items-center justify-between text-gray-800">
                        <span className="font-medium truncate max-w-[240px]">✔ {p.name}</span>
                        <span className="text-[11px] text-gray-400 capitalize">{p.status}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Skipped active items */}
              {cleanupResult.skipped.length > 0 && (
                <div>
                  <h4 className="text-xs font-semibold text-gray-700 uppercase tracking-wider mb-2 flex items-center gap-1">
                    <span className="text-amber-500">⏳</span> Skipped Active Projects ({cleanupResult.skipped.length})
                  </h4>
                  <ul className="space-y-1 bg-amber-50/50 rounded-xl p-2.5 border border-amber-100 text-xs">
                    {cleanupResult.skipped.map((p) => (
                      <li key={p.jobId} className="flex items-center justify-between text-gray-800">
                        <span className="font-medium truncate max-w-[240px]">⏳ {p.name}</span>
                        <span className="text-[11px] font-semibold text-amber-700 bg-amber-100 px-1.5 py-0.5 rounded capitalize">
                          {p.status}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {cleanupResult.deleted.length === 0 && cleanupResult.skipped.length === 0 && (
                <p className="text-xs text-gray-400 text-center py-3">No eligible project files needed cleanup.</p>
              )}
            </div>

            <div className="p-3 bg-gray-50 rounded-xl text-center text-xs text-gray-500">
              Only completed, failed, and cancelled projects were cleaned.
            </div>

            <button
              type="button"
              onClick={() => setCleanupResult(null)}
              className="w-full bg-gray-950 text-white text-xs font-semibold rounded-xl py-2.5 hover:bg-gray-800 transition-colors"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
