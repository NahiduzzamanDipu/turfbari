import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, ExternalLink, Loader2, Palette, PlayCircle, RotateCcw, Send, Trash2 } from "lucide-react";
import { useEffect, useState } from "react";
import { toast } from "sonner";
import { PageHeader } from "@/components/layout/AppShell";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge, ErrorState, FormField, Input } from "@/components/ui/form";
import { Skeleton } from "@/components/ui/skeleton";
import { useActiveMembership } from "@/features/auth/auth";
import { ApiError, api } from "@/lib/api";
import {
  type PageTheme,
  THEME_FONTS,
  THEME_PRESETS,
  type ThemeButtons,
  type ThemeFont,
  type ThemePreset,
  type ThemeSurface,
  contrastWithWhite,
  themeProps,
} from "@/lib/themes";
import { cn } from "@/lib/utils";
import { errorText } from "./hooks";

interface DesignResponse {
  published: Required<PageTheme>;
  draft: Required<PageTheme> | null;
  youtube_video_id: string | null;
  slug: string;
}

const HEX = /^#[0-9a-f]{6}$/i;
const YT_ID = /^[A-Za-z0-9_-]{11}$/;

/** Same rules as the server (apps/turfs/design_views.youtube_id), used only for the instant preview. */
function youtubeId(url: string): string | null {
  const raw = url.trim();
  if (YT_ID.test(raw)) return raw;
  try {
    const u = new URL(/^https?:\/\//.test(raw) ? raw : `https://${raw}`);
    const host = u.hostname.toLowerCase();
    if (!["youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtu.be"].includes(host)) return null;
    let id: string | null = null;
    if (host === "youtu.be") id = u.pathname.split("/")[1] ?? null;
    else if (u.pathname === "/watch") id = u.searchParams.get("v");
    else {
      const [kind, value] = u.pathname.split("/").filter(Boolean);
      if (kind && ["shorts", "embed", "live", "v"].includes(kind)) id = value ?? null;
    }
    return id && YT_ID.test(id) ? id : null;
  } catch {
    return null;
  }
}

function Choice<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { value: T; label: string; sample?: React.ReactNode }[];
  onChange: (v: T) => void;
}) {
  return (
    <fieldset>
      <legend className="mb-2 text-sm font-medium">{label}</legend>
      <div className="flex flex-wrap gap-2" role="radiogroup" aria-label={label}>
        {options.map((o) => (
          <button
            key={o.value}
            type="button"
            role="radio"
            aria-checked={value === o.value}
            onClick={() => onChange(o.value)}
            className={cn("rounded-lg border px-3 py-2 text-sm transition hover:bg-secondary", value === o.value && "border-primary ring-1 ring-primary")}
          >
            {o.sample ?? o.label}
          </button>
        ))}
      </div>
    </fieldset>
  );
}

