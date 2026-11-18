import type * as React from "react";

export type ThemePreset = "turfbari" | "ocean" | "sunset" | "crimson" | "royal" | "midnight";

interface Palette {
  label: string;
  primary: string;
  accent: string;
  accentForeground: string;
}

/** Public turf page palettes. "turfbari" = the brand tokens (no override). Primaries keep white text ≥ 4.5:1. */
export const THEME_PRESETS: Record<ThemePreset, Palette> = {
  turfbari: { label: "TurfBari green", primary: "#065f46", accent: "#bef264", accentForeground: "#1a2e05" },
  ocean: { label: "Ocean blue", primary: "#1d4ed8", accent: "#7dd3fc", accentForeground: "#0c2d48" },
  sunset: { label: "Sunset orange", primary: "#c2410c", accent: "#fdba74", accentForeground: "#431407" },
  crimson: { label: "Crimson red", primary: "#b91c1c", accent: "#fca5a5", accentForeground: "#450a0a" },
  royal: { label: "Royal purple", primary: "#6d28d9", accent: "#c4b5fd", accentForeground: "#2e1065" },
  midnight: { label: "Midnight navy", primary: "#1e3a8a", accent: "#bef264", accentForeground: "#1a2e05" },
};

const HEX = /^#[0-9a-f]{6}$/i;

/** WCAG contrast of white text on `hex` (mirrors the backend check). */
export function contrastWithWhite(hex: string): number {
  const ch = (i: number) => {
    const c = Number.parseInt(hex.slice(i, i + 2), 16) / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const lum = 0.2126 * ch(1) + 0.7152 * ch(3) + 0.0722 * ch(5);
  return 1.05 / (lum + 0.05);
}

/** CSS custom properties that re-colour one turf's public page. Empty for the default brand look. */
export function themeStyle(theme: { preset: string; color: string | null } | undefined): React.CSSProperties {
  if (!theme) return {};
  const preset = THEME_PRESETS[theme.preset as ThemePreset] ?? THEME_PRESETS.turfbari;
  const custom = theme.color && HEX.test(theme.color) && contrastWithWhite(theme.color) >= 3 ? theme.color : null;
  if (theme.preset === "turfbari" && !custom) return {};
  const primary = custom ?? preset.primary;
  return {
    "--primary": primary,
    "--primary-foreground": "#ffffff",
    "--ring": primary,
    "--accent": preset.accent,
    "--accent-foreground": preset.accentForeground,
  } as React.CSSProperties;
}
