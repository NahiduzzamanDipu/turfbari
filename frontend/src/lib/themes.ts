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

export type ThemeSurface = "plain" | "tinted";
export type ThemeButtons = "rounded" | "pill" | "square";
export type ThemeFont = "inter" | "system" | "serif" | "rounded" | "condensed";

export interface PageTheme {
  preset: string;
  color: string | null;
  secondary?: string | null;
  surface?: ThemeSurface;
  buttons?: ThemeButtons;
  font?: ThemeFont;
}

export const THEME_FONTS: Record<ThemeFont, { label: string; stack: string }> = {
  inter: { label: "Inter (default)", stack: '"Inter", ui-sans-serif, system-ui, "Segoe UI", sans-serif' },
  system: { label: "Phone / system font", stack: 'system-ui, -apple-system, "Segoe UI", Roboto, "Noto Sans Bengali", sans-serif' },
  serif: { label: "Classic serif", stack: 'Georgia, "Times New Roman", "Noto Serif Bengali", serif' },
  rounded: { label: "Rounded", stack: 'ui-rounded, "SF Pro Rounded", "Nunito", "Segoe UI", system-ui, sans-serif' },
  condensed: { label: "Sporty condensed", stack: '"Barlow Condensed", "Inter", ui-sans-serif, sans-serif' },
};

/** Black or white text, whichever reads better on `hex`. */
export function readableOn(hex: string): string {
  return contrastWithWhite(hex) >= 4.5 ? "#ffffff" : "#111827";
}

/** CSS custom properties that re-colour one turf's public page. Empty for the default brand look. */
export function themeStyle(theme: PageTheme | undefined): React.CSSProperties {
  if (!theme) return {};
  const preset = THEME_PRESETS[theme.preset as ThemePreset] ?? THEME_PRESETS.turfbari;
  const custom = theme.color && HEX.test(theme.color) && contrastWithWhite(theme.color) >= 3 ? theme.color : null;
  const secondary = theme.secondary && HEX.test(theme.secondary) ? theme.secondary : null;
  const style: Record<string, string> = {};
  if (theme.preset !== "turfbari" || custom) {
    const primary = custom ?? preset.primary;
    Object.assign(style, {
      "--primary": primary,
      "--primary-foreground": "#ffffff",
      "--ring": primary,
      "--accent": preset.accent,
      "--accent-foreground": preset.accentForeground,
    });
  }
  if (secondary) Object.assign(style, { "--accent": secondary, "--accent-foreground": readableOn(secondary) });
  if (theme.surface === "tinted") {
    style.backgroundColor = "color-mix(in oklch, var(--primary) 7%, var(--background))";
  }
  if (theme.font && theme.font !== "inter" && THEME_FONTS[theme.font]) {
    style["--font-sans"] = THEME_FONTS[theme.font].stack;
    style.fontFamily = THEME_FONTS[theme.font].stack;
  }
  return style as React.CSSProperties;
}

/** Wrapper props for a themed page: CSS variables plus the button-shape hook used in index.css. */
export function themeProps(theme: PageTheme | undefined) {
  return { style: themeStyle(theme), "data-buttons": theme?.buttons ?? "rounded" };
}