export function DesignPage() {
  const qc = useQueryClient();
  const isOwner = useActiveMembership()?.role === "owner";
  const design = useQuery({ queryKey: ["ws", "design"], queryFn: () => api<DesignResponse>("/workspace/design/") });
  const [theme, setTheme] = useState<Required<PageTheme> | null>(null);
  const [videoUrl, setVideoUrl] = useState("");
  useEffect(() => {
    if (design.data && !theme) setTheme(design.data.draft ?? design.data.published);
  }, [design.data, theme]);
  const done = (d: DesignResponse, message: string) => {
    toast.success(message);
    qc.setQueryData(["ws", "design"], d);
  };
  const saveDraft = useMutation({
    mutationFn: () => api<DesignResponse>("/workspace/design/", { method: "PUT", json: { ...theme, color: theme?.color || null, secondary: theme?.secondary || null } }),
    onSuccess: (d) => done(d, "Draft saved — not live yet"),
    onError: (e) => toast.error(errorText(e)),
  });
  const publish = useMutation({
    mutationFn: async () => {
      await api<DesignResponse>("/workspace/design/", { method: "PUT", json: { ...theme, color: theme?.color || null, secondary: theme?.secondary || null } });
      return api<DesignResponse>("/workspace/design/publish/", { method: "POST" });
    },
    onSuccess: (d) => done(d, "Published — your booking page has the new look"),
    onError: (e) => toast.error(errorText(e)),
  });
  const discard = useMutation({
    mutationFn: () => api<DesignResponse>("/workspace/design/publish/", { method: "DELETE" }),
    onSuccess: (d) => {
      setTheme(d.published);
      done(d, "Draft discarded");
    },
  });
  const video = useMutation({
    mutationFn: (url: string) => api<DesignResponse>("/workspace/design/video/", { method: "PUT", json: { url } }),
    onSuccess: (d) => {
      setVideoUrl("");
      done(d, d.youtube_video_id ? "Video added to your booking page" : "Video removed");
    },
    onError: (e) => toast.error(errorText(e)),
  });

  const d = design.data;
  const set = (patch: Partial<PageTheme>) => setTheme((t) => (t ? ({ ...t, ...patch } as Required<PageTheme>) : t));
  const colorOk = !theme?.color || (HEX.test(theme.color) && contrastWithWhite(theme.color) >= 3);
  const secondaryOk = !theme?.secondary || HEX.test(theme.secondary);
  const changed = theme && d && JSON.stringify(theme) !== JSON.stringify(d.published);
  const previewId = youtubeId(videoUrl);
  const fieldErrors = saveDraft.error instanceof ApiError ? saveDraft.error.fields : null;

  return (
    <>
      <PageHeader
        title="Page design"
        description="How your public booking page looks. Try changes in the preview, save a draft, and publish when you're happy."
        actions={
          d && (
            <Button asChild variant="outline">
              <a href={`/turfs/${d.slug}`} target="_blank" rel="noreferrer">
                <ExternalLink /> Open live page
              </a>
            </Button>
          )
        }
      />
      {design.isPending && <Skeleton className="h-96" />}
      {design.isError && <ErrorState error={design.error} onRetry={() => design.refetch()} />}
      {d && theme && (
        <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
          <div className="flex flex-col gap-6">
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Palette className="size-4" /> Theme
                  {d.draft && <Badge tone="amber">Unpublished draft</Badge>}
                </CardTitle>
              </CardHeader>
              <CardContent>
                <fieldset disabled={!isOwner} className="flex flex-col gap-5">
                  <div className="grid grid-cols-2 gap-2 sm:grid-cols-3" role="radiogroup" aria-label="Colour preset">
                    {(Object.entries(THEME_PRESETS) as [ThemePreset, (typeof THEME_PRESETS)[ThemePreset]][]).map(([key, p]) => (
                      <button
                        key={key}
                        type="button"
                        role="radio"
                        aria-checked={theme.preset === key}
                        onClick={() => set({ preset: key, color: null, secondary: null })}
                        className={cn(
                          "flex items-center gap-2 rounded-lg border px-3 py-2 text-left text-sm transition hover:bg-secondary",
                          theme.preset === key && "border-primary ring-1 ring-primary",
                        )}
                      >
                        <span className="flex shrink-0">
                          <span className="size-5 rounded-full border border-black/10" style={{ background: p.primary }} />
                          <span className="-ml-2 size-5 rounded-full border border-black/10" style={{ background: p.accent }} />
                        </span>
                        <span className="flex-1">{p.label}</span>
                        {theme.preset === key && <Check className="size-4 text-primary" />}
                      </button>
                    ))}
                  </div>
                  <div className="grid gap-3 sm:grid-cols-2">
                    <FormField label="Main colour (buttons, links)" error={!colorOk ? ["Too light for white button text — pick a darker shade."] : fieldErrors?.color}>
                      {(id) => (
                        <span className="flex gap-2">
                          <input
                            type="color"
                            aria-label="Pick main colour"
                            className="h-10 w-12 cursor-pointer rounded-md border bg-transparent p-0.5"
                            value={HEX.test(theme.color ?? "") ? theme.color! : THEME_PRESETS[theme.preset as ThemePreset]?.primary ?? "#065f46"}
                            onChange={(e) => set({ color: e.target.value })}
                          />
                          <Input id={id} placeholder="Preset" maxLength={7} className="font-mono" value={theme.color ?? ""} onChange={(e) => set({ color: e.target.value.trim() || null })} />
                        </span>
                      )}
                    </FormField>
                    <FormField label="Second colour (badges, highlights)" error={!secondaryOk ? ["Use a colour like #bef264."] : fieldErrors?.secondary}>
                      {(id) => (
                        <span className="flex gap-2">
                          <input
                            type="color"
                            aria-label="Pick second colour"
                            className="h-10 w-12 cursor-pointer rounded-md border bg-transparent p-0.5"
                            value={HEX.test(theme.secondary ?? "") ? theme.secondary! : THEME_PRESETS[theme.preset as ThemePreset]?.accent ?? "#bef264"}
                            onChange={(e) => set({ secondary: e.target.value })}
                          />
                          <Input id={id} placeholder="Preset" maxLength={7} className="font-mono" value={theme.secondary ?? ""} onChange={(e) => set({ secondary: e.target.value.trim() || null })} />
                        </span>
                      )}
                    </FormField>
                  </div>
                  <Choice<ThemeSurface>
                    label="Background"
                    value={theme.surface}
                    onChange={(surface) => set({ surface })}
                    options={[
                      { value: "plain", label: "Clean white" },
                      { value: "tinted", label: "Soft tint of main colour" },
                    ]}
                  />
                  <Choice<ThemeButtons>
                    label="Buttons"
                    value={theme.buttons}
                    onChange={(buttons) => set({ buttons })}
                    options={[
                      { value: "rounded", label: "Rounded", sample: <span className="inline-block rounded-md bg-primary px-3 py-1 text-xs text-primary-foreground">Rounded</span> },
                      { value: "pill", label: "Pill", sample: <span className="inline-block rounded-full bg-primary px-3 py-1 text-xs text-primary-foreground">Pill</span> },
                      { value: "square", label: "Square", sample: <span className="inline-block rounded-sm bg-primary px-3 py-1 text-xs text-primary-foreground">Square</span> },
                    ]}
                  />
                  <Choice<ThemeFont>
                    label="Font"
                    value={theme.font}
                    onChange={(font) => set({ font })}
                    options={(Object.entries(THEME_FONTS) as [ThemeFont, (typeof THEME_FONTS)[ThemeFont]][]).map(([value, f]) => ({
                      value,
                      label: f.label,
                      sample: <span style={{ fontFamily: f.stack }}>{f.label}</span>,
                    }))}
                  />
                </fieldset>
                {isOwner ? (
                  <div className="mt-6 flex flex-wrap justify-end gap-2">
                    {d.draft && (
                      <Button type="button" variant="ghost" disabled={discard.isPending} onClick={() => discard.mutate()}>
                        <RotateCcw /> Discard draft
                      </Button>
                    )}
                    <Button type="button" variant="outline" disabled={!colorOk || !secondaryOk || saveDraft.isPending} onClick={() => saveDraft.mutate()}>
                      Save draft
                    </Button>
                    <Button type="button" disabled={!colorOk || !secondaryOk || publish.isPending || (!changed && !d.draft)} onClick={() => publish.mutate()}>
                      {publish.isPending ? <Loader2 className="animate-spin" /> : <Send />} Publish
                    </Button>
                  </div>
                ) : (
                  <p className="mt-4 text-xs text-muted-foreground">Only the turf owner can change the page design.</p>
                )}
              </CardContent>
            </Card>

            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <PlayCircle className="size-4 text-[#FF0000]" /> Video on your page
                </CardTitle>
              </CardHeader>
              <CardContent className="flex flex-col gap-3">
                <p className="text-sm text-muted-foreground">
                  Add a YouTube video of your turf. Players see a YouTube button at the top of your page and watch it in a popup. It never autoplays.
                </p>
                {d.youtube_video_id && (
                  <div className="flex items-center justify-between gap-2 rounded-lg border p-2 text-sm">
                    <span>
                      Current video: <span className="font-mono">{d.youtube_video_id}</span>
                    </span>
                    {isOwner && (
                      <Button size="sm" variant="ghost" onClick={() => window.confirm("Remove the video from your page?") && video.mutate("")}>
                        <Trash2 /> Remove
                      </Button>
                    )}
                  </div>
                )}
                {isOwner && (
                  <form
                    className="flex flex-col gap-2 sm:flex-row sm:items-end"
                    onSubmit={(e) => {
                      e.preventDefault();
                      if (previewId) video.mutate(videoUrl);
                    }}
                  >
                    <FormField
                      label="YouTube link"
                      className="flex-1"
                      error={videoUrl && !previewId ? ["That's not a YouTube video link."] : video.error instanceof ApiError ? video.error.fields?.url : null}
                    >
                      {(id) => <Input id={id} placeholder="https://youtu.be/…" value={videoUrl} onChange={(e) => setVideoUrl(e.target.value)} />}
                    </FormField>
                    <Button type="submit" disabled={!previewId || video.isPending}>
                      {d.youtube_video_id ? "Replace video" : "Add video"}
                    </Button>
                  </form>
                )}
                {previewId && (
                  <div className="aspect-video w-full overflow-hidden rounded-lg bg-black">
                    <iframe
                      className="size-full"
                      src={`https://www.youtube-nocookie.com/embed/${previewId}?rel=0`}
                      title="Video preview"
                      allow="encrypted-media; picture-in-picture; fullscreen"
                      referrerPolicy="strict-origin-when-cross-origin"
                      allowFullScreen
                    />
                  </div>
                )}
              </CardContent>
            </Card>
          </div>

          <div className="xl:sticky xl:top-4 xl:self-start">
            <p className="mb-2 text-sm font-medium text-muted-foreground">Preview {changed ? "(not published)" : "(live look)"}</p>
            <ThemePreview theme={theme} />
          </div>
        </div>
      )}
    </>
  );
}

