import React, { useRef, useState, useEffect } from "react";
import { ClipSelector } from "./ClipSelector";
import { EditorLayout } from "../Editor/EditorLayout";
import { useResultsStore } from "../../stores/resultsStore";
import { deepEqual, cloneDeep, getDirtyFields, getDiffPayload } from "../../utils/deepEqual";

interface ResultsPageProps {
  clips: any[];
  selectedClipId: string | null;
  selectedClipIds: string[];
  editorOpen: boolean;
  editorTab: any;
  saving: boolean;
  clipEdits: Record<string, any>;
  setClips: (clips: any[]) => void;
  setSelectedClipId: (id: string | null) => void;
  toggleClip: (id: string) => void;
  updateClipTrim: (clipId: string, start: number, end: number) => void;
  openEditor: () => void;
  closeEditor: () => void;
  setEditorTab: (tab: any) => void;
  setSaving: (saving: boolean) => void;
  updateClipEdit: (clipId: string, edits: any) => void;
  applyEditsToClip: (clipId: string) => void;
  activeJobId: string | null;
  renderingClips: Record<string, { stage: string; progress: number }>;
  setRenderingClip: (clipId: string, stage: string | null, progress: number | null) => void;
  setProcessMessage: (message: string | null) => void;
  exportSelected: () => void;
  memes: any[];
  musicTracks: any[];
  hasMusicLibrary: boolean;
  settings: any;
  handleAssetUpload: (type: "memes", file: File) => Promise<void>;
}

const getScoreColor = (score: number) => {
  if (score >= 85) return "bg-green-50 text-green-700 border-green-200";
  if (score >= 70) return "bg-amber-50 text-amber-700 border-amber-200";
  return "bg-blue-50 text-blue-700 border-blue-200";
};

const formatHookType = (type?: string) => {
  if (!type) return "Clip Hook";
  return type.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
};

function getCaptionForTime(words: any[] | undefined, time: number, displayMode: string = "phrase") {
  if (!words || words.length === 0) return null;

  const chunks: any[][] = [];
  let currentChunk: any[] = [];

  if (displayMode === "word") {
    for (const w of words) {
      chunks.push([w]);
    }
  } else if (displayMode === "sentence") {
    for (const w of words) {
      currentChunk.push(w);
      if (/[.?!]$/.test(w.word.trim())) {
        chunks.push(currentChunk);
        currentChunk = [];
      }
    }
    if (currentChunk.length > 0) chunks.push(currentChunk);
  } else {
    let maxWords = 5;
    const match = displayMode.match(/^(\d+)-words?$/);
    if (match) {
      maxWords = parseInt(match[1], 10);
    }
    for (const w of words) {
      currentChunk.push(w);
      if (currentChunk.length >= maxWords || /[.?!]$/.test(w.word.trim())) {
        chunks.push(currentChunk);
        currentChunk = [];
      }
    }
    if (currentChunk.length > 0) chunks.push(currentChunk);
  }

  const activeChunk = chunks.find(chunk => {
    const chunkStart = chunk[0].start;
    const chunkEnd = chunk[chunk.length - 1].end;
    return time >= chunkStart && time <= chunkEnd;
  });

  return activeChunk || null;
}

