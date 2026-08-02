import React, { useState, useEffect, useCallback, useRef } from "react";
import { Slider } from "../Common/Slider";
import { Toggle } from "../Common/Toggle";
import demoVideo from "../../assets/Create_a_premium_seamless_loo.mp4";


/* ═══════════════════════════════════════════════════════════════════════
   Types & Interfaces
   ═══════════════════════════════════════════════════════════════════════ */

interface CaptionSettingsProps {
  settings: any;
  updateSetting: (key: any, value: any) => void;
  captionStyles?: any;
  captionStylePreviews?: any;
}

interface PresetDef {
  id: string;
  label: string;
  category: "bold" | "minimal" | "animated" | "boxed";
  fontPreset: string;
  containerType: string;
  animationType: string;
  highlightMode: string;
  cardStyle: {
    fontFamily: string;
    fontWeight: string;
    fontSize: string;
    letterSpacing: string;
    textTransform?: "uppercase" | "none";
    color: string;
    textShadow?: string;
    background?: string;
    padding?: string;
    borderRadius?: string;
    border?: string;
  };
  highlightWord: number;
  highlightColor: string;
  highlightScale?: string;
}

/* ═══════════════════════════════════════════════════════════════════════
   Color Swatches & Palette Constants
   ═══════════════════════════════════════════════════════════════════════ */

const PRESET_SWATCHES = [
  { id: "white", hex: "#ffffff", label: "White" },
  { id: "black", hex: "#000000", label: "Black" },
  { id: "yellow", hex: "#facc15", label: "Yellow" },
  { id: "blue", hex: "#3b82f6", label: "Blue" },
  { id: "red", hex: "#ef4444", label: "Red" },
  { id: "green", hex: "#22c55e", label: "Green" },
  { id: "orange", hex: "#f97316", label: "Orange" },
  { id: "purple", hex: "#a855f7", label: "Purple" },
];

function hexToRgba(hex: string, alpha: number): string {
  if (!hex || !hex.startsWith("#")) return `rgba(0,0,0,${alpha})`;
  const r = parseInt(hex.slice(1, 3), 16) || 0;
  const g = parseInt(hex.slice(3, 5), 16) || 0;
  const b = parseInt(hex.slice(5, 7), 16) || 0;
  return `rgba(${r},${g},${b},${alpha})`;
}

/* ═══════════════════════════════════════════════════════════════════════
   Color Swatch Picker Component
   ═══════════════════════════════════════════════════════════════════════ */

interface ColorSwatchRowProps {
  label?: string;
  value: string;
  onChange: (hex: string) => void;
}

