import React, { useRef, useState, DragEvent, ChangeEvent, FormEvent } from "react";
import { Button } from "../Common/Button";

interface UploadSectionProps {
  onFileSelected: (file: File) => void;
  onYouTubeImport?: (url: string) => void;
  /** When true, renders a compact inline variant for the "Replace Video" panel */
  compact?: boolean;
  isSubmitting?: boolean;
}

export const UploadSection: React.FC<UploadSectionProps> = ({
  onFileSelected,
  onYouTubeImport,
  compact = false,
  isSubmitting = false,
}) => {
  const [activeTab, setActiveTab] = useState<"file" | "youtube">("file");
  const [youtubeUrl, setYoutubeUrl] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const handleDragOver = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(true);
  };

  const handleDragLeave = () => {
    setIsDragging(false);
  };

  const handleDrop = (e: DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setIsDragging(false);
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      onFileSelected(e.dataTransfer.files[0]);
    }
  };

  const handleInputChange = (e: ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      onFileSelected(e.target.files[0]);
      e.target.value = "";
    }
  };

  const handleYouTubeSubmit = (e: FormEvent) => {
    e.preventDefault();
    setLocalError(null);

    const trimmed = youtubeUrl.trim();
    if (!trimmed) {
      setLocalError("Please enter a YouTube video link.");
      return;
    }

    try {
      const parsed = new URL(trimmed);
      const host = parsed.hostname.toLowerCase();
      if (
        host !== "youtube.com" &&
        host !== "www.youtube.com" &&
        host !== "m.youtube.com" &&
        host !== "youtu.be"
      ) {
        setLocalError("Please enter a valid YouTube video URL (youtube.com or youtu.be).");
        return;
      }
    } catch {
      setLocalError("Please enter a valid URL.");
      return;
    }

    if (onYouTubeImport) {
      onYouTubeImport(trimmed);
    }
  };

  // ── Compact variant — used inside the "Replace Video" section ────────────
  if (compact) {
    return (
      <div className="space-y-4">
        {/* Compact Tabs */}
        <div className="flex gap-2 p-1 bg-gray-100 rounded-lg max-w-[280px]">
          <button
            type="button"
            onClick={() => setActiveTab("file")}
            className={`flex-1 text-xs font-semibold py-1.5 rounded-md transition-all ${
              activeTab === "file"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            File Upload
          </button>
          <button
            type="button"
            onClick={() => setActiveTab("youtube")}
            className={`flex-1 text-xs font-semibold py-1.5 rounded-md transition-all ${
              activeTab === "youtube"
                ? "bg-white text-gray-900 shadow-sm"
                : "text-gray-500 hover:text-gray-900"
            }`}
          >
            YouTube URL
          </button>
        </div>

        {activeTab === "file" ? (
          <div
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            className={`flex items-center gap-4 transition-all duration-200 ${
              isDragging ? "opacity-60" : ""
            }`}
          >
            <input
              ref={inputRef}
              type="file"
              accept=".mp4,.mov,.avi,.mkv,.webm,video/*"
              onChange={handleInputChange}
              className="hidden"
            />
            <Button
              variant="secondary"
              size="md"
              onClick={() => inputRef.current?.click()}
            >
              <svg className="w-4 h-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
                <path strokeLinecap="round" strokeLinejoin="round" d="M12 12v-6m0 0l-3 3m3-3l3 3" />
              </svg>
              Choose a different file
            </Button>
            <span className="text-xs text-gray-400">or drag a new video here</span>
          </div>
        ) : (
          <form onSubmit={handleYouTubeSubmit} className="flex gap-2">
            <input
              type="text"
              placeholder="Paste YouTube video link..."
              value={youtubeUrl}
              onChange={(e) => setYoutubeUrl(e.target.value)}
              className="flex-1 bg-white border border-gray-200 rounded-lg px-3 py-1.5 text-xs text-gray-950 focus:ring-2 focus:ring-black/5 outline-none"
            />
            <Button type="submit" variant="secondary" size="sm">
              Import
            </Button>
          </form>
        )}
        {localError && <p className="text-[11px] text-red-600 animate-fade-in">{localError}</p>}
      </div>
    );
  }

  // ── Full variant — used on the first-time upload screen ─────────────────
  return (
    <div className="space-y-6">
      {/* Tabs Row */}
      <div className="flex gap-1 p-1 bg-gray-100 rounded-xl max-w-[280px] mx-auto select-none">
        <button
          type="button"
          onClick={() => {
            setActiveTab("file");
            setLocalError(null);
          }}
          className={`flex-1 text-xs font-semibold py-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
            activeTab === "file"
              ? "bg-white text-gray-950 shadow-sm"
              : "text-gray-500 hover:text-gray-900"
          }`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
          Local File
        </button>
        <button
          type="button"
          onClick={() => {
            setActiveTab("youtube");
            setLocalError(null);
          }}
          className={`flex-1 text-xs font-semibold py-2 rounded-lg transition-all flex items-center justify-center gap-1.5 ${
            activeTab === "youtube"
              ? "bg-white text-gray-950 shadow-sm"
              : "text-gray-500 hover:text-gray-900"
          }`}
        >
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
            <path d="M22.54 6.42a2.78 2.78 0 00-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 00-1.94 2A29 29 0 001 11.75a29 29 0 00.46 5.33A2.78 2.78 0 003.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 001.94-2 29 29 0 00.46-5.25 29 29 0 00-.46-5.33z" />
            <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02" />
          </svg>
          YouTube URL
        </button>
      </div>

      {activeTab === "file" ? (
        <div
          onDragOver={handleDragOver}
          onDragLeave={handleDragLeave}
          onDrop={handleDrop}
          onClick={() => inputRef.current?.click()}
          className={`relative cursor-pointer flex flex-col items-center justify-center min-h-[300px] rounded-2xl transition-all duration-200 ${
            isDragging
              ? "border-2 border-dashed border-blue-400 bg-blue-50"
              : "border-2 border-dashed border-gray-200 bg-white hover:border-gray-400 hover:bg-gray-50"
          }`}
        >
          <input
            ref={inputRef}
            type="file"
            accept=".mp4,.mov,.avi,.mkv,.webm,video/*"
            onChange={handleInputChange}
            className="hidden"
          />

          <svg className="w-12 h-12 text-gray-300 stroke-current" fill="none" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3 15a4 4 0 004 4h9a5 5 0 10-.1-9.999 5.002 5.002 0 10-9.78 2.096A4.001 4.001 0 003 15z" />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 12v-6m0 0l-3 3m3-3l3 3" />
          </svg>

          <h2 className="text-xl font-semibold text-gray-950 font-[Geist] mt-6">Drop your video here</h2>
          <p className="text-xs text-gray-400 mt-1">or click to browse</p>

          <div className="mt-6" onClick={(e) => e.stopPropagation()}>
            <Button
              variant="secondary"
              size="md"
              onClick={() => inputRef.current?.click()}
            >
              Choose File
            </Button>
          </div>

          <p className="text-[10px] text-gray-300 mt-4">MP4 · MOV · MKV · AVI — up to 2 GB</p>
        </div>
      ) : (
        <form
          onSubmit={handleYouTubeSubmit}
          className="border border-gray-200 bg-white rounded-2xl p-6 min-h-[300px] flex flex-col items-center justify-center space-y-6 animate-fade-in"
        >
          <div className="w-12 h-12 rounded-2xl bg-red-50 border border-red-100 flex items-center justify-center text-red-500">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M22.54 6.42a2.78 2.78 0 00-1.94-2C18.88 4 12 4 12 4s-6.88 0-8.6.46a2.78 2.78 0 00-1.94 2A29 29 0 001 11.75a29 29 0 00.46 5.33A2.78 2.78 0 003.4 19c1.72.46 8.6.46 8.6.46s6.88 0 8.6-.46a2.78 2.78 0 001.94-2 29 29 0 00.46-5.25 29 29 0 00-.46-5.33z" />
              <polygon points="9.75 15.02 15.5 11.75 9.75 8.48 9.75 15.02" />
            </svg>
          </div>

          <div className="text-center space-y-2 max-w-sm">
            <h2 className="text-xl font-semibold text-gray-950 font-[Geist]">Import from YouTube</h2>
            <p className="text-xs text-gray-400">
              Paste a link to any public YouTube video to download and generate short clips automatically.
            </p>
          </div>

          <div className="w-full max-w-md space-y-3">
            <div className="relative">
              <input
                type="text"
                placeholder="https://www.youtube.com/watch?v=..."
                value={youtubeUrl}
                disabled={isSubmitting}
                onChange={(e) => setYoutubeUrl(e.target.value)}
                className="w-full bg-white border border-gray-200 rounded-xl px-4 py-3 text-sm text-gray-950 focus:ring-2 focus:ring-black/5 outline-none placeholder:text-gray-300 disabled:opacity-60 disabled:cursor-not-allowed"
              />
            </div>
            <Button type="submit" variant="primary" size="md" className="w-full" loading={isSubmitting} disabled={isSubmitting}>
              {isSubmitting ? "Connecting to YouTube..." : "Import Video"}
            </Button>
          </div>

          {localError && (
            <p className="text-xs font-medium text-red-600 text-center animate-fade-in">{localError}</p>
          )}
        </form>
      )}
    </div>
  );
};
