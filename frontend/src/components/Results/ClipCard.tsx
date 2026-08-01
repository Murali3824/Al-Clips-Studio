import React from "react";

interface ClipCardProps {
  clip: any;
  index: number;
  isSelected: boolean;
  isExportSelected: boolean;
  renderingInfo?: { stage: string; progress: number } | null;
  onSelect: () => void;
  onToggleExport: () => void;
}

export const ClipCard: React.FC<ClipCardProps> = ({
  clip,
  index,
  isSelected,
  isExportSelected,
  renderingInfo,
  onSelect,
  onToggleExport,
}) => {
  const score = Math.round(clip.score ?? 90);

  const getScoreBadgeClass = (s: number) => {
    if (s >= 85) return "bg-emerald-50 text-emerald-700 border-emerald-200";
    if (s >= 70) return "bg-amber-50 text-amber-700 border-amber-200";
    return "bg-blue-50 text-blue-700 border-blue-200";
  };

  return (
    <div
      onClick={onSelect}
      className={`group relative flex items-start gap-3.5 p-3.5 rounded-2xl border transition-all cursor-pointer select-none ${
        isSelected
          ? "border-gray-950 bg-white ring-2 ring-gray-950/10 shadow-md"
          : "border-gray-200 bg-white hover:border-gray-300 hover:bg-gray-50/80 shadow-sm"
      }`}
    >
      {/* 1. Thumbnail Container (9:16 Vertical Ratio) */}
      <div className="relative w-24 aspect-[9/16] rounded-xl bg-gray-950 overflow-hidden flex-shrink-0 border border-gray-100 shadow-sm">
        {clip.thumbnailUrl ? (
          <img
            alt={`Clip ${index + 1}`}
            className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
            src={`http://localhost:3001${clip.thumbnailUrl}`}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-gray-500 bg-gray-900">
            <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M14.752 11.168l-3.197-2.132A1 1 0 0010 9.87v4.263a1 1 0 001.555.832l3.197-2.132a1 1 0 000-1.664z" />
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
        )}

        {/* 2. Clip Number Badge (#1, #2, #3) */}
        <div className="absolute top-2 left-2 z-10">
          <span className="bg-black/75 text-white font-mono text-[11px] font-bold px-2 py-0.5 rounded-md backdrop-blur-md border border-white/20 shadow-sm">
            #{index + 1}
          </span>
        </div>

        {/* Export Checkbox Overlay */}
        <div
          className={`absolute bottom-2 left-2 z-10 transition-opacity ${
            isExportSelected ? "opacity-100" : "opacity-0 group-hover:opacity-100"
          }`}
          onClick={(e) => {
            e.stopPropagation();
            onToggleExport();
          }}
        >
          <div className="bg-black/75 hover:bg-black p-1 rounded-md border border-white/20 shadow-sm cursor-pointer flex items-center justify-center">
            <input
              type="checkbox"
              checked={isExportSelected}
              onChange={() => {}}
              className="h-3.5 w-3.5 rounded border-gray-300 text-gray-950 focus:ring-0 cursor-pointer pointer-events-none"
            />
          </div>
        </div>

        {/* Rendering Overlay */}
        {renderingInfo && (
          <div className="absolute inset-0 bg-black/75 backdrop-blur-[2px] z-20 flex flex-col items-center justify-center p-2 text-center animate-fade-in">
            <div className="w-5 h-5 rounded-full border-2 border-white/30 border-t-white animate-spin mb-1.5" />
            <span className="text-[10px] font-semibold text-white truncate max-w-full px-1">
              {renderingInfo.stage || "Rendering..."}
            </span>
          </div>
        )}
      </div>

      {/* Card Content Column */}
      <div className="flex-1 min-w-0 py-0.5 flex flex-col justify-between space-y-2.5">
        {/* 3. Title */}
        <div>
          <h3 className={`text-sm font-semibold leading-snug font-[Geist] line-clamp-2 ${
            isSelected ? "text-gray-950" : "text-gray-800"
          }`}>
            {clip.title || `Clip ${index + 1}`}
          </h3>
        </div>

        {/* 4. Viral Score Badge (e.g. Viral Score 95 / 100) */}
        <div>
          <div className={`inline-flex items-center gap-1.5 text-[11px] font-semibold px-2.5 py-1 rounded-lg border shadow-2xs ${getScoreBadgeClass(score)}`}>
            <span>🔥 Viral Score</span>
            <span className="font-bold">{score} / 100</span>
          </div>
        </div>

        {/* 5. Duration & Selection Indicator */}
        <div className="flex items-center justify-between text-xs text-gray-400 font-medium pt-0.5">
          <span className="flex items-center gap-1">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
            </svg>
            {clip.duration ? clip.duration.toFixed(1) : 0}s
          </span>

          {isSelected && (
            <span className="text-[11px] font-semibold text-gray-950 flex items-center gap-1">
              Active
            </span>
          )}
        </div>
      </div>
    </div>
  );
};
