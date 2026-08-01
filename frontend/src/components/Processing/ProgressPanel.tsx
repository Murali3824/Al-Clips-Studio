import React from "react";
import { Button } from "../Common/Button";

interface ProgressPanelProps {
  status: string;
  activeJobId: string | null;
  pipelinePercent: number;
  stages: Array<{ id: string; label: string; status: string; percent: number }>;
  onCancel: () => void;
  onResume?: () => void;
  logsOpen: boolean;
  setLogsOpen: (open: boolean) => void;
}

export const ProgressPanel: React.FC<ProgressPanelProps> = ({
  status,
  activeJobId,
  pipelinePercent,
  stages,
  onCancel,
  onResume,
  logsOpen,
  setLogsOpen,
}) => {
  return (
    <div className="bg-white max-w-2xl mx-auto p-8 rounded-xl border border-gray-200">
      {/* Top Section */}
      <div className="flex items-start justify-between">
        <div>
          <h2 className="text-2xl font-semibold text-gray-950 font-[Geist]">Processing your video</h2>
          <p className="text-sm text-gray-400 mt-1">This may take a few minutes depending on video length</p>
        </div>
        <div className="flex gap-2">
          {(status === "failed" || status === "interrupted" || status === "cancelled") && onResume && (
            <Button
              variant="primary"
              size="sm"
              onClick={onResume}
            >
              Resume Job
            </Button>
          )}
          {status === "running" && (
            <Button
              variant="danger"
              size="sm"
              disabled={!activeJobId}
              onClick={onCancel}
            >
              Cancel Job
            </Button>
          )}
        </div>
      </div>

      <div className="mt-6 mb-8">
        <div className="h-[3px] w-full bg-gray-100 rounded-full overflow-hidden">
          <div
            className="h-full bg-gray-950 transition-all duration-500"
            style={{ width: `${pipelinePercent}%` }}
          />
        </div>
        <div className="mt-3 text-right">
          <span className="text-xs text-gray-500">{pipelinePercent}%</span>
        </div>
      </div>

      {/* Timeline */}
      <div className="relative pl-3">
        {stages.map((stage, index) => {
          const isComplete = stage.status === "complete";
          const isRunning = stage.status === "running";
          const isError = stage.status === "error";
          const isPending = stage.status === "pending" || stage.status === "skipped" || (!isComplete && !isRunning && !isError);
          const isLast = index === stages.length - 1;

          return (
            <div key={stage.id} className="relative mb-5 last:mb-0 flex items-start">
              {/* Connecting Line */}
              {!isLast && (
                <div
                  className={`absolute left-3 top-6 w-[1px] -ml-[0.5px] ${
                    isComplete ? "bg-green-500" : "bg-gray-200"
                  }`}
                  style={{ height: 'calc(100% + 20px)' }}
                />
              )}

              {/* Circle Indicator */}
              <div className="relative z-10 flex-shrink-0 mt-0.5">
                {isComplete ? (
                  <div className="w-6 h-6 rounded-full border-2 border-green-500 bg-green-500 flex items-center justify-center">
                    <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                    </svg>
                  </div>
                ) : isRunning ? (
                  <div className="w-6 h-6 rounded-full border-2 border-blue-500 bg-blue-500 flex items-center justify-center ring-4 ring-blue-500/20">
                    <span className="block w-1.5 h-1.5 bg-white rounded-full animate-pulse" />
                  </div>
                ) : isError ? (
                  <div className="w-6 h-6 rounded-full border-2 border-red-500 bg-red-500 flex items-center justify-center">
                    <svg className="w-3.5 h-3.5 text-white" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </div>
                ) : (
                  <div className="w-6 h-6 rounded-full border-2 border-gray-200 bg-white" />
                )}
              </div>

              {/* Stage Content */}
              <div className="ml-4 flex-1">
                <h4 className={`text-sm font-semibold ${isError ? "text-red-600" : isPending ? "text-gray-400" : "text-gray-950"}`}>
                  {stage.label} {isError && "(Failed)"}
                </h4>
                <div className="mt-0.5">
                  {isRunning && <p className="text-xs font-medium text-blue-600">In progress...</p>}
                  {isComplete && <p className="text-xs font-medium text-green-600">Done</p>}
                  {isPending && <p className="text-xs text-gray-400">Waiting</p>}
                  {isError && <p className="text-xs font-semibold text-red-600">Failed</p>}
                </div>
                
                {isError && (
                  <div className="mt-3.5 rounded-xl border border-red-200 bg-red-50/80 p-3.5 text-xs text-red-800 font-mono shadow-sm">
                    <div className="font-semibold text-red-900 mb-1.5 flex items-center gap-1.5">
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                        <circle cx="12" cy="12" r="10"/>
                        <line x1="12" y1="8" x2="12" y2="12"/>
                        <line x1="12" y1="16" x2="12.01" y2="16"/>
                      </svg>
                      Error:
                    </div>
                    <div className="whitespace-pre-wrap break-words text-[11px] leading-relaxed text-red-700">
                      {(stage as any).error || "Stage execution encountered an unexpected error."}
                    </div>
                  </div>
                )}

                {isRunning && (
                  <div className="mt-2 h-[2px] w-full max-w-md bg-blue-50 rounded-full overflow-hidden">
                    <div
                      className="h-full bg-blue-500 transition-all duration-300"
                      style={{ width: `${stage.percent}%` }}
                    />
                  </div>
                )}
              </div>
            </div>
          );
        })}
      </div>

      <div className="mt-8 pt-6 border-t border-gray-100 flex justify-center">
        <button
          onClick={() => setLogsOpen(!logsOpen)}
          className="text-gray-600 hover:text-gray-950 hover:bg-gray-100 px-4 py-2 text-sm font-medium rounded-lg transition-colors"
        >
          {logsOpen ? "Hide console" : "View console"}
        </button>
      </div>
    </div>
  );
};
