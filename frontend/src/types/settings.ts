export type CaptionStyle =
  | "classic-white"
  | "green-highlight"
  | "yellow-highlight"
  | "blue-highlight"
  | "red-highlight"
  | "boxed"
  | "outline"
  | "bold-pop"
  | "karaoke-bounce"
  | "minimal"
  | "creator"
  | "viral-shorts"
  | "tiktok"
  | "podcast"
  // Legacy aliases for backward compatibility
  | "word-highlight"
  | "boxed-background"
  | "outline-shadow";

export type CaptionDisplayMode = "word" | "phrase" | "sentence";

export type CaptionPosition = "bottom" | "center" | "top";

export type HighlightColor = "yellow" | "green" | "red" | "cyan";

export type HighlightColorMode = "single" | "multi";

export type TranslationLanguage = "es" | "hi" | "fr" | "de" | "pt";

export type WhisperModel = "tiny" | "medium" | "large-v3";

export type HookPosition = "top" | "top-center" | "middle";

export type ProcessingSettings = {
  clipGenerationMode: "auto" | "manual";
  coverageMode: "best" | "entire";
  preferredDuration: "short" | "medium" | "long" | "auto";
  clipCount: number;
  minClipDuration: 5 | 10 | 15 | 20 | 30;
  maxClipDuration: 15 | 30 | 60;
  whisperModel: WhisperModel;
  speakerDiarization: boolean;
  backgroundMusic: boolean;
  musicVolume: number;
  thumbnailGeneration: boolean;
  silenceRemoval: boolean;
  translationLanguages: TranslationLanguage[];
  captionStyle: CaptionStyle;
  captionDisplayMode: CaptionDisplayMode;
  captionFontSize: number;
  captionPosition: CaptionPosition;
  layoutMode: "auto" | "full-crop" | "blur-pad";
  highlightColorMode: HighlightColorMode;
  highlightColor: HighlightColor;
  // Modular Caption Engine
  captionFontPreset?: "minimal" | "clean-white" | "bold" | "modern" | "rounded" | "heavy" | "condensed" | "elegant" | "classic" | "creator" | "custom";
  captionContainerType?: "none" | "solid" | "transparent-box" | "outline" | "shadow" | "glow" | "border-only" | "gradient";
  captionAnimationType?: "none" | "fade" | "pop" | "bounce" | "scale" | "zoom" | "elastic";
  captionFontFamily?: string;
  captionFontWeight?: "normal" | "bold";
  captionLetterSpacing?: number;
  captionLineHeight?: number;
  captionTextColor?: string;
  captionHighlightColor?: string;
  captionBgColor?: string;
  captionOutlineColor?: string;
  captionShadowColor?: string;
  captionBorderRadius?: number;
  captionPadding?: number;
  captionOpacity?: number;
  captionOutlineSize?: number;
  captionShadowSize?: number;
  captionCustomMarginV?: number;
  // Single Universal Auto Hook
  autoHook: boolean;
  autoHookText: string;
  autoHookFont: string;
  autoHookFontSize: number;
  autoHookColor: string;
  autoHookBgColor: string;
  autoHookPosition: HookPosition;
  autoHookDuration: number;
  autoHookDurationMode?: 'custom' | 'entire';
  autoHookPadding: number;
  autoHookRadius: number;
  autoHookFadeIn: number;
  autoHookFadeOut: number;
};
