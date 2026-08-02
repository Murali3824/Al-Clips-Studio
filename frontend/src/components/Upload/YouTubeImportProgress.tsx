import React from "react";

export interface ImportProgressData {
  stage: "CONNECTING" | "FETCHING_METADATA" | "DOWNLOADING_THUMBNAIL" | "DOWNLOADING" | "PROCESSING" | "READY" | "FAILED";
  stageText: string;
  progress: number;
  title?: string;
  thumbnailUrl?: string | null;
  duration?: number;
  totalSizeStr?: string;
  speedStr?: string;
  etaStr?: string;
  error?: string;
}

interface YouTubeImportProgressProps {
  progressData: ImportProgressData;
  onRetry?: () => void;
  onEditUrl?: () => void;
  isReplacing?: boolean;
}

export const YouTubeImportProgress: React.FC<YouTubeImportProgressProps> = ({
  progressData,
  onRetry,
  onEditUrl,
  isReplacing = false,
}) => {
  const { stage, stageText, progress, title, thumbnailUrl, totalSizeStr, speedStr, etaStr, error } = progressData;

  const isFailed = stage === "FAILED";
  const isComplete = stage === "READY" || progress >= 100;

  return (
    <div className={`relative rounded-2xl border border-gray-200 bg-white overflow-hidden shadow-sm animate-scale-in ${isReplacing ? "p-0" : "p-6"}`}>
      {/* Container header */}
      <div className="flex items-center justify-between border-b border-gray-100 pb-4 mb-5">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-xl bg-red-50 border border-red-100 flex items-center justify-center text-red-600">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22.54 6.42a2.78 2.78 0 00-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 00-1.94 2A29 29 0 001 11.75a29 29 0 00.46 5.33A2.78 2.78 0 003.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 001.94-2 29 29 0 00.46-5.25 29 29 0 00-.46-5.33z" />
              <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02" />
            </svg>
          </div>
          <div>
            <h3 className="text-base font-semibold text-gray-950 font-[Geist]">
              {isReplacing ? "Replacing Video..." : "Importing YouTube Video"}
            </h3>
            <p className="text-xs text-gray-400 font-medium">{stageText || "Connecting to YouTube..."}</p>
          </div>
        </div>

        {isComplete && (
          <span className="bg-green-50 text-green-700 text-xs px-3 py-1 rounded-full border border-green-200 font-semibold flex items-center gap-1.5 shadow-sm animate-fade-in">
            ✓ Ready
          </span>
        )}
      </div>

      {/* Main card body */}
      {isFailed ? (
        <div className="space-y-4 py-4 text-center animate-fade-in">
          <div className="w-12 h-12 rounded-2xl bg-red-50 border border-red-200 text-red-600 mx-auto flex items-center justify-center">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5">
              <circle cx="12" cy="12" r="10" />
              <line x1="15" y1="9" x2="9" y2="15" />
              <line x1="9" y1="9" x2="15" y2="15" />
            </svg>
          </div>
          <div>
            <h4 className="text-sm font-semibold text-gray-950">Import Failed</h4>
            <p className="text-xs text-red-600 mt-1 max-w-md mx-auto leading-relaxed">{error || "Unable to download this video. Please check the URL or try again."}</p>
          </div>
          <div className="flex items-center justify-center gap-3 pt-2">
            {onRetry && (
              <button
                type="button"
                onClick={onRetry}
                className="bg-gray-950 text-white text-xs font-semibold px-4 py-2 rounded-xl hover:bg-gray-800 transition-colors shadow-sm"
              >
                Try Again
              </button>
            )}
            {onEditUrl && (
              <button
                type="button"
                onClick={onEditUrl}
                className="bg-white border border-gray-200 text-gray-700 text-xs font-semibold px-4 py-2 rounded-xl hover:bg-gray-50 transition-colors"
              >
                Edit URL
              </button>
            )}
          </div>
        </div>
      ) : (
        <div className="space-y-5">
          {/* Progressive Metadata & Thumbnail Preview Card */}
          <div className="rounded-xl border border-gray-200 bg-gray-50 overflow-hidden relative min-h-[140px] flex flex-col sm:flex-row items-center gap-4 p-4 transition-all">
            {/* Thumbnail Box */}
            <div className="w-full sm:w-48 aspect-video rounded-lg bg-gray-200 overflow-hidden relative flex-shrink-0 flex items-center justify-center">
              {thumbnailUrl ? (
                <img
                  src={thumbnailUrl}
                  alt="Video thumbnail"
                  className="w-full h-full object-cover animate-fade-in"
                />
              ) : (
                <div className="w-full h-full flex flex-col items-center justify-center bg-gray-900 text-gray-400 animate-pulse">
                  <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                    <rect x="3" y="3" width="18" height="18" rx="2" ry="2" />
                    <circle cx="8.5" cy="8.5" r="1.5" />
                    <polyline points="21 15 16 10 5 21" />
                  </svg>
                  <span className="text-[10px] mt-1.5 font-medium">Loading thumbnail...</span>
                </div>
              )}
            </div>

            {/* Video Info Skeleton / Metadata */}
            <div className="flex-1 min-w-0 space-y-2.5 w-full">
              {title ? (
                <h4 className="text-sm font-semibold text-gray-950 line-clamp-2 leading-snug animate-fade-in">
                  {title}
                </h4>
              ) : (
                <div className="space-y-1.5 animate-pulse">
                  <div className="h-4 bg-gray-200 rounded-md w-3/4" />
                  <div className="h-3 bg-gray-200 rounded-md w-1/2" />
                </div>
              )}

              {/* Dynamic Metrics Row */}
              <div className="flex flex-wrap items-center gap-2 text-[11px] text-gray-500 font-medium pt-1">
                {totalSizeStr && (
                  <span className="bg-white border border-gray-200 px-2 py-0.5 rounded-md text-gray-700">
                    📦 {totalSizeStr}
                  </span>
                )}
                {speedStr && (
                  <span className="bg-white border border-gray-200 px-2 py-0.5 rounded-md text-blue-700">
                    ⚡ {speedStr}
                  </span>
                )}
                {etaStr && (
                  <span className="bg-white border border-gray-200 px-2 py-0.5 rounded-md text-gray-600">
                    ⏱️ {etaStr} remaining
                  </span>
                )}
              </div>
            </div>
          </div>

          {/* Progress Bar & Stage Metric Row */}
          <div className="space-y-2">
            <div className="flex justify-between items-center text-xs text-gray-600 font-medium">
              <span className="flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-blue-600 animate-ping" />
                {stageText}
              </span>
              <span className="tabular-nums font-semibold text-gray-950">{progress}%</span>
            </div>
            <div className="h-2 w-full bg-gray-100 rounded-full overflow-hidden p-0.5 border border-gray-200">
              <div
                className="h-full bg-gradient-to-r from-blue-600 to-indigo-600 rounded-full transition-all duration-300 shadow-sm"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