const ColorSwatchRow: React.FC<ColorSwatchRowProps> = ({ label, value, onChange }) => {
  const customInputRef = useRef<HTMLInputElement>(null);

  const normalizeHex = (h: string) => (h || "").toLowerCase();
  const currentNormalized = normalizeHex(value);
  const isPreset = PRESET_SWATCHES.some((s) => normalizeHex(s.hex) === currentNormalized);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 5 }}>
      {label && <span className="field-label" style={{ marginBottom: 2 }}>{label}</span>}
      <div style={{ display: "flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
        {PRESET_SWATCHES.map((swatch) => {
          const isSelected = normalizeHex(swatch.hex) === currentNormalized;
          return (
            <button
              key={swatch.hex}
              type="button"
              title={swatch.label}
              onClick={() => onChange(swatch.hex)}
              style={{
                width: 22,
                height: 22,
                borderRadius: "50%",
                backgroundColor: swatch.hex,
                border: swatch.hex === "#ffffff" ? "1px solid #d1d5db" : "1px solid transparent",
                cursor: "pointer",
                transition: "all 0.15s cubic-bezier(0.16,1,0.3,1)",
                boxShadow: isSelected
                  ? "0 0 0 2.5px #0a0a0a, 0 2px 4px rgba(0,0,0,0.2)"
                  : "0 1px 2px rgba(0,0,0,0.1)",
                transform: isSelected ? "scale(1.15)" : "scale(1)",
                position: "relative",
              }}
            />
          );
        })}

        {/* Custom Color Button */}
        <div style={{ position: "relative" }}>
          <button
            type="button"
            title="Custom Color"
            onClick={() => customInputRef.current?.click()}
            style={{
              height: 22,
              padding: "0 8px",
              borderRadius: 11,
              fontSize: 10,
              fontWeight: 600,
              cursor: "pointer",
              display: "flex",
              alignItems: "center",
              gap: 4,
              background: !isPreset ? value : "#f3f4f6",
              color: !isPreset ? (value === "#ffffff" || value.toLowerCase() === "#ffff00" || value.toLowerCase() === "#facc15" ? "#0a0a0a" : "#ffffff") : "#4b5563",
              border: !isPreset ? "2px solid #0a0a0a" : "1px solid #e5e7eb",
              transition: "all 0.15s",
              boxShadow: !isPreset ? "0 0 0 1px rgba(0,0,0,0.1)" : "none",
            }}
          >
            <span style={{ fontSize: 12, lineHeight: 1 }}>+</span>
            <span>{!isPreset ? value.toUpperCase() : "Custom"}</span>
          </button>
          <input
            ref={customInputRef}
            type="color"
            value={value || "#ffffff"}
            onChange={(e) => onChange(e.target.value)}
            style={{ position: "absolute", opacity: 0, width: 0, height: 0, pointerEvents: "none" }}
          />
        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════
   Presets Data
   ═══════════════════════════════════════════════════════════════════════ */

const PRESETS: PresetDef[] = [
  {
    id: "bold", label: "Bold Pop", category: "bold",
    fontPreset: "bold", containerType: "none", animationType: "pop", highlightMode: "single",
    cardStyle: {
      fontFamily: "Arial Black, sans-serif", fontWeight: "900", fontSize: "14px",
      letterSpacing: "1px", textTransform: "uppercase", color: "#d1d5db",
      textShadow: "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000",
    },
    highlightWord: 1, highlightColor: "#facc15", highlightScale: "1.18",
  },
  {
    id: "minimal", label: "Minimalist", category: "minimal",
    fontPreset: "minimal", containerType: "none", animationType: "fade", highlightMode: "single",
    cardStyle: {
      fontFamily: "Helvetica, Arial, sans-serif", fontWeight: "400", fontSize: "13px",
      letterSpacing: "0.5px", textTransform: "none", color: "#9ca3af",
    },
    highlightWord: 1, highlightColor: "#ffffff",
  },
  {
    id: "outline", label: "Outline", category: "bold",
    fontPreset: "heavy", containerType: "outline", animationType: "pop", highlightMode: "single",
    cardStyle: {
      fontFamily: "Impact, sans-serif", fontWeight: "700", fontSize: "15px",
      letterSpacing: "1px", textTransform: "uppercase", color: "#ffffff",
      textShadow: "-3px -3px 0 #000, 3px -3px 0 #000, -3px 3px 0 #000, 3px 3px 0 #000",
    },
    highlightWord: 0, highlightColor: "#f97316", highlightScale: "1.1",
  },
  {
    id: "boxed", label: "Boxed", category: "boxed",
    fontPreset: "clean-white", containerType: "solid", animationType: "none", highlightMode: "single",
    cardStyle: {
      fontFamily: "Arial, sans-serif", fontWeight: "700", fontSize: "13px",
      letterSpacing: "0px", color: "#ffffff",
      background: "rgba(0,0,0,0.85)", padding: "5px 12px", borderRadius: "6px",
    },
    highlightWord: 1, highlightColor: "#60a5fa",
  },
  {
    id: "karaoke-bounce", label: "Karaoke Bounce", category: "animated",
    fontPreset: "bold", containerType: "none", animationType: "bounce", highlightMode: "single",
    cardStyle: {
      fontFamily: "Arial Black, sans-serif", fontWeight: "800", fontSize: "13px",
      letterSpacing: "0.5px", textTransform: "uppercase", color: "#d1d5db",
      textShadow: "-1.5px -1.5px 0 #000, 1.5px -1.5px 0 #000, -1.5px 1.5px 0 #000, 1.5px 1.5px 0 #000",
    },
    highlightWord: 1, highlightColor: "#60a5fa", highlightScale: "1.15",
  },
  {
    id: "clean-white", label: "Clean White", category: "minimal",
    fontPreset: "clean-white", containerType: "none", animationType: "none", highlightMode: "none",
    cardStyle: {
      fontFamily: "Arial, sans-serif", fontWeight: "700", fontSize: "13px",
      letterSpacing: "0px", color: "#ffffff",
      textShadow: "1px 1px 3px rgba(0,0,0,0.6)",
    },
    highlightWord: -1, highlightColor: "#ffffff",
  },
  {
    id: "creator", label: "Creator Pro", category: "bold",
    fontPreset: "creator", containerType: "outline", animationType: "elastic", highlightMode: "creator",
    cardStyle: {
      fontFamily: "Impact, sans-serif", fontWeight: "900", fontSize: "15px",
      letterSpacing: "1.2px", textTransform: "uppercase", color: "#ffffff",
      textShadow: "-2px -2px 0 #000, 2px -2px 0 #000, -2px 2px 0 #000, 2px 2px 0 #000",
    },
    highlightWord: 1, highlightColor: "#facc15", highlightScale: "1.22",
  },
  {
    id: "viral-shorts", label: "Viral Shorts", category: "bold",
    fontPreset: "heavy", containerType: "shadow", animationType: "bounce", highlightMode: "single",
    cardStyle: {
      fontFamily: "Impact, sans-serif", fontWeight: "800", fontSize: "14px",
      letterSpacing: "1px", textTransform: "uppercase", color: "#ffffff",
      textShadow: "3px 3px 0 #000",
    },
    highlightWord: 0, highlightColor: "#facc15", highlightScale: "1.12",
  },
  {
    id: "tiktok", label: "TikTok Style", category: "boxed",
    fontPreset: "bold", containerType: "transparent-box", animationType: "pop", highlightMode: "single",
    cardStyle: {
      fontFamily: "Arial Black, sans-serif", fontWeight: "700", fontSize: "13px",
      letterSpacing: "0px", color: "#ffffff",
      background: "rgba(0,0,0,0.55)", padding: "4px 10px", borderRadius: "8px",
    },
    highlightWord: 1, highlightColor: "#38bdf8",
  },
  {
    id: "podcast", label: "Podcast Style", category: "boxed",
    fontPreset: "modern", containerType: "border-only", animationType: "none", highlightMode: "single",
    cardStyle: {
      fontFamily: "'Trebuchet MS', sans-serif", fontWeight: "600", fontSize: "12px",
      letterSpacing: "0.3px", color: "#e5e7eb",
      background: "rgba(0,0,0,0.75)", padding: "4px 8px", borderRadius: "4px",
      border: "1px solid #525252",
    },
    highlightWord: 1, highlightColor: "#facc15",
  },
];

const CATEGORIES = [
  { id: "all", label: "All" },
  { id: "bold", label: "Bold" },
  { id: "minimal", label: "Minimal" },
  { id: "animated", label: "Animated" },
  { id: "boxed", label: "Boxed" },
] as const;

const FONT_PRESETS: Record<string, { fontFamily: string; fontWeight: "normal" | "bold"; letterSpacing: number; lineHeight: number }> = {
  "minimal": { fontFamily: "Helvetica", fontWeight: "normal", letterSpacing: 1, lineHeight: 1.2 },
  "clean-white": { fontFamily: "Arial", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "bold": { fontFamily: "Arial Black", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "modern": { fontFamily: "Trebuchet MS", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.3 },
  "rounded": { fontFamily: "Arial Rounded MT Bold", fontWeight: "bold", letterSpacing: 0, lineHeight: 1.2 },
  "heavy": { fontFamily: "Impact", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.1 },
  "condensed": { fontFamily: "Arial Narrow", fontWeight: "bold", letterSpacing: -0.5, lineHeight: 1.1 },
  "elegant": { fontFamily: "Georgia", fontWeight: "bold", letterSpacing: 0.5, lineHeight: 1.4 },
  "classic": { fontFamily: "Times New Roman", fontWeight: "normal", letterSpacing: 0, lineHeight: 1.2 },
  "creator": { fontFamily: "Impact", fontWeight: "bold", letterSpacing: 1.0, lineHeight: 1.1 },
};

/* ═══════════════════════════════════════════════════════════════════════
   Main Component
   ═══════════════════════════════════════════════════════════════════════ */

export const CaptionSettings: React.FC<CaptionSettingsProps> = ({
  settings,
  updateSetting,
}) => {
  const [search, setSearch] = useState("");
  const [category, setCategory] = useState<string>("all");
  const [highlightIndex, setHighlightIndex] = useState(1);

  // Cycling highlight animation in center live preview
  useEffect(() => {
    const iv = setInterval(() => setHighlightIndex((p) => (p + 1) % 3), 1600);
    return () => clearInterval(iv);
  }, []);

  /* ─── Preset Application ─── */
  const applyPreset = useCallback((preset: PresetDef) => {
    updateSetting("captionStyle", preset.id);
    updateSetting("captionFontPreset", preset.fontPreset);
    updateSetting("captionContainerType", preset.containerType);
    updateSetting("captionAnimationType", preset.animationType);
    updateSetting("highlightColorMode", preset.highlightMode);
    if (preset.highlightColor) updateSetting("captionHighlightColor", preset.highlightColor);

    const fp = FONT_PRESETS[preset.fontPreset];
    if (fp) {
      updateSetting("captionFontFamily", fp.fontFamily);
      updateSetting("captionFontWeight", fp.fontWeight);
      updateSetting("captionLetterSpacing", fp.letterSpacing);
      updateSetting("captionLineHeight", fp.lineHeight);
    }
  }, [updateSetting]);

  const applyFontPreset = useCallback((id: string) => {
    updateSetting("captionFontPreset", id);
    if (id === "custom") return;
    const fp = FONT_PRESETS[id];
    if (fp) {
      updateSetting("captionFontFamily", fp.fontFamily);
      updateSetting("captionFontWeight", fp.fontWeight);
      updateSetting("captionLetterSpacing", fp.letterSpacing);
      updateSetting("captionLineHeight", fp.lineHeight);
    }
  }, [updateSetting]);

  /* ─── Filtering ─── */
  const filteredPresets = PRESETS.filter((p) => {
    if (category !== "all" && p.category !== category) return false;
    if (search && !p.label.toLowerCase().includes(search.toLowerCase())) return false;
    return true;
  });

  /* ─── Center preview calculations ─── */
  const previewWords = ["Create", "Viral", "Shorts"];
  const scaleFactor = 0.42;

  const getPreviewContainerStyle = (): React.CSSProperties => {
    const containerType = settings.captionContainerType || "none";
    const bgColor = settings.captionBgColor || "#000000";
    const outlineColor = settings.captionOutlineColor || "#000000";
    const base: React.CSSProperties = {
      fontFamily: settings.captionFontFamily || "Arial Black",
      fontSize: `${(settings.captionFontSize || 72) * scaleFactor}px`,
      fontWeight: settings.captionFontWeight === "normal" ? 400 : 700,
      lineHeight: settings.captionLineHeight || 1.2,
      letterSpacing: `${(settings.captionLetterSpacing || 0) * scaleFactor}px`,
      padding: `${(settings.captionPadding || 12) * 0.5}px ${(settings.captionPadding || 12) * 0.7}px`,
      opacity: (settings.captionOpacity ?? 100) / 100,
      borderRadius: `${settings.captionBorderRadius ?? 8}px`,
      transition: "all 0.25s cubic-bezier(0.16,1,0.3,1)",
      display: "flex", flexWrap: "wrap" as const, justifyContent: "center", gap: "0 6px",
    };
    if (containerType === "solid") base.backgroundColor = bgColor;
    else if (containerType === "transparent-box") base.backgroundColor = hexToRgba(bgColor, 0.6);
    else if (containerType === "border-only") { base.border = `2px solid ${outlineColor}`; base.backgroundColor = "transparent"; }
    else if (containerType === "gradient") base.background = `linear-gradient(135deg, ${bgColor}, ${outlineColor})`;
    else base.backgroundColor = "transparent";
    return base;
  };

  const getPreviewWordStyle = (isHi: boolean, idx: number): React.CSSProperties => {
    const s: React.CSSProperties = { transition: "all 0.2s cubic-bezier(0.16,1,0.3,1)", display: "inline-block" };
    const textColor = settings.captionTextColor || "#ffffff";
    const outlineColor = settings.captionOutlineColor || "#000000";
    const os = settings.captionOutlineSize ?? 3;
    const shadowColor = settings.captionShadowColor || "#000000";
    const ss = settings.captionShadowSize ?? 2;
    const hlColor = settings.captionHighlightColor || "#ffff00";
    const ct = settings.captionContainerType || "none";
    const hm = settings.highlightColorMode || "single";

    if (ct === "outline") s.textShadow = `-${os}px -${os}px 0 ${outlineColor}, ${os}px -${os}px 0 ${outlineColor}, -${os}px ${os}px 0 ${outlineColor}, ${os}px ${os}px 0 ${outlineColor}`;
    else if (ct === "shadow") s.textShadow = `${ss}px ${ss}px 0 ${shadowColor}`;
    else if (ct === "glow") s.textShadow = `0 0 8px ${outlineColor}, 0 0 14px ${outlineColor}`;
    else s.textShadow = `-1.5px -1.5px 0 ${outlineColor}, 1.5px -1.5px 0 ${outlineColor}, -1.5px 1.5px 0 ${outlineColor}, 1.5px 1.5px 0 ${outlineColor}`;

    s.color = isHi ? hlColor : textColor;
    if (isHi) {
      if (hm === "multi") {
        const palette = settings.captionMultiColors || ["#ffff00", "#00ff00", "#ef4444", "#3b82f6"];
        s.color = palette[idx % palette.length];
      } else if (hm === "random") {
        const palette = ["#ffff00", "#00ff00", "#ef4444", "#3b82f6", "#a855f7"];
        s.color = palette[(idx * 7) % palette.length];
      }
      if (hm === "creator") { s.transform = "scale(1.22)"; s.color = hlColor; s.textTransform = "uppercase"; }
      else s.transform = "scale(1.12)";
    }
    return s;
  };

  const getPreviewWordClass = (isHi: boolean): string => {
    if (!isHi) return "";
    const at = settings.captionAnimationType || "none";
    switch (at) {
      case "pop": return "animate-pop";
      case "bounce": return "animate-bounce-pop";
      case "scale": return "animate-scale-up";
      case "zoom": return "animate-zoom-in";
      case "elastic": return "animate-elastic";
      case "fade": return "animate-fade-in-quick";
      default: return "";
    }
  };

  const getPreviewPositionStyle = (): React.CSSProperties => {
    const pos = settings.captionPosition ?? "bottom";
    const base: React.CSSProperties = { position: "absolute", left: "50%", transform: "translateX(-50%)", width: "90%", textAlign: "center", display: "flex", justifyContent: "center", transition: "all 0.3s ease" };
    switch (pos) {
      case "top": return { ...base, top: "8%" };
      case "top-center": return { ...base, top: "20%" };
      case "center": return { ...base, top: "50%", transform: "translate(-50%, -50%)" };
      case "lower-third": return { ...base, bottom: "25%" };
      case "custom": return { ...base, bottom: `${((settings.captionCustomMarginV ?? 170) / 1920) * 100}%` };
      default: return { ...base, bottom: "10%" };
    }
  };

  const multiColors = settings.captionMultiColors || ["#ffff00", "#22c55e", "#ef4444", "#3b82f6"];
  const updateMultiColorStep = (index: number, newHex: string) => {
    const next = [...multiColors];
    next[index] = newHex;
    updateSetting("captionMultiColors", next);
  };

  const isHookEnabled = settings.autoHook !== false;

  /* ─── Render ─── */
  return (
    <div style={{ display: "grid", gridTemplateColumns: "1.5fr 1fr 1.5fr", height: "100%", minHeight: 0, width: "100%" }}>

      {/* ════════════ LEFT PANEL – Expanded Preset Gallery ════════════ */}
      <div style={{ borderRight: "1px solid #e5e7eb", display: "flex", flexDirection: "column", overflow: "hidden", background: "#ffffff" }}>
        {/* Search */}
        <div style={{ padding: "14px 16px 8px" }}>
          <div style={{ position: "relative" }}>
            <svg style={{ position: "absolute", left: 10, top: "50%", transform: "translateY(-50%)", pointerEvents: "none" }} width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="11" cy="11" r="8" /><path d="M21 21l-4.35-4.35" /></svg>
            <input
              type="text"
              placeholder="Search caption styles…"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              style={{ width: "100%", padding: "8px 10px 8px 32px", border: "1px solid #e5e7eb", borderRadius: 8, fontSize: 13, color: "#374151", background: "#fff", outline: "none", transition: "border-color 0.15s" }}
              onFocus={(e) => (e.target.style.borderColor = "#9ca3af")}
              onBlur={(e) => (e.target.style.borderColor = "#e5e7eb")}
            />
          </div>
        </div>

        {/* Category Tabs */}
        <div style={{ display: "flex", gap: 4, padding: "0 16px 12px", flexWrap: "wrap" }}>
          {CATEGORIES.map((c) => (
            <button
              key={c.id}
              type="button"
              onClick={() => setCategory(c.id)}
              style={{
                padding: "5px 12px", borderRadius: 6, fontSize: 11, fontWeight: 600, cursor: "pointer",
                border: "1px solid transparent", transition: "all 0.15s",
                background: category === c.id ? "#0a0a0a" : "#f3f4f6",
                color: category === c.id ? "#fff" : "#6b7280",
              }}
            >
              {c.label}
            </button>
          ))}
        </div>

        {/* Preset Cards */}
        <div style={{ flex: 1, overflowY: "auto", padding: "0 16px 16px", display: "grid", gridTemplateColumns: "1fr 1fr", gap: 12, alignContent: "start" }}>
          {filteredPresets.map((preset) => {
            const isActive = settings.captionStyle === preset.id;
            const words = preset.label.split(" ");
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => applyPreset(preset)}
                style={{
                  display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center",
                  minHeight: 96, borderRadius: 12, border: isActive ? "2.5px solid #0a0a0a" : "1px solid #e5e7eb",
                  background: "#111827", cursor: "pointer", transition: "all 0.2s cubic-bezier(0.16,1,0.3,1)",
                  boxShadow: isActive ? "0 0 0 3px rgba(10,10,10,0.12), 0 6px 16px rgba(0,0,0,0.2)" : "0 1px 4px rgba(0,0,0,0.12)",
                  transform: isActive ? "scale(1.02)" : "scale(1)",
                  padding: "14px 10px",
                  position: "relative", overflow: "hidden",
                }}
                onMouseEnter={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "#6b7280"; e.currentTarget.style.transform = "scale(1.015)"; }}}
                onMouseLeave={(e) => { if (!isActive) { e.currentTarget.style.borderColor = "#e5e7eb"; e.currentTarget.style.transform = "scale(1)"; }}}
              >
                {/* Rendered caption preview */}
                <div style={{
                  ...preset.cardStyle,
                  display: "flex", flexWrap: "wrap", justifyContent: "center", gap: "2px 4px",
                  lineHeight: 1.3, textAlign: "center",
                }}>
                  {words.map((w, i) => (
                    <span key={i} style={{
                      color: i === preset.highlightWord ? preset.highlightColor : preset.cardStyle.color,
                      transform: i === preset.highlightWord && preset.highlightScale ? `scale(${preset.highlightScale})` : undefined,
                      display: "inline-block", transition: "all 0.15s ease",
                    }}>{w}</span>
                  ))}
                </div>
                <span style={{ fontSize: 9, color: "#6b7280", marginTop: 8, fontWeight: 600, letterSpacing: "0.4px", fontFamily: "system-ui, sans-serif", textTransform: "uppercase" }}>{preset.label}</span>

                {/* Active checkmark */}
                {isActive && (
                  <div style={{ position: "absolute", top: 6, right: 6, width: 16, height: 16, borderRadius: "50%", background: "#0a0a0a", display: "flex", alignItems: "center", justifyContent: "center" }}>
                    <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="#fff" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12" /></svg>
                  </div>
                )}
              </button>
            );
          })}
        </div>
      </div>

      {/* ════════════ CENTER PANEL – 9:16 Frame ONLY (No Outer Dark Background) ════════════ */}
      <div style={{
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "16px 14px",
        background: "#f9fafb",
        borderRight: "1px solid #e5e7eb",
      }}>
        {/* Exact 9:16 Vertical Video Frame (Live Looping Presenter Demo Video Canvas) */}
        <div style={{
          aspectRatio: "9 / 16",
          height: "100%",
          maxHeight: "calc(100vh - 120px)",
          backgroundColor: "#09090b",
          borderRadius: 12,
          position: "relative",
          overflow: "hidden",
          boxShadow: "0 4px 20px rgba(0, 0, 0, 0.15)",
          border: "1px solid #1f2937",
        }}>
          {/* Live Looping Presenter Demo Video Background */}
          <video
            src={demoVideo}
            autoPlay
            loop
            muted
            playsInline
            controls={false}
            style={{
              position: "absolute",
              inset: 0,
              width: "100%",
              height: "100%",
              objectFit: "cover",
              pointerEvents: "none",
            }}
            onError={(e) => {
              (e.target as HTMLElement).style.display = "none";
            }}
          />
          {/* Dynamic Auto Hook Overlay Preview */}
          {isHookEnabled && (
            <div
              style={{
                position: "absolute",
                left: 0,
                right: 0,
                top: (settings.autoHookPosition ?? "top-center") === "top" ? "7.3%" : (settings.autoHookPosition ?? "top-center") === "middle" ? "42%" : "11.4%",
                display: "flex",
                justifyContent: "center",
                pointerEvents: "none",
                zIndex: 30,
                transition: "all 0.2s ease-out",
              }}
            >
              <div
                style={{
                  backgroundColor: settings.autoHookBgColor ?? "#000000",
                  color: settings.autoHookColor ?? "#ffffff",
                  fontFamily: settings.autoHookFont ?? "Arial Black",
                  fontSize: `${Math.round((settings.autoHookFontSize ?? 120) * 0.24)}px`,
                  fontWeight: "bold",
                  padding: `${Math.round(12 * (280 / 430))}px ${Math.round(18 * (280 / 430))}px`,
                  borderRadius: `${Math.round(8 * (280 / 430))}px`,
                  textAlign: "center",
                  maxWidth: "85%",
                  lineHeight: 1.25,
                  boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
                }}
              >
                {settings.autoHookText && settings.autoHookText.trim() ? settings.autoHookText : "Key Highlight Hook"}
              </div>
            </div>
          )}

          {/* Dynamic Caption Overlay */}
          <div style={getPreviewPositionStyle()} key={`pos-${settings.captionPosition}`}>
            <div style={getPreviewContainerStyle()}>
              {previewWords.map((word, idx) => {
                const isHi = idx === highlightIndex && (settings.highlightColorMode ?? "single") !== "none";
                return (
                  <span key={`${idx}-${highlightIndex}`} style={getPreviewWordStyle(isHi, idx)} className={getPreviewWordClass(isHi)}>
                    {word}
                  </span>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      {/* ════════════ RIGHT PANEL – Properties & Controls ════════════ */}
      <div style={{ overflowY: "auto", background: "#ffffff" }}>
        <div style={{ padding: "16px 18px", display: "flex", flexDirection: "column", gap: 0 }}>

          {/* ── Section: Typography ── */}
          <SettingsSection title="Typography" defaultOpen>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <div>
                <label className="field-label">Font Preset</label>
                <select value={settings.captionFontPreset ?? "bold"} onChange={(e) => applyFontPreset(e.target.value)} className="input-field" style={{ fontSize: 12 }}>
                  {Object.keys(FONT_PRESETS).map((id) => <option key={id} value={id}>{id.replace("-", " ")}</option>)}
                  <option value="custom">Custom</option>
                </select>
              </div>
              <div>
                <label className="field-label">Font Family</label>
                <select value={settings.captionFontFamily ?? "Arial Black"} onChange={(e) => { updateSetting("captionFontFamily", e.target.value); updateSetting("captionFontPreset", "custom"); }} className="input-field" style={{ fontSize: 12 }}>
                  {["Arial","Arial Black","Helvetica","Impact","Verdana","Trebuchet MS","Georgia","Times New Roman","Courier New"].map((f) => <option key={f} value={f}>{f}</option>)}
                </select>
              </div>
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
              <div>
                <label className="field-label">Weight</label>
                <select value={settings.captionFontWeight ?? "bold"} onChange={(e) => { updateSetting("captionFontWeight", e.target.value); updateSetting("captionFontPreset", "custom"); }} className="input-field" style={{ fontSize: 12 }}>
                  <option value="normal">Normal</option>
                  <option value="bold">Bold</option>
                </select>
              </div>
              <Slider label="Font Size" min={24} max={140} value={settings.captionFontSize ?? 72} onChange={(v) => updateSetting("captionFontSize", v)} unit="px" />
            </div>

            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
              <Slider label="Letter Spacing" min={-4} max={15} value={settings.captionLetterSpacing ?? 0} onChange={(v) => { updateSetting("captionLetterSpacing", v); updateSetting("captionFontPreset", "custom"); }} unit="px" />
              <Slider label="Line Height" min={0.8} max={2.2} step={0.1} value={settings.captionLineHeight ?? 1.2} onChange={(v) => { updateSetting("captionLineHeight", v); updateSetting("captionFontPreset", "custom"); }} unit="x" />
            </div>
          </SettingsSection>

          {/* ── Section: Highlight Engine ── */}
          <SettingsSection title="Highlight Engine" defaultOpen>
            <label className="field-label">Highlight Mode</label>
            <div style={{ display: "flex", gap: 4, background: "#f3f4f6", padding: 3, borderRadius: 8, marginBottom: 10 }}>
              {[
                { id: "none", label: "Off" },
                { id: "single", label: "Single" },
                { id: "multi", label: "Multi" },
                { id: "creator", label: "Creator" },
              ].map((mode) => {
                const isActive = (settings.highlightColorMode ?? "single") === mode.id;
                return (
                  <button
                    key={mode.id}
                    type="button"
                    onClick={() => updateSetting("highlightColorMode", mode.id)}
                    style={{
                      flex: 1, padding: "5px 0", textAlign: "center", borderRadius: 6, fontSize: 11, fontWeight: 600,
                      cursor: "pointer", transition: "all 0.15s", border: "1px solid transparent",
                      background: isActive ? "#ffffff" : "transparent",
                      color: isActive ? "#0a0a0a" : "#6b7280",
                      boxShadow: isActive ? "0 1px 3px rgba(0,0,0,0.1)" : "none",
                    }}
                  >
                    {mode.label}
                  </button>
                );
              })}
            </div>

            {(settings.highlightColorMode ?? "single") === "multi" ? (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, background: "#f9fafb", padding: 10, borderRadius: 10, border: "1px solid #e5e7eb" }}>
                <span className="field-label" style={{ marginBottom: 0 }}>Rotation Steps (4 Colors)</span>
                <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 8 }}>
                  {multiColors.map((colorHex: string, idx: number) => (
                    <div key={idx} style={{ display: "flex", flexDirection: "column", alignItems: "center", gap: 4 }}>
                      <span style={{ fontSize: 10, color: "#6b7280", fontWeight: 600 }}>Step {idx + 1}</span>
                      <div style={{ position: "relative" }}>
                        <input
                          type="color"
                          value={colorHex}
                          onChange={(e) => updateMultiColorStep(idx, e.target.value)}
                          style={{
                            width: 26,
                            height: 26,
                            borderRadius: "50%",
                            border: "2px solid #ffffff",
                            boxShadow: "0 0 0 1.5px #d1d5db, 0 1px 3px rgba(0,0,0,0.15)",
                            cursor: "pointer",
                            padding: 0,
                            background: "none",
                          }}
                        />
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            ) : (settings.highlightColorMode ?? "single") !== "none" ? (
              <ColorSwatchRow
                label="Accent Highlight Color"
                value={settings.captionHighlightColor ?? "#ffff00"}
                onChange={(v) => updateSetting("captionHighlightColor", v)}
              />
            ) : null}
          </SettingsSection>

          {/* ── Section: Text & Palette Colors ── */}
          <SettingsSection title="Text & Background Colors">
            <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
              <ColorSwatchRow
                label="Text Color"
                value={settings.captionTextColor ?? settings.textColor ?? "#ffffff"}
                onChange={(v) => updateSetting("captionTextColor", v)}
              />
              <ColorSwatchRow
                label="Background Box Color"
                value={settings.captionBgColor ?? "#000000"}
                onChange={(v) => updateSetting("captionBgColor", v)}
              />
              <ColorSwatchRow
                label="Outline Stroke Color"
                value={settings.captionOutlineColor ?? "#000000"}
                onChange={(v) => updateSetting("captionOutlineColor", v)}
              />
              <ColorSwatchRow
                label="Shadow Color"
                value={settings.captionShadowColor ?? "#000000"}
                onChange={(v) => updateSetting("captionShadowColor", v)}
              />
            </div>
          </SettingsSection>

          {/* ── Section: Container & Background ── */}
          <SettingsSection title="Container & Frame">
            <label className="field-label">Background Style</label>
            <select value={settings.captionContainerType ?? "none"} onChange={(e) => updateSetting("captionContainerType", e.target.value)} className="input-field" style={{ fontSize: 12, marginBottom: 8 }}>
              {[["none","No Background"],["solid","Solid Box"],["transparent-box","Transparent Box"],["outline","Outline Stroke"],["shadow","Drop Shadow"],["glow","Glow Effect"],["border-only","Border Only"],["gradient","Gradient"]].map(([id, l]) => <option key={id} value={id}>{l}</option>)}
            </select>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              <Slider label="Padding" min={0} max={40} value={settings.captionPadding ?? 12} onChange={(v) => updateSetting("captionPadding", v)} unit="px" />
              <Slider label="Radius" min={0} max={24} value={settings.captionBorderRadius ?? 8} onChange={(v) => updateSetting("captionBorderRadius", v)} unit="px" />
            </div>
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8, marginTop: 8 }}>
              <Slider label="Outline Thickness" min={0} max={10} value={settings.captionOutlineSize ?? 3} onChange={(v) => updateSetting("captionOutlineSize", v)} unit="px" />
              <Slider label="Shadow Offset" min={0} max={10} value={settings.captionShadowSize ?? 2} onChange={(v) => updateSetting("captionShadowSize", v)} unit="px" />
            </div>
            <div style={{ marginTop: 8 }}>
              <Slider label="Opacity" min={10} max={100} value={settings.captionOpacity ?? 100} onChange={(v) => updateSetting("captionOpacity", v)} unit="%" />
            </div>
          </SettingsSection>

          {/* ── Section: Animation ── */}
          <SettingsSection title="Entry Animation">
            <label className="field-label">Animation Type</label>
            <select value={settings.captionAnimationType ?? "none"} onChange={(e) => updateSetting("captionAnimationType", e.target.value)} className="input-field" style={{ fontSize: 12 }}>
              {[["none","None"],["fade","Smooth Fade"],["pop","Pop Zoom"],["bounce","Karaoke Bounce"],["scale","Scale Up"],["zoom","Zoom In"],["elastic","Elastic Spring"]].map(([id,l]) => <option key={id} value={id}>{l}</option>)}
            </select>
          </SettingsSection>

          {/* ── Section: Position ── */}
          <SettingsSection title="Position & Alignment">
            <label className="field-label">Vertical Alignment</label>
            <select value={settings.captionPosition ?? "bottom"} onChange={(e) => updateSetting("captionPosition", e.target.value)} className="input-field" style={{ fontSize: 12, marginBottom: 8 }}>
              {[["bottom","Bottom"],["lower-third","Lower Third"],["center","Center"],["top-center","Top Center"],["top","Top"],["custom","Custom Margin"]].map(([id,l]) => <option key={id} value={id}>{l}</option>)}
            </select>
            {(settings.captionPosition ?? "bottom") === "custom" && (
              <Slider label="Custom Vertical Margin" min={20} max={1500} value={settings.captionCustomMarginV ?? 170} onChange={(v) => updateSetting("captionCustomMarginV", v)} unit="px" />
            )}
          </SettingsSection>

          {/* ── Section: Segmentation ── */}
          <SettingsSection title="Text Segmentation">
            <label className="field-label">Caption Mode</label>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {[
                { value: "3-words", label: "Word Count Mode", isWord: true },
                { value: "phrase", label: "Phrase Mode" },
                { value: "sentence", label: "Full Sentence Mode" },
              ].map((opt) => {
                const mode = settings.captionDisplayMode ?? "phrase";
                const checked = opt.isWord ? (mode !== "phrase" && mode !== "sentence") : mode === opt.value;
                return (
                  <label key={opt.value} style={{ display: "flex", alignItems: "center", gap: 8, cursor: "pointer", fontSize: 12, color: "#374151" }}>
                    <input type="radio" name="segMode" checked={checked} onChange={() => updateSetting("captionDisplayMode", opt.value)} style={{ accentColor: "#0a0a0a" }} />
                    {opt.label}
                  </label>
                );
              })}
            </div>
            {(() => {
              const mode = settings.captionDisplayMode ?? "phrase";
              if (mode === "phrase" || mode === "sentence") return null;
              let cnt = 3;
              if (mode === "word") cnt = 1;
              else { const m = mode.match?.(/^(\d+)-words?$/); if (m) cnt = parseInt(m[1], 10); }
              return (
                <div style={{ display: "flex", alignItems: "center", gap: 8, marginTop: 8, padding: "6px 10px", background: "#f9fafb", borderRadius: 8, border: "1px solid #e5e7eb" }}>
                  <span style={{ fontSize: 11, color: "#6b7280", fontWeight: 500 }}>Words per block:</span>
                  <button type="button" onClick={() => { const n = Math.max(1, cnt - 1); updateSetting("captionDisplayMode", n === 1 ? "word" : `${n}-words`); }} style={{ width: 22, height: 22, borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "#374151" }}>−</button>
                  <span style={{ fontFamily: "monospace", fontSize: 13, fontWeight: 700, color: "#0a0a0a", width: 18, textAlign: "center" }}>{cnt}</span>
                  <button type="button" onClick={() => { const n = Math.min(20, cnt + 1); updateSetting("captionDisplayMode", `${n}-words`); }} style={{ width: 22, height: 22, borderRadius: 4, border: "1px solid #d1d5db", background: "#fff", cursor: "pointer", display: "flex", alignItems: "center", justifyContent: "center", fontSize: 13, fontWeight: 700, color: "#374151" }}>+</button>
                </div>
              );
            })()}
          </SettingsSection>

          {/* ── Section: Auto Hook ── */}
          <SettingsSection title="Auto Hook Overlay">
            <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between", marginBottom: 8 }}>
              <span style={{ fontSize: 12, color: "#6b7280" }}>Display hook overlay on clip start</span>
              <Toggle label="" checked={isHookEnabled} onChange={(c) => updateSetting("autoHook", c)} />
            </div>
            {isHookEnabled && (
              <div style={{ display: "flex", flexDirection: "column", gap: 8, paddingTop: 8, borderTop: "1px solid #f3f4f6" }}>
                <input type="text" value={settings.autoHookText ?? ""} onChange={(e) => updateSetting("autoHookText", e.target.value)} placeholder="Default hook text" className="input-field" style={{ fontSize: 12 }} />
                
                <div>
                  <label className="field-label" style={{ marginBottom: 4 }}>Hook Duration Mode</label>
                  <div className="segment-root">
                    <button
                      type="button"
                      className={`segment-option ${(settings.autoHookDurationMode ?? "custom") === "custom" ? "active" : ""}`}
                      onClick={() => updateSetting("autoHookDurationMode", "custom")}
                    >
                      Custom Duration
                    </button>
                    <button
                      type="button"
                      className={`segment-option ${(settings.autoHookDurationMode ?? "custom") === "entire" ? "active" : ""}`}
                      onClick={() => updateSetting("autoHookDurationMode", "entire")}
                    >
                      Entire Video
                    </button>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div style={{ opacity: (settings.autoHookDurationMode ?? "custom") === "entire" ? 0.4 : 1, pointerEvents: (settings.autoHookDurationMode ?? "custom") === "entire" ? "none" : "auto" }}>
                    <Slider label="Duration" min={1} max={10} value={settings.autoHookDuration ?? 5} onChange={(v) => updateSetting("autoHookDuration", v)} unit="s" disabled={(settings.autoHookDurationMode ?? "custom") === "entire"} />
                  </div>
                  <Slider label="Font Size" min={24} max={160} value={settings.autoHookFontSize ?? 120} onChange={(v) => updateSetting("autoHookFontSize", v)} unit="px" />
                </div>
                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <div>
                    <label className="field-label">Font</label>
                    <select value={settings.autoHookFont ?? "Arial Black"} onChange={(e) => updateSetting("autoHookFont", e.target.value)} className="input-field" style={{ fontSize: 12 }}>
                      {["Arial","Arial Black","Helvetica","Impact","Verdana","Georgia","Courier New"].map((f) => <option key={f} value={f}>{f}</option>)}
                    </select>
                  </div>
                  <div>
                    <label className="field-label">Position</label>
                    <select value={settings.autoHookPosition ?? "top-center"} onChange={(e) => updateSetting("autoHookPosition", e.target.value)} className="input-field" style={{ fontSize: 12 }}>
                      <option value="top">Top</option>
                      <option value="top-center">Top Center</option>
                      <option value="middle">Middle</option>
                    </select>
                  </div>
                </div>

                <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
                  <Slider label="Fade In" min={0} max={1000} step={50} value={settings.autoHookFadeIn ?? 300} onChange={(v) => updateSetting("autoHookFadeIn", v)} unit="ms" />
                  <Slider label="Fade Out" min={0} max={1000} step={50} value={settings.autoHookFadeOut ?? 500} onChange={(v) => updateSetting("autoHookFadeOut", v)} unit="ms" />
                </div>
                <ColorSwatchRow label="Hook Text Color" value={settings.autoHookColor ?? "#ffffff"} onChange={(v) => updateSetting("autoHookColor", v)} />
                <ColorSwatchRow label="Hook Background Color" value={settings.autoHookBgColor ?? "#000000"} onChange={(v) => updateSetting("autoHookBgColor", v)} />
              </div>
            )}
          </SettingsSection>

        </div>
      </div>
    </div>
  );
};

/* ═══════════════════════════════════════════════════════════════════════
   Collapsible Section Helper Component
   ═══════════════════════════════════════════════════════════════════════ */

interface SettingsSectionProps {
  title: string;
  defaultOpen?: boolean;
  children: React.ReactNode;
}

const SettingsSection: React.FC<SettingsSectionProps> = ({ title, defaultOpen = false, children }) => {
  return (
    <details open={defaultOpen} style={{ borderBottom: "1px solid #f3f4f6" }} className="group">
      <summary style={{
        display: "flex", alignItems: "center", justifyContent: "space-between",
        padding: "11px 0", cursor: "pointer", userSelect: "none", listStyle: "none",
        fontSize: 11, fontWeight: 700, color: "#374151", textTransform: "uppercase", letterSpacing: "0.05em",
      }}>
        <span>{title}</span>
        <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="#9ca3af" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" style={{ transition: "transform 0.2s" }} className="group-open:rotate-180"><polyline points="6 9 12 15 18 9" /></svg>
      </summary>
      <div style={{ paddingBottom: 14 }}>
        {children}
      </div>
    </details>
  );
};
