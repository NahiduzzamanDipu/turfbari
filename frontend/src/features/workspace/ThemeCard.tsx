import { Check, Palette } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, Input } from "@/components/ui/form";
import { THEME_PRESETS, type ThemePreset, contrastWithWhite, themeStyle } from "@/lib/themes";
import type { TurfSettings } from "@/lib/types";
import { cn } from "@/lib/utils";

const HEX = /^#[0-9a-f]{6}$/i;

/** Colour theme for this turf's public page (saved with the main "Save settings" button). */
export function ThemeCard({
  form,
  update,
}: {
  form: TurfSettings;
  update: (patch: Partial<TurfSettings>) => void;
}) {
  const color = form.theme_color ?? "";
  const valid = !color || HEX.test(color);
  const tooLight = valid && !!color && contrastWithWhite(color) < 3;
  const preview = themeStyle({ preset: form.theme_preset, color: valid && !tooLight ? color || null : null });

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Palette className="size-4" /> Public page colours
        </CardTitle>
      </CardHeader>
      <CardContent className="flex flex-col gap-4">
        <p className="text-sm text-muted-foreground">
          Colours for buttons, links and highlights on your turf's own page. The rest of TurfBari keeps its usual look.
        </p>
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Colour theme">
          {(Object.entries(THEME_PRESETS) as [ThemePreset, (typeof THEME_PRESETS)[ThemePreset]][]).map(([key, p]) => {
            const selected = form.theme_preset === key;
            return (
              <button
                key={key}
                type="button"
                role="radio"
                aria-checked={selected}
                onClick={() => update({ theme_preset: key })}
                className={cn(
                  "flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition hover:bg-secondary",
                  selected && "border-primary ring-1 ring-primary",
                )}
              >
                <span className="relative flex shrink-0">
                  <span className="size-5 rounded-full border border-black/10" style={{ background: p.primary }} />
                  <span className="-ml-2 size-5 rounded-full border border-black/10" style={{ background: p.accent }} />
                </span>
                <span className="flex-1">{p.label}</span>
                {selected && <Check className="size-4 text-primary" />}
              </button>
            );
          })}
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <label className="flex flex-col gap-1.5 text-sm font-medium">
            Custom main colour (optional)
            <span className="flex gap-2">
              <input
                type="color"
                aria-label="Pick a custom colour"
                className="h-9 w-12 cursor-pointer rounded-md border bg-transparent p-0.5"
                value={HEX.test(color) ? color : THEME_PRESETS[form.theme_preset as ThemePreset]?.primary ?? "#065f46"}
                onChange={(e) => update({ theme_color: e.target.value })}
              />
              <Input
                aria-label="Custom colour code"
                placeholder="#1f7a4d"
                maxLength={7}
                className="w-28 font-mono"
                value={color}
                onChange={(e) => update({ theme_color: e.target.value.trim() })}
              />
            </span>
          </label>
          {color && (
            <Button type="button" variant="ghost" size="sm" onClick={() => update({ theme_color: "" })}>
              Use preset colour
            </Button>
          )}
        </div>
        {!valid && <p className="text-xs text-destructive">Use a colour code like #1f7a4d.</p>}
        {tooLight && <p className="text-xs text-destructive">Too light: white text on buttons would be hard to read.</p>}
        <div style={preview} className="flex flex-wrap items-center gap-3 rounded-lg border bg-background p-3" aria-label="Preview">
          <span className="text-xs text-muted-foreground">Preview</span>
          <Button type="button" size="sm" tabIndex={-1}>
            Send booking request
          </Button>
          <Badge tone="lime">Featured</Badge>
          <span className="text-sm font-semibold text-primary">৳1,500/hr</span>
        </div>
      </CardContent>
    </Card>
  );
}
