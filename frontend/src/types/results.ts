export type ClipResult = {
  id: string;
  path: string;
  mediaUrl: string;
  thumbnailUrl?: string;
  start: number;
  end: number;
  duration: number;
  aiStart: number;
  aiEnd: number;
  userStart: number | null;
  userEnd: number | null;
  score: number;
  hookScore?: number | null;
  retentionScore?: number | null;
  emotionalImpact?: number | null;
  productionScore?: number | null;
  seoScore?: number | null;
  viralScore?: number | null;
  hook: string;
  type?: string;
  trimStart?: number;
  trimEnd?: number;
  reason?: string;
  source?: string;
  model?: string;
  title?: string;
  description?: string;
  tags?: string[];
  platformRecommendation?: string;
  suggestedPostingTime?: string;
  keywords?: string[];
  translations?: Array<{
    language: string;
    mediaUrl: string;
  }>;

  // Per-clip editor overrides (saved in metadata/{clipId}.json)
  captionStyle?: string;
  captionDisplayMode?: string;
  captionFontSize?: number;
  captionPosition?: string;
  highlightColorMode?: string;
  highlightColor?: string;
  textColor?: string;
  backgroundColor?: string;
  backgroundEnabled?: boolean;
  fontFamily?: string;
  layoutMode?: string;
  blurStrength?: number;
  frameAspect?: string;
  autoHook?: boolean;
  autoHookText?: string;
  autoHookDuration?: number;
  autoHookDurationMode?: 'custom' | 'entire';
  autoHookPosition?: string;
  // Hook Layer 1 (Small Top Label) overrides
  hook1Enabled?: boolean;
  hook1Text?: string;
  hook1Font?: string;
  hook1FontSize?: number;
  hook1Color?: string;
  hook1BgColor?: string;
  hook1Radius?: number;
  hook1Padding?: number;
  hook1X?: number;
  hook1Y?: number;
  hook1Width?: number;
  hook1Opacity?: number;
  hook1Duration?: number;

  // Hook Layer 2 (Main Hook) overrides
  hook2Enabled?: boolean;
  hook2Text?: string;
  hook2Font?: string;
  hook2FontSize?: number;
  hook2Color?: string;
  hook2BgColor?: string;
  hook2Radius?: number;
  hook2Padding?: number;
  hook2Width?: number;
  hook2Position?: string;
  hook2FadeIn?: number;
  hook2FadeOut?: number;
  hook2Duration?: number;

  gameplayLayout?: string;
  gameplayVolume?: number;
  backgroundMusic?: boolean;
  musicVolume?: number;
  musicTrack?: string;
  memePath?: string;
  memeDuration?: number;
  gameplayPath?: string;
  gameplayDuration?: number;
  words?: Array<{ word: string; start: number; end: number }>;
};

export type ResultsResponse = {
  jobId: string;
  clips: ClipResult[];
};