function hexToRgba(hex: string, alpha: number): string {
  if (!hex || !hex.startsWith("#")) return `rgba(0, 0, 0, ${alpha})`;
  const r = parseInt(hex.slice(1, 3), 16) || 0;
  const g = parseInt(hex.slice(3, 5), 16) || 0;
  const b = parseInt(hex.slice(5, 7), 16) || 0;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function getCaptionPositionStyle(position: string, customMarginV?: number): React.CSSProperties {
  switch (position) {
    case "top":
      return { top: "8%" };
    case "top-center":
      return { top: "20%" };
    case "center":
      return { top: "50%", transform: "translateY(-50%)" };
    case "lower-third":
      return { bottom: "25%" };
    case "custom":
      const pct = Math.max(5, Math.min(95, (customMarginV ?? 170) / 1920 * 100));
      return { bottom: `${pct}%` };
    case "bottom":
    default:
      return { bottom: "10%" };
  }
}

function getCaptionContainerStyle(ec: any): React.CSSProperties {
  const styles: React.CSSProperties = {
    fontFamily: ec.captionFontFamily || "Arial Black",
    fontSize: `${(ec.captionFontSize || 72) * 0.32}px`, // scale down for player size
    fontWeight: ec.captionFontWeight === "normal" ? "normal" : "bold",
    lineHeight: ec.captionLineHeight || 1.2,
    letterSpacing: `${(ec.captionLetterSpacing || 0) * 0.32}px`,
    padding: `${(ec.captionPadding || 12) * 0.35}px`,
    opacity: (ec.captionOpacity ?? 100) / 100,
    transition: "all 0.1s ease-out",
  };

  const containerType = ec.captionContainerType || "none";
  const bgColor = ec.captionBgColor || "#000000";
  const outlineColor = ec.captionOutlineColor || "#000000";
  const borderRadius = ec.captionBorderRadius || 8;

  if (containerType === "solid") {
    styles.backgroundColor = bgColor;
    styles.borderRadius = `${borderRadius}px`;
  } else if (containerType === "transparent-box") {
    styles.backgroundColor = hexToRgba(bgColor, 0.6);
    styles.borderRadius = `${borderRadius}px`;
  } else if (containerType === "border-only") {
    styles.border = `2px solid ${outlineColor}`;
    styles.borderRadius = `${borderRadius}px`;
    styles.backgroundColor = "transparent";
  } else if (containerType === "gradient") {
    styles.background = `linear-gradient(135deg, ${bgColor}, ${outlineColor})`;
    styles.borderRadius = `${borderRadius}px`;
  } else {
    styles.backgroundColor = "transparent";
  }

  return styles;
}

function getCaptionWordStyle(ec: any, isHighlighted: boolean, index: number): React.CSSProperties {
  const styles: React.CSSProperties = {
    transition: "all 0.15s cubic-bezier(0.175, 0.885, 0.32, 1.275)",
    display: "inline-block",
  };

  const textColor = ec.captionTextColor || ec.textColor || "#ffffff";
  const outlineColor = ec.captionOutlineColor || "#000000";
  const outlineSize = ec.captionOutlineSize ?? 3;
  const shadowColor = ec.captionShadowColor || "#000000";
  const shadowSize = ec.captionShadowSize ?? 2;
  const highlightColor = ec.captionHighlightColor || "#ffff00";
  const containerType = ec.captionContainerType || "none";
  const highlightMode = ec.highlightColorMode || "single";

  // Outline/Shadow mapping
  if (containerType === "outline") {
    styles.textShadow = `
      -${outlineSize}px -${outlineSize}px 0 ${outlineColor},  
       ${outlineSize}px -${outlineSize}px 0 ${outlineColor},
      -${outlineSize}px  ${outlineSize}px 0 ${outlineColor},
       ${outlineSize}px  ${outlineSize}px 0 ${outlineColor}
    `;
  } else if (containerType === "shadow") {
    styles.textShadow = `${shadowSize}px ${shadowSize}px 0px ${shadowColor}`;
  } else if (containerType === "glow") {
    styles.textShadow = `0 0 8px ${outlineColor}, 0 0 12px ${outlineColor}`;
  } else if (containerType === "none" || containerType === "border-only") {
    styles.textShadow = `-1.5px -1.5px 0 ${outlineColor}, 1.5px -1.5px 0 ${outlineColor}, -1.5px 1.5px 0 ${outlineColor}, 1.5px 1.5px 0 ${outlineColor}`;
  }

  // Text color
  styles.color = isHighlighted ? highlightColor : textColor;

  if (isHighlighted) {
    if (highlightMode === "multi") {
      const palette = ["#ffff00", "#00ff00", "#ff0000", "#00ffff"];
      styles.color = palette[index % palette.length];
    } else if (highlightMode === "random") {
      const palette = ["#ffff00", "#00ff00", "#ff0000", "#00ffff"];
      styles.color = palette[(index * 7) % palette.length];
    }

    if (highlightMode === "creator") {
      styles.transform = "scale(1.22)";
      styles.color = highlightColor;
      styles.textTransform = "uppercase";
    } else {
      styles.transform = "scale(1.12)";
    }
  }

  return styles;
}

function getCaptionWordClassName(ec: any, isHighlighted: boolean): string {
  const animType = ec.captionAnimationType || "none";
  if (isHighlighted) {
    switch (animType) {
      case "pop":
        return "animate-pop";
      case "bounce":
        return "animate-bounce-pop";
      case "scale":
        return "animate-scale-up";
      case "zoom":
        return "animate-zoom-in";
      case "elastic":
        return "animate-elastic";
      case "fade":
        return "animate-fade-in-quick";
      default:
        return "";
    }
  }
  return "";
}

export const ResultsPage: React.FC<ResultsPageProps> = ({
  clips,
  selectedClipId,
  selectedClipIds,
  editorOpen,
  editorTab,
  saving,
  clipEdits,
  setClips,
  setSelectedClipId,
  toggleClip,
  updateClipTrim,
  openEditor,
  closeEditor,
  setEditorTab,
  setSaving,
  updateClipEdit,
  applyEditsToClip,
  activeJobId,
  renderingClips,
  setRenderingClip,
  setProcessMessage,
  exportSelected,
  memes,
  musicTracks,
  hasMusicLibrary,
  settings,
  handleAssetUpload,
}) => {
  const videoRef = useRef<HTMLVideoElement>(null);
  const trimTimeoutRef = useRef<any>(null);
  const originalClipStatesRef = useRef<Record<string, any>>({});
  const [currentTime, setCurrentTime] = useState(0);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [expandedDesc, setExpandedDesc] = useState(false);
  const [savingClips, setSavingClips] = useState<Record<string, boolean>>({});
  const [saveSuccessClips, setSaveSuccessClips] = useState<Record<string, string | null>>({});
  const [renderErrorClips, setRenderErrorClips] = useState<Record<string, string | null>>({});

  const copyToClipboard = (text: string, fieldName: string) => {
    if (!text) return;
    navigator.clipboard.writeText(text);
    setCopiedField(fieldName);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const [videoVersions, setVideoVersions] = useState<Record<string, number>>({});

  const incrementVideoVersion = (clipId: string) => {
    setVideoVersions((prev) => ({
      ...prev,
      [clipId]: (prev[clipId] || 0) + 1
    }));
  };

  const selectedClip = clips.find((clip) => clip.id === selectedClipId) ?? null;
  const currentClipState = selectedClip
    ? { ...(selectedClip || {}), ...(selectedClipId ? (clipEdits[selectedClipId] || {}) : {}) }
    : null;

  const isCurrentClipSaving = selectedClipId ? Boolean(savingClips[selectedClipId]) : false;
  const currentClipSaveSuccess = selectedClipId ? (saveSuccessClips[selectedClipId] ?? null) : null;
  const currentClipRenderError = selectedClipId ? (renderErrorClips[selectedClipId] ?? null) : null;
  const currentOriginalState = selectedClipId ? (originalClipStatesRef.current[selectedClipId] ?? null) : null;

  // Initialize/Update per-clip baseline original state when modal opens or clip changes
  useEffect(() => {
    if (editorOpen && selectedClipId && selectedClip) {
      if (!originalClipStatesRef.current[selectedClipId]) {
        const initialEffective = {
          ...(selectedClip || {}),
          ...(clipEdits[selectedClipId] || {})
        };
        originalClipStatesRef.current[selectedClipId] = cloneDeep(initialEffective);
      }
    } else if (!editorOpen) {
      originalClipStatesRef.current = {};
      setSaveSuccessClips({});
      setRenderErrorClips({});
      setSavingClips({});
    }
  }, [editorOpen, selectedClipId]);

  // Compute field-level and global dirty state strictly for current clip
  const dirtyFields = (selectedClipId && currentOriginalState && currentClipState)
    ? getDirtyFields(currentOriginalState, currentClipState)
    : {};
  const isDirty = Object.values(dirtyFields).some(Boolean);

  // Keyboard shortcut: ESC key closes editor directly
  useEffect(() => {
    if (!editorOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        if (selectedClipId) {
          setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
        }
        closeEditor();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [editorOpen, selectedClipId]);

  useEffect(() => {
    if (videoRef.current) {
      videoRef.current.playbackRate = 1.0;
    }
    setCurrentTime(0);
  }, [selectedClipId]);

  const handleTimeUpdate = () => {
    if (videoRef.current) {
      setCurrentTime(videoRef.current.currentTime);
    }
  };

  const handleLoadedMetadata = () => {
    if (!selectedClipId || !videoRef.current) return;
    videoRef.current.playbackRate = 1.0;
    const clip = clips.find((c) => c.id === selectedClipId);
    if (!clip) return;

    if (clip.trimStart === undefined || clip.trimEnd === undefined) {
      updateClipTrim(
        selectedClipId,
        clip.userStart ?? clip.aiStart ?? 0,
        clip.userEnd ?? clip.aiEnd ?? (videoRef.current.duration || clip.duration)
      );
    }
  };

  const handleTrimChange = (start: number, end: number) => {
    if (!selectedClipId) return;
    const clip = clips.find((c) => c.id === selectedClipId);
    if (!clip) return;

    const newStart = Math.min(start, end - 0.5);
    const newEnd = Math.max(end, start + 0.5);

    updateClipTrim(selectedClipId, newStart, newEnd);

    if (videoRef.current) {
      if (videoRef.current.currentTime < newStart) {
        videoRef.current.currentTime = newStart;
      } else if (videoRef.current.currentTime > newEnd) {
        videoRef.current.currentTime = newStart;
      }
    }

    if (trimTimeoutRef.current) {
      clearTimeout(trimTimeoutRef.current);
    }

    trimTimeoutRef.current = setTimeout(async () => {
      try {
        await fetch(`http://localhost:3001/api/results/${activeJobId}/clips/${selectedClipId}/trim`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ userStart: newStart, userEnd: newEnd })
        });
      } catch (err) {
        console.error("Failed to save trim coordinates to server:", err);
      }
    }, 500);
  };

  const handleDiscardEdits = () => {
    if (selectedClipId) {
      updateClipEdit(selectedClipId, {});
      useResultsStore.setState((state) => {
        const next = { ...state.clipEdits };
        delete next[selectedClipId];
        return { clipEdits: next };
      });
    }
    // setShowUnsavedPrompt(false); // Cleaned up
    if (selectedClipId) {
      setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
    }
    closeEditor();
  };

  const handleSaveRender = async (targetClipIdParam?: string, closeAfterSave: boolean = true) => {
    const targetClipId = targetClipIdParam || selectedClipId;
    if (!activeJobId || !targetClipId || savingClips[targetClipId]) return;

    const clipOriginalState = originalClipStatesRef.current[targetClipId];
    const clipTargetObj = clips.find((c) => c.id === targetClipId);
    const clipStateToSave = clipTargetObj
      ? { ...(clipTargetObj || {}), ...(clipEdits[targetClipId] || {}) }
      : null;

    const targetDirtyFields = (clipOriginalState && clipStateToSave)
      ? getDirtyFields(clipOriginalState, clipStateToSave)
      : {};
    const targetIsDirty = Object.values(targetDirtyFields).some(Boolean);

    // Strict guard: Never call save API when target clip is clean
    if (!targetIsDirty && clipOriginalState) {
      if (closeAfterSave && useResultsStore.getState().selectedClipId === targetClipId) {
        closeEditor();
      }
      return;
    }

    const diffPayload = getDiffPayload(clipOriginalState || {}, clipStateToSave || {});

    setRenderErrorClips((prev) => ({ ...prev, [targetClipId]: null }));
    setSaveSuccessClips((prev) => ({ ...prev, [targetClipId]: null }));
    setSavingClips((prev) => ({ ...prev, [targetClipId]: true }));
    setRenderingClip(targetClipId, "Saving Changes...", 5);

    try {
      if (Object.keys(diffPayload).length > 0) {
        const editRes = await fetch(`http://localhost:3001/api/results/${activeJobId}/clips/${targetClipId}/edit`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(diffPayload)
        });
        if (!editRes.ok) {
          const errData = await editRes.json().catch(() => ({}));
          throw new Error(errData.message || "Failed to save edits.");
        }
        applyEditsToClip(targetClipId);
      }

      setRenderingClip(targetClipId, "Rendering Video...", 10);

      const renderRes = await fetch(`http://localhost:3001/api/results/${activeJobId}/clips/${targetClipId}/render`, {
        method: "POST"
      });
      if (!renderRes.ok) {
        const errData = await renderRes.json().catch(() => ({}));
        throw new Error(errData.message || "Render request failed.");
      }

      incrementVideoVersion(targetClipId);
      setProcessMessage("Changes saved & rendered successfully.");
      setRenderingClip(targetClipId, null, null);
      setSavingClips((prev) => ({ ...prev, [targetClipId]: false }));

      // Update baseline state ONLY for targetClipId
      originalClipStatesRef.current[targetClipId] = cloneDeep(clipStateToSave);

      setSaveSuccessClips((prev) => ({ ...prev, [targetClipId]: "Changes saved successfully ✓" }));
      setTimeout(() => {
        setSaveSuccessClips((prev) => ({ ...prev, [targetClipId]: null }));
      }, 3000);

      if (closeAfterSave && useResultsStore.getState().selectedClipId === targetClipId) {
        closeEditor();
      }
    } catch (err: any) {
      setSavingClips((prev) => ({ ...prev, [targetClipId]: false }));
      const msg = err.message || "Failed to process edits.";
      setRenderErrorClips((prev) => ({ ...prev, [targetClipId]: msg }));
      setProcessMessage(`Error: ${msg}`);
      setRenderingClip(targetClipId, null, null);
    }
  };

  const ec = currentClipState;

  const captionChunk = ec ? getCaptionForTime(ec.words, currentTime, ec.captionDisplayMode ?? settings.captionDisplayMode ?? "phrase") : null;
  const activeRender = selectedClipId ? renderingClips[selectedClipId] : null;
  const isCurrentClipRendering = selectedClipId ? Boolean(renderingClips[selectedClipId]) : false;

  return (
    <div className="flex h-screen bg-white font-sans overflow-hidden">
      {/* Left sidebar: clip list */}
      <aside className="w-[360px] flex-shrink-0 border-r border-gray-200 flex flex-col bg-gray-50/80 h-full">
        {/* Header */}
        <div className="px-4 py-5 border-b border-gray-200">
          <h2 className="text-sm font-semibold text-gray-950 font-[Geist]">Generated Clips</h2>
          <p className="text-xs text-gray-400 mt-0.5">{clips.length} clips ready</p>
        </div>

        {/* Scrollable clip list */}
        <div className="flex-1 overflow-y-auto p-3">
          <ClipSelector
            clips={clips.map((c) => ({
              ...c,
              thumbnailUrl: c.thumbnailUrl ? `${c.thumbnailUrl}?v=${videoVersions[c.id] || 0}` : undefined
            }))}
            selectedClipId={selectedClipId}
            selectedClipIds={selectedClipIds}
            renderingClips={renderingClips}
            setSelectedClipId={setSelectedClipId}
            toggleClip={toggleClip}
          />
        </div>

        {/* Footer: export selected */}
        <div className="p-4 border-t border-gray-200">
          <button
            onClick={exportSelected}
            className="w-full bg-gray-950 text-white text-sm font-medium rounded-lg py-2.5 hover:bg-gray-800 transition-colors disabled:opacity-40"
            disabled={!activeJobId || selectedClipIds.length === 0}
          >
            Export {selectedClipIds.length > 0 ? `(${selectedClipIds.length})` : 'Selected'}
          </button>
        </div>
      </aside>

      {/* Main area */}
      <main className="flex-1 overflow-y-auto h-full">
        {selectedClip && ec ? (
          <div className="p-6 max-w-2xl mx-auto">
            {/* Video player */}
            <div className="rounded-xl overflow-hidden bg-black relative mx-auto" style={{ aspectRatio: '9/16', maxHeight: '500px' }}>
              <video
                ref={videoRef}
                className="w-full h-full object-contain"
                controls
                key={`${selectedClip.mediaUrl}?v=${videoVersions[selectedClip.id] || 0}`}
                src={`http://localhost:3001${selectedClip.mediaUrl}?v=${videoVersions[selectedClip.id] || 0}`}
                onTimeUpdate={handleTimeUpdate}
                onLoadedMetadata={handleLoadedMetadata}
              />

              {/* Live Auto Hook Overlay (real-time DOM preview in the editor player) */}
              {editorOpen && (() => {
                const isHookEnabled = ec.autoHook !== undefined 
                  ? Boolean(ec.autoHook) 
                  : (settings.autoHook !== undefined ? Boolean(settings.autoHook) : true);
                const hookText = ec.autoHookText ?? ec.hook ?? selectedClip.hook ?? "";
                
                if (!isHookEnabled || !hookText.trim()) return null;

                const font = ec.autoHookFont ?? settings.autoHookFont ?? "Arial Black";
                const fontSize = ec.autoHookFontSize ?? settings.autoHookFontSize ?? 120;
                const textColor = ec.autoHookColor ?? settings.autoHookColor ?? "#ffffff";
                const bgColor = ec.autoHookBgColor ?? settings.autoHookBgColor ?? "#16a34a";
                const pos = ec.autoHookPosition ?? settings.autoHookPosition ?? "top-center";
                
                const scale = 0.28;
                const padding = Math.round(12 * (300 / 430));
                const radius = Math.round(8 * (300 / 430));
                const scaledFontSize = Math.round(fontSize * scale);

                let topOffset = "11.4%";
                if (pos === "top") topOffset = "7.3%";
                if (pos === "middle") topOffset = "42%";

                return (
                  <div
                    className="absolute inset-x-0 pointer-events-none flex justify-center z-30 transition-all"
                    style={{ top: topOffset }}
                  >
                    <div
                      style={{
                        backgroundColor: bgColor,
                        color: textColor,
                        fontFamily: font,
                        fontSize: `${scaledFontSize}px`,
                        fontWeight: "bold",
                        padding: `${padding}px ${padding * 1.5}px`,
                        borderRadius: `${radius}px`,
                        textAlign: "center",
                        maxWidth: "85%",
                        lineHeight: 1.25,
                        boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                      }}
                      className="animate-fade-in"
                    >
                      {hookText}
                    </div>
                  </div>
                );
              })()}

              {/* Live Caption Overlay (real-time DOM preview in the editor player) */}
              {editorOpen && captionChunk && (
                <div
                  className="absolute inset-x-4 pointer-events-none flex justify-center z-25 transition-all"
                  style={getCaptionPositionStyle(ec.captionPosition ?? settings.captionPosition ?? "bottom", ec.captionCustomMarginV)}
                >
                  <div
                    style={getCaptionContainerStyle(ec)}
                    className="flex flex-wrap justify-center gap-x-2 text-center"
                  >
                    {captionChunk.map((wordObj: any, index: number) => {
                      const isHighlighted = currentTime >= wordObj.start && currentTime <= wordObj.end;
                      return (
                        <span
                          key={index}
                          style={getCaptionWordStyle(ec, isHighlighted, index)}
                          className={getCaptionWordClassName(ec, isHighlighted)}
                        >
                          {wordObj.word}
                        </span>
                      );
                    })}
                  </div>
                </div>
              )}

              {/* Meme prepend indication */}
              {ec.memePath && (
                <div className="absolute top-3 left-3 bg-amber-50 text-amber-700 border border-amber-200 px-2 py-0.5 rounded text-[10px] font-medium z-20 pointer-events-none shadow-sm flex items-center gap-1 animate-fade-in">
                  🎬 Meme Prepend
                </div>
              )}

              {/* Caption overlay intentionally removed — rendered video already has baked-in captions */}

              {/* Rendering progress overlay */}
              {activeRender && (
                <div className="absolute inset-0 bg-white/90 backdrop-blur-md z-30 flex flex-col items-center justify-center p-6 text-center animate-fade-in">
                  <div className="w-10 h-10 rounded-full border-2 border-gray-200 border-t-blue-600 animate-spin mb-4" />
                  <h3 className="text-sm font-semibold text-gray-950 mb-1">
                    {activeRender.stage}
                  </h3>
                  {activeRender.progress !== null && (
                    <div className="w-full max-w-[180px] mt-2">
                      <div className="flex justify-between items-center text-xs font-medium text-gray-500 mb-1.5">
                        <span>Progress</span>
                        <span>{activeRender.progress}%</span>
                      </div>
                      <div className="h-1.5 w-full bg-gray-100 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-blue-600 rounded-full transition-all duration-300 ease-out"
                          style={{ width: `${activeRender.progress}%` }}
                        />
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>

            {/* Clip info & AI Metadata */}
            <div className="mt-6 rounded-2xl border border-gray-200 bg-gray-50 p-6 space-y-6">
              {/* Header & Main Actions */}
              <div className="flex flex-col sm:flex-row items-start justify-between gap-4 border-b border-gray-200 pb-5">
                <div className="flex-1 min-w-0">
                  <h1 className="text-xl font-semibold text-gray-950 font-[Geist] leading-snug ">
                    {selectedClip.title || `Clip ${selectedClip.id}`}
                  </h1>
                  <div className="flex flex-wrap items-center gap-2 mt-2.5">
                    <span className={`text-xs font-semibold px-2.5 py-0.5 rounded-full border ${getScoreColor(selectedClip.score ?? selectedClip.viralScore)}`}>
                      🔥 Viral Score {selectedClip.viralScore ?? selectedClip.score != null ? `${selectedClip.viralScore ?? selectedClip.score} / 100` : "N/A"}
                    </span>
                    <span className="text-xs text-gray-600 font-mono bg-white border border-gray-200 rounded-full px-2.5 py-0.5">
                      ⏱️ {selectedClip.duration.toFixed(1)}s
                    </span>
                    {selectedClip.platformRecommendation && (
                      <span className="text-xs text-blue-700 bg-blue-50 border border-blue-200 rounded-full px-2.5 py-0.5 font-medium">
                        🎯 {selectedClip.platformRecommendation}
                      </span>
                    )}
                    {selectedClip.suggestedPostingTime && (
                      <span className="text-xs text-gray-600 bg-white border border-gray-200 rounded-full px-2.5 py-0.5">
                        ⏰ {selectedClip.suggestedPostingTime}
                      </span>
                    )}
                  </div>
                </div>

                {/* Primary Action Buttons */}
                <div className="flex items-center gap-2 flex-shrink-0">
                  <button
                    onClick={() => openEditor()}
                    className="inline-flex items-center gap-1.5 bg-white border border-gray-200 text-gray-800 text-xs font-semibold rounded-lg px-3.5 py-2 hover:bg-gray-100 transition-colors shadow-sm"
                  >
                    <svg className="w-3.5 h-3.5 text-gray-500" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 210.3H3v-3.572L16.732 3.732z" /></svg>
                    Edit Clip
                  </button>
                  <a
                    href={`http://localhost:3001/api/results/${activeJobId}/clips/${selectedClip.id}/download`}
                    className="inline-flex items-center gap-1.5 bg-gray-950 text-white text-xs font-semibold rounded-lg px-3.5 py-2 hover:bg-gray-800 transition-colors shadow-sm"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" /></svg>
                    Download
                  </a>
                </div>
              </div>

              {/* 📊 Score Breakdown Card */}
              <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-3 shadow-sm">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">📊 Performance & Score Breakdown</span>
                  <span className="text-xs font-bold text-emerald-600 bg-emerald-50 border border-emerald-200 px-2.5 py-0.5 rounded-full">
                    Overall: {selectedClip.score != null ? `${selectedClip.score} / 100` : "N/A"}
                  </span>
                </div>
                <div className="grid grid-cols-2 sm:grid-cols-3 gap-2.5 text-xs font-medium">
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-2.5 flex flex-col">
                    <span className="text-gray-400 text-[10px]">Hook Score</span>
                    <span className="text-gray-950 font-bold text-sm mt-0.5">
                      {selectedClip.hookScore != null ? `${selectedClip.hookScore} / 100` : "N/A"}
                    </span>
                  </div>
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-2.5 flex flex-col">
                    <span className="text-gray-400 text-[10px]">Retention</span>
                    <span className="text-gray-950 font-bold text-sm mt-0.5">
                      {selectedClip.retentionScore != null ? `${selectedClip.retentionScore} / 100` : "N/A"}
                    </span>
                  </div>
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-2.5 flex flex-col">
                    <span className="text-gray-400 text-[10px]">Emotional Impact</span>
                    <span className="text-gray-950 font-bold text-sm mt-0.5">
                      {selectedClip.emotionalImpact != null ? `${selectedClip.emotionalImpact} / 100` : "N/A"}
                    </span>
                  </div>
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-2.5 flex flex-col">
                    <span className="text-gray-400 text-[10px]">Production Score</span>
                    <span className="text-gray-950 font-bold text-sm mt-0.5">
                      {selectedClip.productionScore != null ? `${selectedClip.productionScore} / 100` : "N/A"}
                    </span>
                  </div>
                  <div className="bg-gray-50 border border-gray-100 rounded-lg p-2.5 flex flex-col">
                    <span className="text-gray-400 text-[10px]">SEO Score</span>
                    <span className="text-gray-950 font-bold text-sm mt-0.5">
                      {selectedClip.seoScore != null ? `${selectedClip.seoScore} / 100` : "N/A"}
                    </span>
                  </div>
                  <div className="bg-emerald-50/60 border border-emerald-200 rounded-lg p-2.5 flex flex-col">
                    <span className="text-emerald-700 text-[10px] font-semibold">Viral Score</span>
                    <span className="text-emerald-800 font-bold text-sm mt-0.5">
                      {selectedClip.viralScore != null ? `${selectedClip.viralScore} / 100` : (selectedClip.score != null ? `${selectedClip.score} / 100` : "N/A")}
                    </span>
                  </div>
                </div>
              </div>

              {/* ── AI Generated Metadata Section ── */}
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <h2 className="text-xs font-bold text-gray-500 uppercase tracking-wider font-[Geist]">
                    ✨ AI Generated Metadata
                  </h2>
                  <button
                    type="button"
                    onClick={() => {
                      const allText = `Title: ${selectedClip.title || ""}\n\nDescription: ${selectedClip.description || ""}\n\nHashtags: ${Array.isArray(selectedClip.tags) ? selectedClip.tags.join(" ") : ""}`;
                      copyToClipboard(allText, "all");
                    }}
                    className="text-xs font-medium text-blue-600 hover:text-blue-800 transition-colors"
                  >
                    {copiedField === "all" ? "✓ Copied All Metadata!" : "Copy All Metadata"}
                  </button>
                </div>

                {/* Optimized Title Card */}
                <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 shadow-sm">
                  <div className="flex items-center justify-between">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Optimized Title</span>
                    <button
                      type="button"
                      onClick={() => copyToClipboard(selectedClip.title || "", "title")}
                      className="text-xs text-gray-500 hover:text-gray-950 font-medium transition-colors"
                    >
                      {copiedField === "title" ? "✓ Copied" : "Copy Title"}
                    </button>
                  </div>
                  <p className="text-sm font-medium text-gray-950 leading-snug">
                    {selectedClip.title || "—"}
                  </p>
                </div>

                {/* Hook Core Text Card */}
                {selectedClip.hook && (
                  <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 shadow-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Hook Core Text</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(selectedClip.hook || "", "hook")}
                        className="text-xs text-gray-500 hover:text-gray-950 font-medium transition-colors"
                      >
                        {copiedField === "hook" ? "✓ Copied" : "Copy Hook"}
                      </button>
                    </div>
                    <p className="text-sm italic text-gray-800 leading-relaxed font-serif">
                      "{selectedClip.hook}"
                    </p>
                  </div>
                )}

                {/* AI Description Card */}
                {selectedClip.description && (
                  <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 shadow-sm">
                    <div className="flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Description</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(selectedClip.description || "", "desc")}
                        className="text-xs text-gray-500 hover:text-gray-950 font-medium transition-colors"
                      >
                        {copiedField === "desc" ? "✓ Copied Full Description" : "Copy Description"}
                      </button>
                    </div>
                    <p className="text-xs text-gray-700 leading-relaxed whitespace-pre-line">
                      {expandedDesc || selectedClip.description.length <= 160
                        ? selectedClip.description
                        : `${selectedClip.description.slice(0, 160)}...`}
                    </p>
                    {selectedClip.description.length > 160 && (
                      <button
                        type="button"
                        onClick={() => setExpandedDesc(!expandedDesc)}
                        className="text-xs font-semibold text-blue-600 hover:text-blue-800 transition-colors pt-1"
                      >
                        {expandedDesc ? "Show Less ↑" : "Read More ↓"}
                      </button>
                    )}
                  </div>
                )}

                {/* Hashtags Card */}
                {Array.isArray(selectedClip.tags) && selectedClip.tags.length > 0 && (
                  <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 shadow-sm">
                    <div className="flex items-center justify-between mb-1">
                      <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide">Hashtags</span>
                      <button
                        type="button"
                        onClick={() => copyToClipboard(selectedClip.tags.join(" "), "tags")}
                        className="text-xs text-gray-500 hover:text-gray-950 font-medium transition-colors"
                      >
                        {copiedField === "tags" ? "✓ Copied" : "Copy Hashtags"}
                      </button>
                    </div>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedClip.tags.map((tag: string, idx: number) => (
                        <span key={idx} className="text-xs bg-blue-50 text-blue-700 border border-blue-100 rounded-md px-2 py-0.5 font-medium">
                          {tag.startsWith("#") ? tag : `#${tag}`}
                        </span>
                      ))}
                    </div>
                  </div>
                )}

                {/* Keywords Pills */}
                {Array.isArray(selectedClip.keywords) && selectedClip.keywords.length > 0 && (
                  <div className="rounded-xl border border-gray-200 bg-white p-4 space-y-2 shadow-sm">
                    <span className="text-[11px] font-semibold text-gray-400 uppercase tracking-wide block">SEO Keywords</span>
                    <div className="flex flex-wrap gap-1.5">
                      {selectedClip.keywords.map((kw: string, idx: number) => (
                        <span key={idx} className="text-xs bg-gray-100 text-gray-700 rounded-md px-2 py-0.5 font-medium capitalize">
                          {kw}
                        </span>
                      ))}
                    </div>
                  </div>
                )}
              </div>


            </div>
          </div>
        ) : (
          <div className="flex items-center justify-center h-full">
            <p className="text-gray-400 text-sm font-medium">Select a clip to preview</p>
          </div>
        )}
      </main>

      {/* Editor modal — centered dialog */}
      {editorOpen && selectedClip && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-sm"
          onClick={(e) => {
            if (e.target === e.currentTarget) {
              if (selectedClipId) setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
              closeEditor();
            }
          }}
        >
          <div className="relative w-full max-w-2xl max-h-[90vh] flex flex-col rounded-2xl bg-white shadow-2xl border border-gray-200 animate-scale-in">
            {/* Modal header */}
            <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 flex-shrink-0">
              <div>
                <h2 className="text-base font-semibold text-gray-950 font-[Geist]">Edit Clip</h2>
                <p className="text-xs text-gray-400 mt-0.5  max-w-xs">{selectedClip.title}</p>
              </div>
              <button
                onClick={() => {
                  if (selectedClipId) setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
                  closeEditor();
                }}
                className="p-2 rounded-lg text-gray-400 hover:text-gray-700 hover:bg-gray-100 transition-colors"
                aria-label="Close editor"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
              </button>
            </div>

            {/* Modal body — scrollable */}
            <div className="flex-1 overflow-y-auto">
              <EditorLayout
                selectedClip={selectedClip}
                clipEdits={clipEdits}
                dirtyFields={dirtyFields}
                editorTab={editorTab}
                setEditorTab={setEditorTab}
                updateClipEdit={updateClipEdit}
                memes={memes}
                musicTracks={musicTracks}
                hasMusicLibrary={hasMusicLibrary}
                settings={settings}
                handleAssetUpload={handleAssetUpload}
                activeJobId={activeJobId}
                selectedClipIds={selectedClipIds}
                exportSelected={exportSelected}
              />
            </div>

            {/* Modal footer — Save / Cancel / Error */}
            <div className="flex flex-col gap-2 px-6 py-4 border-t border-gray-100 flex-shrink-0 bg-gray-50 rounded-b-2xl">
              {/* Error banner */}
              {currentClipRenderError && (
                <div className="flex items-start gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-xs font-medium animate-fade-in">
                  <svg className="w-4 h-4 flex-shrink-0 mt-0.5 text-red-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-2.5L13.732 4c-.77-.833-1.964-.833-2.732 0L4.082 16.5c-.77.833.192 2.5 1.732 2.5z" />
                  </svg>
                  <span>{currentClipRenderError}</span>
                  <button
                    onClick={() => {
                      if (selectedClipId) {
                        setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
                      }
                    }}
                    className="ml-auto text-red-400 hover:text-red-700"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" /></svg>
                  </button>
                </div>
              )}

              {/* Render progress bar (inside modal) */}
              {isCurrentClipRendering && activeRender && (
                <div className="flex items-center gap-3 p-3 rounded-lg bg-blue-50 border border-blue-200 animate-fade-in">
                  <div className="w-4 h-4 rounded-full border-2 border-blue-200 border-t-blue-600 animate-spin flex-shrink-0" />
                  <div className="flex-1">
                    <span className="text-xs font-semibold text-blue-800">{activeRender.stage}</span>
                    {activeRender.progress !== null && (
                      <div className="h-1 w-full bg-blue-100 rounded-full overflow-hidden mt-1">
                        <div
                          className="h-full bg-blue-600 rounded-full transition-all duration-300 ease-out"
                          style={{ width: `${activeRender.progress}%` }}
                        />
                      </div>
                    )}
                  </div>
                </div>
              )}

              <div className="flex items-center justify-between">
                <button
                  onClick={() => {
                    if (selectedClipId) {
                      setRenderErrorClips((prev) => ({ ...prev, [selectedClipId]: null }));
                    }
                    closeEditor();
                  }}
                  disabled={isCurrentClipSaving || isCurrentClipRendering}
                  className="text-sm font-medium text-gray-500 hover:text-gray-800 transition-colors px-4 py-2 rounded-lg hover:bg-gray-200 disabled:opacity-40 disabled:cursor-not-allowed"
                >
                  Cancel
                </button>
                <button
                  onClick={() => handleSaveRender(selectedClipId ?? undefined, true)}
                  disabled={!isDirty || isCurrentClipSaving || isCurrentClipRendering}
                  className={`text-sm font-semibold rounded-lg px-6 py-2.5 transition-all flex items-center gap-2 ${
                    !isDirty || isCurrentClipSaving || isCurrentClipRendering
                      ? "bg-gray-100 text-gray-400 opacity-60 cursor-not-allowed pointer-events-none"
                      : "bg-gray-950 text-white hover:bg-gray-800 cursor-pointer shadow-sm active:scale-[0.98]"
                  }`}
                >
                  {isCurrentClipSaving || isCurrentClipRendering ? (
                    <>
                      <span className="w-3.5 h-3.5 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      Saving...
                    </>
                  ) : currentClipSaveSuccess ? (
                    <>
                      <svg className="w-4 h-4 text-green-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2.5} d="M5 13l4 4L19 7" />
                      </svg>
                      Changes Saved
                    </>
                  ) : (
                    "Save Changes"
                  )}
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
};