/** A small mock of the public booking page in the chosen theme. */
function ThemePreview({ theme }: { theme: PageTheme }) {
  const props = themeProps(theme);
  return (
    <div {...props} className="overflow-hidden rounded-2xl border bg-background shadow-sm" aria-label="Theme preview">
      <div className="relative h-32 bg-gradient-to-br from-primary to-primary/60 p-4 text-primary-foreground">
        <span className="absolute right-3 top-3 inline-flex items-center gap-1 rounded-full bg-white/95 px-2 py-1 text-xs font-semibold text-neutral-900">
          <svg viewBox="0 0 28 20" className="h-3.5 w-auto" aria-hidden>
            <rect width="28" height="20" rx="5" fill="#FF0000" />
            <path d="M11.2 5.8v8.4l7.3-4.2-7.3-4.2Z" fill="#fff" />
          </svg>
          Video
        </span>
        <span className="inline-block rounded-full bg-accent px-2 py-0.5 text-[10px] font-bold text-accent-foreground">Outdoor</span>
        <p className="mt-6 text-2xl font-extrabold uppercase leading-none">Your Turf</p>
      </div>
      <div className="flex flex-col gap-3 p-4" style={{ backgroundColor: props.style.backgroundColor as string | undefined }}>
        <p className="font-semibold">Book a slot</p>
        <div className="grid grid-cols-3 gap-2 text-xs">
          {["6:00 PM", "7:00 PM", "8:00 PM"].map((time, i) => (
            <span key={time} className={cn("rounded-lg border px-2 py-2", i === 1 && "border-primary bg-primary text-primary-foreground")}>
              <span className="block font-medium">{time}</span>
              <span className="opacity-80">৳2,000</span>
            </span>
          ))}
        </div>
        <p className="text-sm">
          Night prices from <span className="font-semibold text-primary">৳2,000/hr</span>{" "}
          <span className="rounded-full bg-accent px-2 py-0.5 text-xs font-semibold text-accent-foreground">Popular</span>
        </p>
        <Button type="button" tabIndex={-1}>
          Submit payment &amp; request booking
        </Button>
      </div>
    </div>
  );
}
