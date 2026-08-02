import React from "react";

interface UploadPreviewProps {
  previewUrl: string | null;
  file: { name: string; size: number } | File | null;
  progress: number;
  jobId?: string | null;
  job?: any;
  error?: string | null;
  isDownloadingYoutube?: boolean;
}

function formatFileSize(bytes: number): string {
  if (!bytes || bytes <= 0) return "File size detected after download";
  const mb = bytes / (1024 * 1024);
  if (mb >= 1024) {
    return `${(mb / 1024).toFixed(2)} GB`;
  }
  return `${mb.toFixed(1)} MB`;
}

export const UploadPreview: React.FC<UploadPreviewProps> = ({
  previewUrl,
  file,
  progress,
  jobId,
  job,
  error,
  isDownloadingYoutube = false,
}) => {
  if (!file && !jobId && !isDownloadingYoutube) return null;

  const fileName = file?.name ?? "Source Video";
  const rawSize = (file as any)?.size || (job as any)?.size || (job as any)?.storageBytes || 0;
  const fileSize = formatFileSize(rawSize);

  return (
    <div className="rounded-2xl border border-gray-200 bg-white overflow-hidden shadow-sm animate-fade-in">
      {/* Primary Video / Media Preview */}
      <div className="aspect-[16/9] bg-gray-950 flex items-center justify-center relative border-b border-gray-100 overflow-hidden group">
        {previewUrl ? (
          <video
            className="w-full h-full object-contain"
            controls
            playsInline
            src={previewUrl}
          />
        ) : isDownloadingYoutube ? (
          <div className="flex flex-col items-center justify-center p-8 text-center select-none">
            <div className="w-12 h-12 rounded-2xl bg-gray-900 border border-gray-800 flex items-center justify-center animate-pulse mb-3">
              <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2563eb" strokeWidth="2.5" className="animate-spin">
                <path d="M21 12a9 9 0 11-6.219-8.56" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-white">Importing from YouTube…</p>
            <p className="text-xs text-gray-500 mt-1">Downloading video formats and processing thumbnail</p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center p-8 text-center select-none">
            <div className="w-10 h-10 rounded-xl bg-gray-900 flex items-center justify-center mb-2">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
            </div>
            <span className="text-xs text-gray-400 font-medium">Processing video preview...</span>
          </div>
        )}
      </div>

      {/* Media Details Footer */}
      <div className="p-5 flex flex-col gap-3">
        <div className="flex items-center justify-between gap-4">
          <div className="flex items-center gap-3.5 min-w-0">
            <div className="w-10 h-10 rounded-xl bg-gray-50 border border-gray-200 flex items-center justify-center flex-shrink-0 text-gray-600">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                <polygon points="23 7 16 12 23 17 23 7" /><rect x="1" y="5" width="15" height="14" rx="2" />
              </svg>
            </div>
            <div className="min-w-0">
              <p className="text-base font-semibold text-gray-950 truncate">{fileName}</p>
              {fileSize && <p className="text-xs text-gray-400 mt-0.5 font-medium">{fileSize}</p>}
            </div>
          </div>

          <div className="flex items-center gap-2 shrink-0">
            {jobId && (
              <span className="text-xs text-gray-400 font-mono hidden sm:inline-block bg-gray-50 border border-gray-200 px-2 py-1 rounded-md">
                {jobId}
              </span>
            )}
            {(progress === 100 || (jobId && !isDownloadingYoutube)) && (
              <span className="bg-green-50 text-green-700 text-xs px-3 py-1 rounded-full border border-green-200 font-semibold flex items-center gap-1.5 shadow-sm">
                ✓ Ready
              </span>
            )}
          </div>
        </div>

        {/* Upload / Import Progress Bar */}
        {progress > 0 && progress < 100 && (
          <div className="space-y-1.5 pt-2 border-t border-gray-100">
            <div className="flex justify-between text-xs text-gray-500 font-medium">
              <span>{isDownloadingYoutube ? "Downloading video..." : "Uploading file..."}</span>
              <span className="tabular-nums font-semibold text-gray-950">{progress}%</span>
            </div>
            <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
              <div
                className="h-full bg-gray-950 rounded-full transition-all duration-300"
                style={{ width: `${progress}%` }}
              />
            </div>
          </div>
        )}

        {/* Error message box */}
        {error && (
          <div className="mt-2 rounded-xl border border-red-200 bg-red-50 p-3.5 text-xs text-red-600 font-medium leading-relaxed animate-fade-in">
            {error}
          </div>
        )}
      </div>
    </div>
  );
};
