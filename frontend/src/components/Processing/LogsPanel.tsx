import React, { useEffect, useRef } from "react";

interface LogsPanelProps {
  logs: string[];
}

export const LogsPanel: React.FC<LogsPanelProps> = ({ logs }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (containerRef.current) {
      containerRef.current.scrollTop = containerRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div
      ref={containerRef}
      className="mt-4 bg-gray-950 text-green-400 font-mono text-xs rounded-xl p-4 max-h-48 overflow-y-auto animate-fade-in"
    >
      <div className="text-xs text-gray-500 font-medium mb-2 uppercase tracking-wide sticky top-0 bg-gray-950 pb-1">
        Console
      </div>
      <div className="flex flex-col gap-1">
        {logs.length > 0 ? (
          logs.map((line, index) => (
            <p key={`${line}-${index}`} className="leading-relaxed opacity-80 break-all">
              {line}
            </p>
          ))
        ) : (
          <p className="leading-relaxed opacity-80 italic text-gray-600">Waiting for logs...</p>
        )}
      </div>
    </div>
  );
};
