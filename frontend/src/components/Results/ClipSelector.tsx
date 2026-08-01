import React from "react";
import { ClipCard } from "./ClipCard";

interface ClipSelectorProps {
  clips: any[];
  selectedClipId: string | null;
  selectedClipIds: string[];
  renderingClips?: Record<string, { stage: string; progress: number }>;
  setSelectedClipId: (id: string) => void;
  toggleClip: (id: string) => void;
}

export const ClipSelector: React.FC<ClipSelectorProps> = ({
  clips,
  selectedClipId,
  selectedClipIds,
  renderingClips = {},
  setSelectedClipId,
  toggleClip,
}) => {
  if (clips.length === 0) return null;

  return (
    <div className="flex flex-col gap-3 overflow-y-auto w-full">
      {clips.map((clip, idx) => (
        <ClipCard
          key={clip.id}
          clip={clip}
          index={idx}
          isSelected={selectedClipId === clip.id}
          isExportSelected={selectedClipIds.includes(clip.id)}
          renderingInfo={renderingClips[clip.id] ?? null}
          onSelect={() => setSelectedClipId(clip.id)}
          onToggleExport={() => toggleClip(clip.id)}
        />
      ))}
    </div>
  );
};
