import React, { useEffect, useRef, useState } from "react";

interface LogsPanelProps {
  logs: string[];
}

const MILESTONE_PATTERNS: Array<{ pattern: RegExp; text: string }> = [
  { pattern: /stage_01_audio|extracting audio/i, text: "✓ Extracting audio..." },
  { pattern: /stage_02_vad|voice activity/i, text: "✓ Detecting speech..." },
  { pattern: /stage_03_transcription|transcribing/i, text: "✓ Understanding conversation..." },
  { pattern: /stage_03_speaker_diarization|diarization/i, text: "✓ Identifying speakers..." },
  { pattern: /stage_04_highlights|highlight/i, text: "✓ Finding viral moments..." },
  { pattern: /candidate|quality highlight/i, text: "✓ Selecting production-quality highlights..." },
  { pattern: /stage_05_scene_detection|scene/i, text: "✓ Detecting scenes..." },
  { pattern: /stage_06_face_detection|stage_07_face_tracking|tracking face/i, text: "✓ Tracking faces..." },
  { pattern: /stage_08|smooth_crop|cinematic framing|camera/i, text: "✓ Creating cinematic framing..." },
  { pattern: /stage_09_cut_crop|rendering clip/i, text: "✓ Rendering clips..." },
  { pattern: /stage_10_captions|captions/i, text: "✓ Burning captions..." },
  { pattern: /stage_11_metadata|metadata/i, text: "✓ Generating metadata..." },
  { pattern: /stage_12_export|export/i, text: "✓ Preparing export..." },
  { pattern: /complete|finished|done/i, text: "✓ Completed successfully." }
];

function isTechnicalLog(line: string): boolean {
  return /ffmpeg|filter_complex|yolov8|pts_time|candidate_id|autohook|crop=|scale=|win32|python\.exe|libx264|yuv420p/i.test(line);
}

export const LogsPanel: React.FC<LogsPanelProps> = ({ logs }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const [logMode, setLogMode] = useState<"user" | "developer">("user");

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs, logMode]);

  // Filter logs for user mode
  const getUserMilestones = (): string[] => {
    const milestones: string[] = ["✓ Preparing project..."];
    for (const line of logs) {
      if (isTechnicalLog(line)) continue;
      for (const m of MILESTONE_PATTERNS) {
        if (m.pattern.test(line) && !milestones.includes(m.text)) {
          milestones.push(m.text);
        }
      }
    }
    return milestones;
  };

  const userLogs = getUserMilestones();
  const displayLogs = logMode === "user" ? userLogs : logs;

  return (
    <div className="mt-4 bg-gray-950 text-gray-100 font-mono text-xs rounded-xl border border-gray-800 overflow-hidden flex flex-col h-60 animate-fade-in shadow-lg">
      {/* Fixed Sticky Header & Toggle */}
      <div className="flex items-center justify-between px-4 py-3 bg-gray-950 border-b border-gray-800 flex-shrink-0 z-10 select-none">
        <span className="text-xs uppercase tracking-wide font-semibold text-gray-300 font-sans">
          {logMode === "user" ? "Processing Summary" : "Raw Console Output"}
        </span>
        <div className="flex items-center gap-1 bg-gray-900 p-0.5 rounded-lg border border-gray-800">
          <button
            type="button"
            onClick={() => setLogMode("user")}
            className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all ${
              logMode === "user" ? "bg-gray-800 text-white shadow-sm" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            User Mode
          </button>
          <button
            type="button"
            onClick={() => setLogMode("developer")}
            className={`px-2.5 py-1 rounded-md text-[11px] font-semibold transition-all ${
              logMode === "developer" ? "bg-gray-800 text-white shadow-sm" : "text-gray-400 hover:text-gray-200"
            }`}
          >
            Developer Mode
          </button>
        </div>
      </div>

      {/* Scrollable Console Body */}
      <div ref={containerRef} className="flex-1 overflow-y-auto p-4 flex flex-col gap-1.5">
        {displayLogs.length > 0 ? (
          displayLogs.map((line, index) => (
            <p
              key={`${line}-${index}`}
              className={`leading-relaxed break-all ${
                logMode === "user"
                  ? "text-emerald-400 font-sans font-medium text-xs flex items-center gap-2"
                  : "text-green-400 opacity-80 text-[11px]"
              }`}
            >
              {line}
            </p>
          ))
        ) : (
          <p className="leading-relaxed opacity-80 italic text-gray-500">Waiting for processing updates...</p>
        )}
      </div>
    </div>
  );
};
